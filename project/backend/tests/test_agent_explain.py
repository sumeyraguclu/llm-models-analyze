"""Agent explain: call_llm monkeypatch — şema doğrulama."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


def test_explain_malformed_json_returns_500(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    import routers.agent as agent_mod

    monkeypatch.setattr(agent_mod, "call_llm", lambda *_a, **_k: "not json {{{")

    from database import SessionLocal
    from models import AIModel, Dataset

    db = SessionLocal()
    try:
        ds = Dataset(
            file_name="f.csv",
            table_name="tbl_x",
            column_defs=[],
            column_profile={"columns": [{"name": "Customer ID"}]},
        )
        db.add(ds)
        db.commit()
        db.refresh(ds)
        m = AIModel(
            dataset_id=ds.id,
            template="churn",
            column_map={"customer_id": "Customer ID"},
            metrics={"accuracy": 0.81},
            status="completed",
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        mid = m.id
    finally:
        db.close()

    r = client.post("/agent/explain", json={"model_id": mid})
    assert r.status_code == 500
    assert "JSON" in r.json()["detail"] or "json" in r.json()["detail"].lower()


def test_explain_success_with_fake_llm_json(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    import routers.agent as agent_mod

    payload = {
        "summary": "Özet.",
        "key_findings": ["a", "b"],
        "recommended_actions": ["c"],
        "caveats": ["d"],
    }
    monkeypatch.setattr(agent_mod, "call_llm", lambda *_a, **_k: json.dumps(payload, ensure_ascii=False))

    from database import SessionLocal
    from models import AIModel, Dataset

    db = SessionLocal()
    try:
        ds = Dataset(
            file_name="f2.csv",
            table_name="tbl_y",
            column_defs=[],
            column_profile={"columns": [{"name": "Customer ID"}]},
        )
        db.add(ds)
        db.commit()
        db.refresh(ds)
        m = AIModel(
            dataset_id=ds.id,
            template="churn",
            column_map={"customer_id": "Customer ID"},
            metrics={"accuracy": 0.81, "f1": 0.5},
            status="completed",
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        mid = m.id
    finally:
        db.close()

    r = client.post("/agent/explain", json={"model_id": mid})
    assert r.status_code == 200
    j = r.json()
    assert j["summary"] == "Özet."
    assert len(j["key_findings"]) == 2
