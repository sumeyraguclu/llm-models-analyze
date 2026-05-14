"""POST /analyze legacy gövdeler: analysis_plan, column_map, hata durumları."""

from __future__ import annotations

import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient


def _approved_churn_analysis_plan() -> dict:
    return {
        "template": "churn",
        "column_map": {
            "customer_id": "Customer ID",
            "order_date": "InvoiceDate",
            "order_id": "Invoice",
            "quantity": "Quantity",
            "unit_price": "Price",
        },
        "cleaning_steps": [
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
    }


def _legacy_wide_churn_csv(n: int = 120) -> bytes:
    """Ham tabloda last_order_date / total_spent eşlemesi (legacy column_map yolu)."""
    rng = pd.date_range("2023-01-01", periods=n, freq="D")
    rows = []
    for i in range(n):
        rows.append(
            {
                "CustKey": f"C{i:04d}",
                "LastOrder": rng[i].strftime("%Y-%m-%d"),
                "Amount": float(100 + i * 10),
                "Orders": max(1, i % 7),
            }
        )
    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


@pytest.fixture
def churn_ingested(client: TestClient):
    from tests.conftest import ecommerce_tx_dataframe

    buf = io.StringIO()
    ecommerce_tx_dataframe().to_csv(buf, index=False)
    r = client.post("/ingest/csv", files={"csv_file": ("c.csv", buf.getvalue().encode(), "text/csv")})
    assert r.status_code == 200
    did = r.json()["dataset_id"]
    tn = r.json()["table_name"]
    client.post(f"/profile/{tn}")
    return did


def test_analyze_with_raw_analysis_plan(client: TestClient, churn_ingested: int):
    r = client.post(
        "/analyze",
        json={"dataset_id": churn_ingested, "analysis_plan": _approved_churn_analysis_plan()},
    )
    assert r.status_code == 200
    j = r.json()
    assert "model_id" in j and j.get("template") == "churn" and "metrics" in j


def test_analyze_with_raw_column_map_only(client: TestClient):
    raw = _legacy_wide_churn_csv(120)
    ing = client.post("/ingest/csv", files={"csv_file": ("wide.csv", raw, "text/csv")})
    assert ing.status_code == 200
    did = ing.json()["dataset_id"]
    tn = ing.json()["table_name"]
    client.post(f"/profile/{tn}")
    column_map = {
        "CustKey": "customer_id",
        "LastOrder": "last_order_date",
        "Amount": "total_spent",
        "Orders": "order_count",
    }
    r = client.post(
        "/analyze",
        json={"dataset_id": did, "template": "churn", "column_map": column_map},
    )
    assert r.status_code == 200
    assert r.json().get("template") == "churn"


def test_analyze_invalid_plan_rejected(client: TestClient, churn_ingested: int):
    bad_plan = {**_approved_churn_analysis_plan(), "template": "not_a_real_template"}
    r = client.post("/analyze", json={"dataset_id": churn_ingested, "analysis_plan": bad_plan})
    assert r.status_code == 422


def test_analyze_missing_plan_fields_rejected(client: TestClient, churn_ingested: int):
    r = client.post(
        "/analyze",
        json={"dataset_id": churn_ingested, "template": "churn"},
    )
    assert r.status_code == 422


def test_analyze_empty_body_rejected(client: TestClient):
    r = client.post("/analyze", json={})
    assert r.status_code == 422
