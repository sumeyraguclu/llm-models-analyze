"""run_analysis_job hata dalları (doğrudan fonksiyon, SQLite seed)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

import database
from database import SessionLocal
from models import AIModel, AnalysisJob, Dataset, PlanSnapshot
from services import analysis_job_tasks as job_mod
from services.analysis_execution import AnalysisExecutionError


def _approved_churn_payload() -> dict:
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


def _seed_dataset_with_table(*, n_customers: int = 120) -> tuple[int, str]:
    """Dataset ORM + fizik tablo (churn ingest formatı)."""
    from uuid import uuid4

    from tests.conftest import ecommerce_tx_dataframe

    df = ecommerce_tx_dataframe(n_customers=n_customers, rows_per_customer=6)
    table = f"data_jobtest_{uuid4().hex[:10]}"
    df.to_sql(table, database.engine, if_exists="replace", index=False)
    db = SessionLocal()
    try:
        ds = Dataset(
            file_name="jobtest.csv",
            table_name=table,
            column_defs=[{"name": c, "dtype": str(t)} for c, t in df.dtypes.items()],
            column_profile=None,
        )
        db.add(ds)
        db.commit()
        db.refresh(ds)
        return ds.id, table
    finally:
        db.close()


def _seed_approved_snapshot(db, *, dataset_id: int, status: str = "approved") -> int:
    snap = PlanSnapshot(
        dataset_id=dataset_id,
        payload_json=_approved_churn_payload(),
        mapping_confidence_json={},
        warnings_json=[],
        status=status,
        source="test",
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap.id


def test_plan_not_approved_fails_job():
    dataset_id, _ = _seed_dataset_with_table()
    db = SessionLocal()
    try:
        sid = _seed_approved_snapshot(db, dataset_id=dataset_id, status="draft")
        job = AnalysisJob(dataset_id=dataset_id, plan_snapshot_id=sid, status="queued", progress=0)
        db.add(job)
        db.commit()
        db.refresh(job)
        jid = job.id
    finally:
        db.close()

    job_mod.run_analysis_job(jid)

    db = SessionLocal()
    try:
        j = db.query(AnalysisJob).filter(AnalysisJob.id == jid).one()
        assert j.status == "failed"
        assert j.error_message
        err = json.loads(j.error_message)
        assert err["error"] == "plan_not_approved"
        assert err["current_status"] == "draft"
    finally:
        db.close()


def test_dataset_mismatch_fails_job():
    d1, _ = _seed_dataset_with_table()
    d2, _ = _seed_dataset_with_table()
    db = SessionLocal()
    try:
        sid = _seed_approved_snapshot(db, dataset_id=d1, status="approved")
        job = AnalysisJob(dataset_id=d2, plan_snapshot_id=sid, status="queued", progress=0)
        db.add(job)
        db.commit()
        db.refresh(job)
        jid = job.id
    finally:
        db.close()

    job_mod.run_analysis_job(jid)

    db = SessionLocal()
    try:
        j = db.query(AnalysisJob).filter(AnalysisJob.id == jid).one()
        assert j.status == "failed"
        assert "uyuşmuyor" in (j.error_message or "")
    finally:
        db.close()


def test_missing_sql_table_fails_job(monkeypatch: pytest.MonkeyPatch):
    """Dataset satırı var ama fizik tablo yok → run_analysis_training Exception → job failed."""
    dataset_id, table = _seed_dataset_with_table()
    db = SessionLocal()
    try:
        sid = _seed_approved_snapshot(db, dataset_id=dataset_id, status="approved")
        job = AnalysisJob(dataset_id=dataset_id, plan_snapshot_id=sid, status="queued", progress=0)
        db.add(job)
        db.commit()
        db.refresh(job)
        jid = job.id
    finally:
        db.close()

    with database.engine.connect() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{table}"'))
        conn.commit()

    job_mod.run_analysis_job(jid)

    db = SessionLocal()
    try:
        j = db.query(AnalysisJob).filter(AnalysisJob.id == jid).one()
        assert j.status == "failed"
        assert j.error_message
        assert j.finished_at is not None
    finally:
        db.close()


def test_execution_analysis_execution_error_fails_job(monkeypatch: pytest.MonkeyPatch):
    dataset_id, _ = _seed_dataset_with_table()
    db = SessionLocal()
    try:
        sid = _seed_approved_snapshot(db, dataset_id=dataset_id, status="approved")
        job = AnalysisJob(dataset_id=dataset_id, plan_snapshot_id=sid, status="queued", progress=0)
        db.add(job)
        db.commit()
        db.refresh(job)
        jid = job.id
    finally:
        db.close()

    def boom(*_a, **_k):
        raise AnalysisExecutionError(
            "simulated",
            status_code=418,
            detail={"error": "simulated_failure", "message": "unit test"},
        )

    monkeypatch.setattr(job_mod, "run_analysis_training", boom)
    job_mod.run_analysis_job(jid)

    db = SessionLocal()
    try:
        j = db.query(AnalysisJob).filter(AnalysisJob.id == jid).one()
        assert j.status == "failed"
        detail = json.loads(j.error_message or "{}")
        assert detail.get("error") == "simulated_failure"
        mid = j.result_model_run_id
        if mid:
            m = db.query(AIModel).filter(AIModel.id == mid).one()
            assert m.status == "failed"
    finally:
        db.close()


def test_missing_plan_snapshot_fails_job():
    """FK olmadan job satırı (SQLite PRAGMA foreign_keys=OFF)."""
    dataset_id, _ = _seed_dataset_with_table()
    snap_id_orphan = 9_999_999
    with database.engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        result = conn.execute(
            text(
                "INSERT INTO analysis_jobs (dataset_id, plan_snapshot_id, status, progress) "
                "VALUES (:ds, :ps, 'queued', 0)"
            ),
            {"ds": dataset_id, "ps": snap_id_orphan},
        )
        jid = result.lastrowid

    assert jid is not None

    job_mod.run_analysis_job(jid)

    db = SessionLocal()
    try:
        j = db.query(AnalysisJob).filter(AnalysisJob.id == jid).one()
        assert j.status == "failed"
        assert "snapshot" in (j.error_message or "").lower()
    finally:
        db.close()
