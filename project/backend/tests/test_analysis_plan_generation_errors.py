"""generate_validated_analysis_plan: LLM monkeypatch — ağ yok."""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Dataset
from services.analysis_plan_generation import generate_validated_analysis_plan


def _dataset_with_profile(db: Session) -> int:
    ds = Dataset(
        file_name="t.csv",
        table_name="t_dummy",
        column_defs=[{"name": "Customer ID", "dtype": "object"}],
        column_profile={
            "columns": [
                {"name": "Customer ID", "dtype": "object"},
                {"name": "InvoiceDate", "dtype": "object"},
                {"name": "Invoice", "dtype": "object"},
                {"name": "Quantity", "dtype": "int64"},
                {"name": "Price", "dtype": "float64"},
            ]
        },
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return int(ds.id)


def test_malformed_llm_json_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "services.analysis_plan_generation.call_llm",
        lambda *_a, **_k: "NOT_JSON_AT_ALL{{{",
    )
    db = SessionLocal()
    try:
        did = _dataset_with_profile(db)
        with pytest.raises(HTTPException) as ei:
            generate_validated_analysis_plan(db, did, None)
        assert ei.value.status_code == 500
    finally:
        db.close()


def test_valid_fake_llm_plan_passes_validation(monkeypatch: pytest.MonkeyPatch):
    fake = {
        "recommended_template": "churn",
        "dataset_type": "ecommerce_transactions",
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
        "options": {"churn_strategy": "quantile", "churn_quantile": 0.7, "churn_threshold_days": 90},
        "confidence": 0.9,
        "requires_user_confirmation": False,
        "missing_required_columns": [],
        "warnings": [],
        "reasoning": "fake",
    }
    monkeypatch.setattr(
        "services.analysis_plan_generation.call_llm",
        lambda *_a, **_k: json.dumps(fake, ensure_ascii=False),
    )
    db = SessionLocal()
    try:
        did = _dataset_with_profile(db)
        plan, mapping, warnings = generate_validated_analysis_plan(db, did, "churn analizi")
        assert plan["template"] == "churn"
        assert mapping
        assert isinstance(warnings, list)
    finally:
        db.close()


def test_llm_runtime_error_mapped_to_http(monkeypatch: pytest.MonkeyPatch):
    def boom(*_a, **_k):
        raise RuntimeError("invalid_api_key: test")

    monkeypatch.setattr("services.analysis_plan_generation.call_llm", boom)
    db = SessionLocal()
    try:
        did = _dataset_with_profile(db)
        with pytest.raises(HTTPException) as ei:
            generate_validated_analysis_plan(db, did, None)
        assert ei.value.status_code == 401
    finally:
        db.close()
