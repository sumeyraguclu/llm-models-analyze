from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value != "" else default


def _mock_plan() -> str:
    plan = {
        "dataset_type": "ecommerce_transactions",
        "recommended_template": "churn",
        "column_map": {
            "customer_id": "Customer ID",
            "order_date": "InvoiceDate",
            "order_id": "Invoice",
            "quantity": "Quantity",
            "unit_price": "Price",
        },
        "cleaning_plan": [
            "drop_rows_missing_customer_id",
            "parse_order_date",
            "remove_negative_quantity",
            "remove_non_positive_price",
        ],
        "feature_plan": ["build_customer_rfm_features"],
        "options": {
            # Quantile is more robust across historical datasets and small samples.
            "churn_strategy": "quantile",
            "churn_threshold_days": 90,
            "churn_quantile": 0.7,
        },
        "confidence": 0.85,
        "requires_user_confirmation": False,
        "missing_required_columns": [],
        "warnings": [],
        "reasoning": "Mock plan: örnek e-ticaret kolonları ve churn için quantile stratejisi.",
    }
    return json.dumps(plan, ensure_ascii=False)


def _mock_explain() -> str:
    explain = {
        "summary": "Mock analiz tamamlandı. Müşterilerin %23'ü churn riski taşıyor.",
        "key_findings": [
            "Toplam harcama churn ile güçlü negatif korelasyon gösteriyor.",
            "Son 90 günde sipariş vermeyen müşteriler yüksek risk grubunda.",
            "Ortalama sipariş sayısı düşük müşterilerde churn oranı daha yüksek.",
        ],
        "recommended_actions": [
            "Yüksek riskli müşterilere özel indirim kampanyası başlatın.",
            "Son 60-90 günde alışveriş yapmayan müşterilere hatırlatma e-postası gönderin.",
            "VIP müşteriler için sadakat programı oluşturun.",
        ],
        "caveats": [
            "Model 9 satırlık küçük veri ile eğitildi, gerçek veride doğrulama gerekli.",
            "Mock LLM provider kullanılıyor, üretim ortamında gerçek LLM bağlayın.",
        ],
    }
    return json.dumps(explain, ensure_ascii=False)


def _call_ollama(system_prompt: str, user_prompt: str) -> str:
    base_url = _env("OLLAMA_BASE_URL")
    if not base_url:
        raise ValueError("OLLAMA_BASE_URL gerekli (LLM_PROVIDER=ollama).")

    model = _env("OLLAMA_MODEL", "llama3")
    api_key = _env("OLLAMA_API_KEY", "")

    url = base_url.rstrip("/") + "/api/generate"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    combined_prompt = (system_prompt or "").strip() + "\n\n" + (user_prompt or "").strip()
    payload: dict[str, Any] = {
        "model": model,
        "prompt": combined_prompt,
        "stream": False,
        "format": "json",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if "response" not in data:
            raise RuntimeError("Ollama yanıtında 'response' alanı yok.")
        return str(data["response"])
    except ValueError:
        # JSON parse errors from resp.json()
        raise RuntimeError("Ollama yanıtı JSON değil veya parse edilemedi.")
    except requests.RequestException as exc:
        raise RuntimeError(f"Ollama çağrısı başarısız: {exc}") from exc


def _call_openai(system_prompt: str, user_prompt: str, *, structured_json: bool) -> str:
    api_key = _env("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY gerekli (LLM_PROVIDER=openai).")

    model = _env("OPENAI_MODEL", "gpt-4o-mini")
    try:
        from openai import APIConnectionError, APITimeoutError
        from openai import AuthenticationError, RateLimitError
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("OpenAI provider için 'openai' paketi gerekli.") from exc

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    base_url = _env("OPENAI_BASE_URL")
    if base_url:
        client_kwargs["base_url"] = base_url.rstrip("/")
    client = OpenAI(**client_kwargs)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": (system_prompt or "").strip()},
        {"role": "user", "content": (user_prompt or "").strip()},
    ]
    create_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "timeout": 120.0,
    }
    if structured_json:
        create_kwargs["response_format"] = {"type": "json_object"}

    try:
        resp = client.chat.completions.create(**create_kwargs)
    except AuthenticationError as exc:
        raise RuntimeError(
            "invalid_api_key: OpenAI API anahtarı geçersiz veya reddedildi."
        ) from exc
    except RateLimitError as exc:
        raise RuntimeError(
            f"OpenAI rate limit (429) (model={model}): {type(exc).__name__}: {exc}"
        ) from exc
    except (APIConnectionError, APITimeoutError) as exc:
        raise RuntimeError(f"OpenAI bağlantı/zaman aşımı hatası (model={model}): {exc}") from exc
    except Exception as exc:
        raise RuntimeError(
            f"OpenAI çağrısı başarısız (model={model}): {type(exc).__name__}: {exc}"
        ) from exc

    choice = resp.choices[0].message if resp.choices else None
    text = (getattr(choice, "content", None) or "").strip()
    return _clean_llm_response(text or "")


