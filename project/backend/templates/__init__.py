"""Şablon sözleşmesi ve kayıt — ML intelligence platformu için merkez."""

from templates.registry import (
    ensure_template_registered,
    get_template,
    get_template_spec,
    list_template_names,
)

__all__ = [
    "ensure_template_registered",
    "get_template",
    "get_template_spec",
    "list_template_names",
]
