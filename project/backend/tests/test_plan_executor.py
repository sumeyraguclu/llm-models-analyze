"""Plan executor: registry dışı adım ve column_map güvenliği."""

from __future__ import annotations

import pandas as pd
import pytest

from services.plan_executor import execute_analysis_plan


def _minimal_df():
    return pd.DataFrame(
        {
            "Customer ID": [1, 1],
            "InvoiceDate": ["2024-06-01", "2024-07-01"],
            "Invoice": ["a", "b"],
            "Quantity": [1, 2],
            "Price": [10.0, 5.0],
        }
    )


def test_unknown_cleaning_step_rejected():
    df = _minimal_df()
    plan = {
        "column_map": {
            "customer_id": "Customer ID",
            "order_date": "InvoiceDate",
            "order_id": "Invoice",
            "quantity": "Quantity",
            "unit_price": "Price",
        },
        "cleaning_plan": ["not_a_real_step"],
        "feature_plan": "build_customer_rfm_features",
    }
    with pytest.raises(ValueError, match="Bilinmeyen cleaning"):
        execute_analysis_plan(df, plan)


def test_unknown_feature_plan_rejected():
    df = _minimal_df()
    plan = {
        "column_map": {
            "customer_id": "Customer ID",
            "order_date": "InvoiceDate",
            "order_id": "Invoice",
            "quantity": "Quantity",
            "unit_price": "Price",
        },
        "cleaning_plan": [],
        "feature_plan": "unknown_feature_builder",
    }
    with pytest.raises(ValueError, match="Bilinmeyen feature_plan"):
        execute_analysis_plan(df, plan)


def test_column_map_missing_physical_column():
    df = _minimal_df()
    plan = {
        "column_map": {
            "customer_id": "Customer ID",
            "order_date": "InvoiceDate",
            "order_id": "Invoice",
            "quantity": "Quantity",
            "unit_price": "NoSuchColumn",
        },
        "cleaning_plan": [],
        "feature_plan": "build_customer_rfm_features",
    }
    with pytest.raises(ValueError, match="bulunmayan kolonlar"):
        execute_analysis_plan(df, plan)


def test_valid_plan_executes():
    rows: list[dict] = []
    base = pd.Timestamp("2024-01-01")
    for cid in range(1, 25):
        for i in range(5):
            days = i * 20 + cid * 3
            rows.append(
                {
                    "Customer ID": cid,
                    "InvoiceDate": (base + pd.Timedelta(days=days)).strftime("%Y-%m-%d"),
                    "Invoice": f"INV-{cid}-{i}",
                    "Quantity": 1,
                    "Price": 10.0,
                }
            )
    df = pd.DataFrame(rows)
    plan = {
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
        "feature_plan": "build_customer_rfm_features",
        "options": {"churn_strategy": "quantile", "churn_quantile": 0.7, "churn_threshold_days": 90},
    }
    out = execute_analysis_plan(df, plan)
    assert "churn" in out.columns
    assert out["churn"].nunique() >= 2
    assert len(out) >= 10
