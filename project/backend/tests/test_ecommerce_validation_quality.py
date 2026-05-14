"""E-ticaret validasyonu + kalite skoru (LLM yok)."""

from __future__ import annotations

import pandas as pd

from tests.conftest import ecommerce_tx_dataframe
from validation.ecommerce_rules import validate_ecommerce_dataframe
from validation.quality_score import compute_quality_score


def test_good_dataset_valid():
    df = ecommerce_tx_dataframe(n_customers=150, rows_per_customer=6)
    r = validate_ecommerce_dataframe(df)
    assert r.is_valid is True
    assert r.metrics.row_count > 0
    q = compute_quality_score(r.metrics)
    assert 0 <= q.overall_score <= 100
    assert q.level in ("good", "warning", "poor")


def test_empty_dataframe_invalid():
    r = validate_ecommerce_dataframe(pd.DataFrame())
    assert r.is_valid is False
    assert r.errors


def test_missing_required_columns_fails():
    df = pd.DataFrame({"foo": [1, 2], "bar": [3, 4]})
    r = validate_ecommerce_dataframe(df)
    assert r.is_valid is False
    assert any("customer_id" in e.lower() for e in r.errors)
    assert any("order_date" in e.lower() or "tarih" in e.lower() for e in r.errors)


def test_duplicate_heavy_triggers_warning():
    df = ecommerce_tx_dataframe(n_customers=80, rows_per_customer=4, duplicate_rate=0.35)
    r = validate_ecommerce_dataframe(df)
    assert any("Yinelenen" in w for w in r.warnings)


def test_small_dataset_churn_data_not_flagged_sufficient():
    df = ecommerce_tx_dataframe(n_customers=5, rows_per_customer=2)
    r = validate_ecommerce_dataframe(df)
    q = compute_quality_score(r.metrics)
    assert r.metrics.churn_data_sufficient is False
    assert q.overall_score <= 100
