"""LLM ters column_map normalizasyonu."""

from __future__ import annotations

from services.analysis_plan_normalize import normalize_raw_analysis_plan_dict


def test_reverse_column_map_detected_and_flipped():
    raw = {
        "recommended_template": "churn",
        "column_map": {
            "Customer ID": "customer_id",
            "InvoiceDate": "order_date",
        },
        "cleaning_plan": [],
        "feature_plan": ["build_customer_rfm_features"],
    }
    norm = normalize_raw_analysis_plan_dict(raw)
    assert norm["column_map"]["customer_id"] == "Customer ID"
    assert norm["column_map"]["order_date"] == "InvoiceDate"
