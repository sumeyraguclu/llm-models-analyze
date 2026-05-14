"""GET /preview/{table_name} ve GET /datasets/{id} — temel API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_preview_valid_table(client: TestClient, churn_csv_bytes: bytes):
    ing = client.post("/ingest/csv", files={"csv_file": ("c.csv", churn_csv_bytes, "text/csv")})
    assert ing.status_code == 200
    table_name = ing.json()["table_name"]
    r = client.get(f"/preview/{table_name}", params={"limit": 5})
    assert r.status_code == 200
    j = r.json()
    assert j["table_name"] == table_name
    assert j["limit"] == 5
    assert isinstance(j["rows"], list)
    assert len(j["rows"]) <= 5
    assert len(j["rows"]) >= 1


def test_preview_nonexistent_table_returns_500(client: TestClient):
    r = client.get("/preview/no_such_table_xyz_12345")
    assert r.status_code == 500
    assert "Preview" in r.json().get("detail", "") or "preview" in r.json().get("detail", "").lower()


def test_get_dataset_invalid_id_404(client: TestClient):
    r = client.get("/datasets/999999")
    assert r.status_code == 404


def test_preview_limit_validation(client: TestClient, churn_csv_bytes: bytes):
    ing = client.post("/ingest/csv", files={"csv_file": ("c2.csv", churn_csv_bytes, "text/csv")})
    table_name = ing.json()["table_name"]
    r = client.get(f"/preview/{table_name}", params={"limit": 0})
    assert r.status_code == 422