def _call_gemini(prompt: str) -> str:
    api_key = _env("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY gerekli (LLM_PROVIDER=gemini).")

    model = _env("GEMINI_MODEL", "gemini-2.0-flash")

    try:
        from google import genai
    except Exception as exc:
        raise RuntimeError(
            "Gemini provider için google-genai paketi gerekli."
        ) from exc

    def is_rate_limit_error(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if status == 429:
            return True
        msg = str(exc).lower()
        return "429" in msg or "rate limit" in msg or "resource exhausted" in msg

    client = genai.Client(api_key=api_key)

    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            text = (getattr(resp, "text", None) or "").strip()
            return _clean_llm_response(text or "")
        except Exception as exc:
            last_exc = exc
            if is_rate_limit_error(exc) and attempt < 4:
                time.sleep(2 ** (attempt - 1))  # 1s, 2s, 4s
                continue
            if is_rate_limit_error(exc):
                raise RuntimeError(
                    f"Gemini rate limit (429) sonrası tekrar denemeler tükendi (model={model}): "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            raise RuntimeError(f"Gemini çağrısı başarısız (model={model}): {type(exc).__name__}: {exc}") from exc

    raise RuntimeError(f"Gemini çağrısı başarısız (model={model}): {last_exc}")


def _clean_llm_response(text: str) -> str:
    """
    Gemini bazen JSON'u ```json ...``` içine sarabilir.
    Bu helper:
    - code fence'leri temizler
    - whitespace kırpar
    - mümkünse sadece JSON objeyi döndürür
    """
    if text is None:
        return ""

    t = str(text).strip()

    # Remove ```json ... ``` or ``` ... ``` fences
    if "```" in t:
        # prefer fenced JSON block
        start = t.find("```json")
        if start != -1:
            start = t.find("\n", start)
            if start != -1:
                end = t.find("```", start + 1)
                if end != -1:
                    t = t[start:end].strip()
        else:
            start = t.find("```")
            if start != -1:
                start = t.find("\n", start)
                if start != -1:
                    end = t.find("```", start + 1)
                    if end != -1:
                        t = t[start:end].strip()

    # If extra text exists, keep only the first JSON object
    if not (t.startswith("{") and t.endswith("}")):
        s = t.find("{")
        e = t.rfind("}")
        if s != -1 and e != -1 and e > s:
            t = t[s : e + 1].strip()

    return t.strip()


def call_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    structured_json: bool = False,
) -> str:
    provider = (_env("LLM_PROVIDER", "mock") or "mock").lower()
    logger.info(f"LLM çağrısı: {len((system_prompt or '')) + len((user_prompt or ''))} karakter")
    prompt = (system_prompt or "").strip() + "\n\n" + (user_prompt or "").strip()

    if provider == "mock":
        sp = (system_prompt or "").lower()
        up = (user_prompt or "").lower()
        if "key_findings" in sp or "explain" in up or "açıkla" in up:
            return _mock_explain()
        return _mock_plan()
    if provider == "ollama":
        return _call_ollama(system_prompt, user_prompt)
    if provider == "gemini":
        return _call_gemini(prompt)
    if provider == "openai":
        return _call_openai(system_prompt, user_prompt, structured_json=structured_json)

    raise ValueError("Bilinmeyen LLM_PROVIDER. Geçerliler: mock | ollama | gemini | openai")

