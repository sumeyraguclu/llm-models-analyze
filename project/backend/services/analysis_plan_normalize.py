"""Tek kaynak: ham analysis_plan (LLM veya API) → AnalysisPlanSchema giriş dict'i."""

from __future__ import annotations

from cleaning.registry import CLEANING_REGISTRY
from features.registry import FEATURE_REGISTRY

_DEFAULT_CHURN_CLEANING: list[str] = [
    "drop_rows_missing_customer_id",
    "parse_order_date",
    "remove_negative_quantity",
    "remove_non_positive_price",
]

# column_map sol tarafı için bilinen standart adlar + LLM eşanlamlıları (değer tespiti / kanon)
_RECOGNIZED_STANDARD_TOKENS = frozenset(
    {
        "customer_id",
        "order_date",
        "order_id",
        "quantity",
        "unit_price",
        "last_order_date",
        "total_spent",
        "order_count",
        "date",
        "category",
        "invoice_id",
        "price",
        "treatment",
        "outcome",
        "campaign_date",
        "event_date",
        "revenue",
        "channel",
        "segment",
        "recency",
        "frequency",
        "monetary",
    }
)

_CANONICAL_STANDARD_KEYS: dict[str, str] = {
    "invoice_id": "order_id",
    "invoice": "order_id",
    "price": "unit_price",
}


def _normalize_column_map(cm: object) -> dict[str, str]:
    """
    LLM sıkça column_map'i ters üretir: dosya_kolonu -> standart.
    Beklenen: standart_anahatar -> dosyadaki kolon adı (profildeki name ile aynı).
    Ayrıca invoice_id/price -> order_id/unit_price kanonlaştırılır.
    """
    if not isinstance(cm, dict):
        return {}
    raw: dict[str, str] = {}
    for k, v in cm.items():
        if isinstance(k, str) and isinstance(v, str):
            ks, vs = k.strip(), v.strip()
            if ks and vs:
                raw[ks] = vs
    if not raw:
        return {}

    key_std = sum(1 for k in raw if k in _RECOGNIZED_STANDARD_TOKENS)
    val_std = sum(1 for v in raw.values() if v in _RECOGNIZED_STANDARD_TOKENS)

    if key_std == 0 and val_std >= 2:
        raw = {v: k for k, v in raw.items()}

    out: dict[str, str] = {}
    for std, col in raw.items():
        low = std.lower().replace(" ", "_")
        nk = _CANONICAL_STANDARD_KEYS.get(low, std)
        out[nk] = col

    if "invoice_id" in out:
        if "order_id" not in out:
            out["order_id"] = out.pop("invoice_id")
        else:
            del out["invoice_id"]

    if "price" in out:
        if "unit_price" not in out:
            out["unit_price"] = out.pop("price")
        else:
            del out["price"]

    return out


def _coerce_plain_string_list(val: object) -> list[str]:
    """warnings / missing_required_columns için basit list[str] dönüşümü."""
    if val is None:
        return []
    if isinstance(val, str):
        s = val.strip()
        return [s] if s else []
    if isinstance(val, list):
        out: list[str] = []
        for x in val:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
        return out
    return []


def _coerce_string_list(val: object, *, field: str) -> list[str]:
    """LLM bazen dict/object döndürür; list[str] veya iç içe listeye çevir."""
    if val is None:
        return []
    if isinstance(val, str):
        return [val.strip()] if val.strip() else []
    if isinstance(val, list):
        out: list[str] = []
        for x in val:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
        return out
    if isinstance(val, dict):
        for key in ("steps", "cleaning_steps", "cleaning_plan", "pipeline", "plan"):
            inner = val.get(key)
            if isinstance(inner, list):
                return _coerce_string_list(inner, field=field)
            if isinstance(inner, str) and inner.strip():
                return [inner.strip()]
        # Sözlük anahtarları doğrudan registry adları olabilir
        reg = CLEANING_REGISTRY if field == "cleaning" else FEATURE_REGISTRY
        keys = [k for k in val if isinstance(k, str) and k in reg]
        if keys:
            return keys if field == "cleaning" else keys[:1]
    return []


def normalize_raw_analysis_plan_dict(raw: dict) -> dict:
    """
    Backward/forward compatible mapping (agent + analyze ile aynı semantik):
    - template: `template` veya `recommended_template`
    - cleaning_steps: `cleaning_steps` veya `cleaning_plan`
    - feature_plan: list[str] veya tek string; dict/object → listeye çevrilir
    """
    template = raw.get("template") or raw.get("recommended_template")

    cleaning_raw = raw.get("cleaning_steps")
    if cleaning_raw is None:
        cleaning_raw = raw.get("cleaning_plan", [])

    cleaning_steps = _coerce_string_list(cleaning_raw, field="cleaning")

    feature_raw = raw.get("feature_plan", [])
    feature_plan = _coerce_string_list(feature_raw, field="feature")

    if template == "churn":
        if not feature_plan:
            feature_plan = ["build_customer_rfm_features"]
        if not cleaning_steps:
            cleaning_steps = list(_DEFAULT_CHURN_CLEANING)

    ds_type = raw.get("dataset_type")
    if not isinstance(ds_type, str) or not ds_type.strip():
        ds_type = None
    else:
        ds_type = ds_type.strip()

    if template == "uplift":
        if not feature_plan:
            feature_plan = ["build_uplift_customer_features"]
        if not cleaning_steps:
            cleaning_steps = []
        if not ds_type:
            ds_type = "customer_level_campaign_data"

    conf_raw = raw.get("confidence", 0.0)
    try:
        confidence = float(conf_raw)
    except (TypeError, ValueError):
        confidence = 0.0

    ruc = raw.get("requires_user_confirmation", True)
    if not isinstance(ruc, bool):
        ruc = True

    return {
        "template": template,
        "column_map": _normalize_column_map(raw.get("column_map")),
        "cleaning_steps": cleaning_steps,
        "feature_plan": feature_plan,
        "options": raw.get("options"),
        "reasoning": raw.get("reasoning"),
        "dataset_type": ds_type,
        "confidence": confidence,
        "requires_user_confirmation": ruc,
        "missing_required_columns": _coerce_plain_string_list(raw.get("missing_required_columns")),
        "warnings": _coerce_plain_string_list(raw.get("warnings")),
    }
