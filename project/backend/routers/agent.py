import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agent.prompt_builder import build_chat_system_prompt
from database import get_db
from models import AIModel, Dataset
from services.analysis_plan_generation import generate_validated_analysis_plan
from services.dataset_access import require_dataset_with_profile
from services.llm_client import call_llm

router = APIRouter()


class AgentChatRequest(BaseModel):
    dataset_id: int = Field(..., gt=0)
    message: str = Field(..., min_length=1)


class AgentChatResponse(BaseModel):
    reply: str


class AnalysisPlanRequest(BaseModel):
    dataset_id: int = Field(..., gt=0)
    user_goal: str | None = None


class AnalysisPlanResponse(BaseModel):
    analysis_plan: dict


class ExplainRequest(BaseModel):
    model_id: int = Field(..., gt=0)
    user_goal: str | None = None


class ExplainResponse(BaseModel):
    summary: str
    key_findings: list[str]
    recommended_actions: list[str]
    caveats: list[str]


def _extract_json_object(text: str) -> dict:
    """
    Extracts the first JSON object from a string and parses it.
    This is defensive in case the model accidentally wraps JSON with extra text.
    """
    if not text:
        raise ValueError("Boş yanıt alındı.")

    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("JSON bulunamadı. Model sadece JSON döndürmeliydi.")

    candidate = text[start : end + 1]
    return json.loads(candidate)


def _call_llm_or_http(
    system_prompt: str,
    user_prompt: str,
    *,
    structured_json: bool = False,
) -> str:
    try:
        return call_llm(system_prompt, user_prompt, structured_json=structured_json)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        msg = str(exc)
        low = msg.lower()
        # Map common Gemini errors to clearer HTTP responses
        if "api_key_invalid" in low or "api key not found" in low or "invalid_api_key" in low:
            prov = "gemini" if "gemini" in low else ("openai" if "openai" in low else "llm")
            msg = (
                "Gemini API key geçersiz veya bulunamadı. AI Studio (Gemini API) key kullandığınızdan ve ilgili API erişiminin açık olduğundan emin olun."
                if prov == "gemini"
                else (
                    "OpenAI API anahtarı geçersiz veya reddedildi. OPENAI_API_KEY değerini ve faturalandırmanın açık olduğunu kontrol edin."
                    if prov == "openai"
                    else "LLM API anahtarı geçersiz veya bulunamadı."
                )
            )
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "invalid_api_key",
                    "message": msg,
                    "provider": prov,
                },
            ) from exc
        if "429" in low or "resource_exhausted" in low or "rate limit" in low:
            prov = "gemini" if "gemini" in low else ("openai" if "openai" in low else "llm")
            msg = (
                "Gemini rate limit / quota aşıldı. Biraz sonra tekrar deneyin veya quota/billing ayarlarını kontrol edin."
                if prov == "gemini"
                else (
                    "OpenAI rate limit aşıldı. Biraz sonra tekrar deneyin veya kullanım kotanızı kontrol edin."
                    if prov == "openai"
                    else "LLM rate limit aşıldı. Biraz sonra tekrar deneyin."
                )
            )
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limited",
                    "message": msg,
                    "provider": prov,
                },
            ) from exc
        raise HTTPException(status_code=500, detail=msg) from exc


def _normalize_explain_list_field(val: object) -> list[str]:
    """LLM bazen string veya object listesi döndürür; string listesine çevir."""
    if val is None:
        return []
    if isinstance(val, str):
        t = val.strip()
        return [t] if t else []
    if isinstance(val, dict):
        out: list[str] = []
        for v in val.values():
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
            elif isinstance(v, (int, float, bool)):
                out.append(str(v).strip())
        return out
    if isinstance(val, list):
        out = []
        for x in val:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
            elif isinstance(x, (int, float, bool)):
                out.append(str(x).strip())
            elif isinstance(x, dict):
                for key in ("text", "finding", "title", "description", "item"):
                    inner = x.get(key)
                    if isinstance(inner, str) and inner.strip():
                        out.append(inner.strip())
                        break
        return out
    return []


def _normalize_explain_dict(obj: dict) -> dict:
    if not isinstance(obj, dict):
        raise ValueError("explain JSON bir object olmalı.")
    out = dict(obj)
    s = out.get("summary")
    if s is not None and not isinstance(s, str):
        out["summary"] = str(s).strip()
    for k in ("key_findings", "recommended_actions", "caveats"):
        out[k] = _normalize_explain_list_field(out.get(k))
    return out


