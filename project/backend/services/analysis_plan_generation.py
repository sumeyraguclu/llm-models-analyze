"""
LLM + hibrit kolon birleştirmesi ile doğrulanmış analysis_plan üretimi (tek kaynak).
/agent/analysis-plan ve POST /datasets/{id}/plans aynı pipeline'ı kullanır.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from agent.prompt_builder import build_system_prompt
from schemas.analysis_plan import AnalysisPlanSchema
from services.analysis_plan_normalize import normalize_raw_analysis_plan_dict
from services.column_matching import (
    match_columns_hybrid,
    merge_llm_column_map_with_hybrid,
    merge_plan_flags_with_hybrid,
    sync_missing_required_columns,
)
from services.dataset_access import require_dataset_with_profile
from services.llm_client import call_llm


def _extract_json_object(text: str) -> dict:
    if not text:
        raise ValueError("Boş yanıt alındı.")
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("JSON bulunamadı.")
    return json.loads(text[start : end + 1])


def _call_llm_or_http(
    system_prompt: str,
    user_prompt: str,
    *,
    structured_json: bool = False,
) -> str:
    """Agent router ile aynı HTTP eşlemesi (401/429)."""
    try:
        return call_llm(system_prompt, user_prompt, structured_json=structured_json)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        msg = str(exc)
        low = msg.lower()
        if "api_key_invalid" in low or "api key not found" in low or "invalid_api_key" in low:
            prov = "gemini" if "gemini" in low else ("openai" if "openai" in low else "llm")
            detail_msg = (
                "Gemini API key geçersiz veya bulunamadı."
                if prov == "gemini"
                else (
                    "OpenAI API anahtarı geçersiz veya reddedildi."
                    if prov == "openai"
                    else "LLM API anahtarı geçersiz veya bulunamadı."
                )
            )
            raise HTTPException(
                status_code=401,
                detail={"error": "invalid_api_key", "message": detail_msg, "provider": prov},
            ) from exc
        if "429" in low or "resource_exhausted" in low or "rate limit" in low:
            prov = "gemini" if "gemini" in low else ("openai" if "openai" in low else "llm")
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limited",
                    "message": "LLM rate limit; daha sonra tekrar deneyin.",
                    "provider": prov,
                },
            ) from exc
        raise HTTPException(status_code=500, detail=msg) from exc


def generate_validated_analysis_plan(
    db: Session,
    dataset_id: int,
    user_goal: str | None,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """
    Returns:
        plan_dump: AnalysisPlanSchema.model_dump() — UI ve snapshot payload_json
        mapping_confidence: hibrit kolon eşleştirme özeti (PlanSnapshot.mapping_confidence_json)
        warnings: düz liste (PlanSnapshot.warnings_json; plan_dump['warnings'] ile uyumlu)
    """
    dataset = require_dataset_with_profile(db, dataset_id)

    profile = dataset.column_profile or {}
    prof_cols = profile.get("columns") or []
    prof_names = [str(c.get("name")) for c in prof_cols if isinstance(c, dict) and c.get("name")]
    allowed_profile = set(prof_names)
    hybrid_report = match_columns_hybrid(prof_names)

    system_prompt = build_system_prompt(
        dataset,
        hybrid_hints_json=hybrid_report.to_prompt_json(),
    )

    user_goal_s = (user_goal or "").strip()
    user_message = (
        "Bir analysis_plan üret.\n"
        + (f"Kullanıcı hedefi: {user_goal_s}\n" if user_goal_s else "")
        + "Sadece JSON döndür."
    )

    raw = _call_llm_or_http(system_prompt, user_message, structured_json=True)

    try:
        plan = _extract_json_object(raw)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"analysis_plan JSON parse başarısız: {exc}") from exc

    try:
        normalized = normalize_raw_analysis_plan_dict(plan)
        normalized["column_map"] = merge_llm_column_map_with_hybrid(
            normalized["column_map"],
            hybrid_report,
            allowed_profile,
        )
        sync_missing_required_columns(normalized)
        merge_plan_flags_with_hybrid(normalized, hybrid_report)
        validated = AnalysisPlanSchema(**normalized)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={"error": "Plan validasyon hatası", "detail": str(e)},
        ) from e

    plan_dump = validated.model_dump()
    mapping_confidence = hybrid_report.to_debug_dict()
    warnings = list(plan_dump.get("warnings") or [])
    if not isinstance(warnings, list):
        warnings = []

    return plan_dump, mapping_confidence, warnings
