"""FastAPI: health, job lifecycle, plan onayı, validation API şeması."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


def test_health_and_ready(client: TestClient):
    h = client.get("/health")
    assert h.status_code == 200
    body = h.json()
    assert body.get("status") == "ok"
    assert "llm" in body
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json().get("status") == "ready"


def test_validation_and_quality_shapes(client: TestClient, churn_csv_bytes: bytes):
    ing = client.post("/ingest/csv", files={"csv_file": ("c.csv", churn_csv_bytes, "text/csv")})
    assert ing.status_code == 200
    body = ing.json()
    dataset_id = body["dataset_id"]
    table_name = body["table_name"]
    client.post(f"/profile/{table_name}")
    v = client.get(f"/datasets/{dataset_id}/validation")
    assert v.status_code == 200
    data = v.json()
    assert "is_valid" in data and "errors" in data and "metrics" in data
    q = client.get(f"/datasets/{dataset_id}/quality")
    assert q.status_code == 200
    qj = q.json()
    assert "overall_score" in qj and "level" in qj and "breakdown" in qj


def test_job_rejected_when_plan_not_approved(client: TestClient, churn_csv_bytes: bytes):
    ing = client.post("/ingest/csv", files={"csv_file": ("c.csv", churn_csv_bytes, "text/csv")})
    dataset_id = ing.json()["dataset_id"]
    table_name = ing.json()["table_name"]
    client.post(f"/profile/{table_name}")
    pr = client.post(f"/datasets/{dataset_id}/plans", json={})
    assert pr.status_code == 200
    plan_id = pr.json()["plan_id"]
    jr = client.post(f"/plans/{plan_id}/jobs", json={"dataset_id": dataset_id})
    assert jr.status_code == 400
    assert jr.json()["detail"]["error"] == "plan_not_approved"


def test_job_rejects_mismatched_dataset_id(client: TestClient, churn_csv_bytes: bytes):
    ing = client.post("/ingest/csv", files={"csv_file": ("c.csv", churn_csv_bytes, "text/csv")})
    dataset_id = ing.json()["dataset_id"]
    table_name = ing.json()["table_name"]
    client.post(f"/profile/{table_name}")
    pr = client.post(f"/datasets/{dataset_id}/plans", json={})
    plan_id = pr.json()["plan_id"]
    client.post(f"/plans/{plan_id}/approve")
    jr = client.post(f"/plans/{plan_id}/jobs", json={"dataset_id": 99999})
    assert jr.status_code == 400
    assert jr.json()["detail"]["error"] == "dataset_mismatch"


@pytest.mark.integration
def test_job_lifecycle_completes_and_result_schema(client: TestClient, churn_csv_bytes: bytes):
    ing = client.post("/ingest/csv", files={"csv_file": ("c.csv", churn_csv_bytes, "text/csv")})
    assert ing.status_code == 200
    dataset_id = ing.json()["dataset_id"]
    table_name = ing.json()["table_name"]
    pf = client.post(f"/profile/{table_name}")
    assert pf.status_code == 200
    pr = client.post(f"/datasets/{dataset_id}/plans", json={})
    assert pr.status_code == 200
    plan_id = pr.json()["plan_id"]
    ap = client.post(f"/plans/{plan_id}/approve")
    assert ap.status_code == 200
    jr = client.post(f"/plans/{plan_id}/jobs", json={"dataset_id": dataset_id})
    assert jr.status_code == 200
    job_id = jr.json()["job_id"]
    assert jr.json()["status"] == "queued"
    st = client.get(f"/jobs/{job_id}")
    assert st.status_code == 200
    sj = st.json()
    assert set(sj.keys()) >= {
        "job_id",
        "dataset_id",
        "plan_snapshot_id",
        "status",
        "progress",
        "result_model_run_id",
        "error_message",
        "created_at",
        "started_at",
        "finished_at",
    }
    assert sj["status"] in ("queued", "running", "completed", "failed")
    # BackgroundTasks: genelde aynı istek içinde tamamlanır
    if sj["status"] != "completed":
        for _ in range(50):
            sj = client.get(f"/jobs/{job_id}").json()
            if sj["status"] in ("completed", "failed"):
                break
    assert sj["status"] == "completed", sj
    rs = client.get(f"/jobs/{job_id}/result")
    assert rs.status_code == 200
    rj = rs.json()
    assert set(rj.keys()) == {"model_id", "template", "metrics", "summary", "data_warning"}
    assert rj["template"] == "churn"
    assert isinstance(rj["metrics"], dict)
    assert "accuracy" in rj["metrics"]


def test_analyze_sync_still_works(client: TestClient, churn_csv_bytes: bytes):
    ing = client.post("/ingest/csv", files={"csv_file": ("c.csv", churn_csv_bytes, "text/csv")})
    dataset_id = ing.json()["dataset_id"]
    table_name = ing.json()["table_name"]
    client.post(f"/profile/{table_name}")
    pr = client.post(f"/datasets/{dataset_id}/plans", json={})
    plan_id = pr.json()["plan_id"]
    client.post(f"/plans/{plan_id}/approve")
    ar = client.post(
        "/analyze",
        json={"dataset_id": dataset_id, "plan_id": plan_id},
    )
    assert ar.status_code == 200
    aj = ar.json()
    assert "model_id" in aj and "metrics" in aj
