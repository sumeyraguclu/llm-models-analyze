"""
Geriye dönük uyumluluk: şablon tanımları `templates/` paketine taşındı.

Yeni kod: `from templates.registry import get_template, get_template_spec`.
"""

from __future__ import annotations

from typing import Any

from templates.registry import get_template, get_template_spec, list_template_names

__all__ = ["get_template", "get_template_spec", "list_template_names", "TEMPLATES"]


def __getattr__(name: str) -> Any:
    if name == "TEMPLATES":
        return {n: get_template(n) for n in list_template_names()}
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
