"""Kayıtlı ML şablonları — tek giriş noktası."""

from __future__ import annotations

from typing import Any

from templates.base import MlTemplate
from templates.churn import ChurnTemplate
from templates.sales_forecast import SalesForecastTemplate
from templates.segmentation import SegmentationTemplate
from templates.uplift import UpliftTemplate

_REGISTRY: dict[str, MlTemplate] | None = None


def _ensure_registry() -> dict[str, MlTemplate]:
    global _REGISTRY
    if _REGISTRY is None:
        instances: list[MlTemplate] = [
            ChurnTemplate(),
            SegmentationTemplate(),
            SalesForecastTemplate(),
            UpliftTemplate(),
        ]
        _REGISTRY = {t.name: t for t in instances}
    return _REGISTRY


def list_template_names() -> tuple[str, ...]:
    """Kayıtlı şablon kimlikleri (sıralı)."""
    reg = _ensure_registry()
    return tuple(sorted(reg.keys()))


def get_template_spec(name: str) -> MlTemplate:
    reg = _ensure_registry()
    if name not in reg:
        raise ValueError(f"Bilinmeyen şablon: {name}. Geçerliler: {list(reg.keys())}")
    return reg[name]


def get_template(name: str) -> dict[str, Any]:
    """`run_analysis_training` ve legacy kod için sözlük görünümü."""
    return get_template_spec(name).to_execution_dict()


def ensure_template_registered(name: str) -> str:
    """
    LLM veya dış girdi sonrası şablon kimliğini doğrula.
    Geçersizse ValueError (HTTP katmanı 422/400 map edebilir).
    """
    reg = _ensure_registry()
    if name not in reg:
        raise ValueError(f"Kayıtlı olmayan şablon: {name!r}. Geçerliler: {sorted(reg.keys())}")
    return name