def _validate_explanation(obj: dict) -> ExplainResponse:
    required = ["summary", "key_findings", "recommended_actions", "caveats"]
    missing = [k for k in required if k not in obj]
    if missing:
        raise ValueError(f"explain JSON eksik alanlar: {missing}")

    if not isinstance(obj["summary"], str) or not obj["summary"].strip():
        raise ValueError("explain.summary string olmalı.")

    for k in ["key_findings", "recommended_actions", "caveats"]:
        if not isinstance(obj[k], list) or not all(isinstance(x, str) and x.strip() for x in obj[k]):
            raise ValueError(f"explain.{k} string list olmalı.")

    return ExplainResponse(
        summary=obj["summary"].strip(),
        key_findings=[x.strip() for x in obj["key_findings"]],
        recommended_actions=[x.strip() for x in obj["recommended_actions"]],
        caveats=[x.strip() for x in obj["caveats"]],
    )


@router.post("/agent/chat", response_model=AgentChatResponse)
def chat_with_agent(payload: AgentChatRequest, db: Session = Depends(get_db)):
    try:
        dataset = require_dataset_with_profile(db, payload.dataset_id)

        system_prompt = build_chat_system_prompt(dataset)
        answer = call_llm(system_prompt, payload.message)
        return AgentChatResponse(reply=answer)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent hatası: {exc}") from exc


@router.post("/agent/analysis-plan", response_model=AnalysisPlanResponse)
def create_analysis_plan(payload: AnalysisPlanRequest, db: Session = Depends(get_db)):
    try:
        plan_dump, _, _ = generate_validated_analysis_plan(db, payload.dataset_id, payload.user_goal)
        return AnalysisPlanResponse(analysis_plan=plan_dump)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent planning hatası: {exc}") from exc


@router.post("/agent/explain", response_model=ExplainResponse)
def explain_model_results(payload: ExplainRequest, db: Session = Depends(get_db)):
    try:
        model_row = db.query(AIModel).filter(AIModel.id == payload.model_id).first()
        if not model_row:
            raise HTTPException(status_code=404, detail="Model bulunamadı.")
        if model_row.status != "completed" or not model_row.metrics:
            raise HTTPException(status_code=400, detail="Model metrikleri hazır değil (completed + metrics gerekli).")

        dataset = db.query(Dataset).filter(Dataset.id == model_row.dataset_id).first()
        table_name = dataset.table_name if dataset else None

        system_prompt = """
Sen teknik olmayan bir dil kullanan veri bilimi asistanısın.
Kullanıcıya model sonuçlarını anlaşılır ve aksiyon odaklı şekilde anlat.

KRITIK:
- Kod yazma, tool çağırma veya SQL çalıştırma YAPMA.
- SADECE tek bir JSON object döndür (açıklama/markdown/metin yok).
- JSON şemasını şu alanlarla üret: summary, key_findings, recommended_actions, caveats.

Alan tipleri (zorunlu):
- summary: tek string (kısa genel özet).
- key_findings: JSON array; her eleman string (ör. 3-5 madde).
- recommended_actions: JSON array; her eleman string (ör. 3-5 aksiyon).
- caveats: JSON array; her eleman string (ör. 2-4 uyarı).
ASLA key_findings için tek string veya object/dict kullanma; her zaman string dizisi kullan.
Örnek:
{"summary": "...", "key_findings": ["...", "..."], "recommended_actions": ["..."], "caveats": ["..."]}
""".strip()

        user_goal = (payload.user_goal or "").strip()
        user_message = (
            "Aşağıdaki model koşusunun metriklerini kullanıcı için özetle.\n"
            + (f"Kullanıcı hedefi: {user_goal}\n" if user_goal else "")
            + f"Dataset table: {table_name}\n"
            + f"Template: {model_row.template}\n"
            + f"Column map: {json.dumps(model_row.column_map or {}, ensure_ascii=False)}\n"
            + f"Metrics: {json.dumps(model_row.metrics or {}, ensure_ascii=False)}\n"
            + "Sadece JSON döndür."
        )

        raw = _call_llm_or_http(system_prompt, user_message, structured_json=True)

        try:
            obj = _extract_json_object(raw)
            obj = _normalize_explain_dict(obj)
            resp = _validate_explanation(obj)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"explain JSON parse/validasyon başarısız: {exc}") from exc

        return resp
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Explain hatası: {exc}") from exc
