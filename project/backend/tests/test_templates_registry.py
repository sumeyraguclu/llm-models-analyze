"""Şablon registry ve template-aware validation."""

from __future__ import annotations

import pytest

from services.analysis_execution import AnalysisExecutionError, validated_plan_from_snapshot_payload
from templates.registry import ensure_template_registered, get_template, get_template_spec, list_template_names


def test_list_template_names_sorted():
    names = list_template_names()
    assert names == tuple(sorted(names))
    assert "churn" in names
    assert "segmentasyon" in names
    assert "satis_tahmini" in names


def test_get_template_execution_dict_churn():
    d = get_template("churn")
    assert d["metric"] == "accuracy"
    assert "model_class" in d
    assert "required_raw" in d


def test_get_template_spec_unknown():
    with pytest.raises(ValueError, match="Bilinmeyen"):
        get_template_spec("uplift")


def test_ensure_template_registered_rejects_unknown():
    with pytest.raises(ValueError):
        ensure_template_registered("uplift_model")


def test_validated_plan_rejects_unknown_template_in_payload():
    raw = {
        "template": "uplift",
        "column_map": {"customer_id": "c"},
        "cleaning_steps": ["drop_rows_missing_customer_id"],
        "feature_plan": ["build_customer_rfm_features"],
    }
    with pytest.raises(AnalysisExecutionError) as ei:
        validated_plan_from_snapshot_payload(raw)
    assert ei.value.detail.get("error") == "unknown_template"


def test_validate_ecommerce_respects_template_thresholds():
    import pandas as pd
    from tests.conftest import ecommerce_tx_dataframe
    from validation.ecommerce_rules import validate_ecommerce_dataframe

    df = ecommerce_tx_dataframe(n_customers=40, rows_per_customer=3)
    r_churn = validate_ecommerce_dataframe(df, template="churn")
    r_seg = validate_ecommerce_dataframe(df, template="segmentasyon")
    assert r_churn.metrics.churn_data_sufficient is False
    assert r_seg.metrics.churn_data_sufficient is True
