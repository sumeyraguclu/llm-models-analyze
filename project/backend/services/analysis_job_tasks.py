"""
Onaylı plan ile asenkron analiz job'ı (FastAPI BackgroundTasks).
Her task kendi DB oturumu açar (request oturumu kapanır).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from database import SessionLocal
from models import AIModel, AnalysisJob, PlanSnapshot
from services.analysis_execution import (
    AnalysisExecutionError,
    run_analysis_training,
    validated_plan_from_snapshot_payload,
)

logger = logging.getLogger(__name__)


def _log_job(job_id: int, dataset_id: int, plan_snapshot_id: int, status: str, progress: int | None = None) -> None:
    msg = "analysis_job transition job_id=%s dataset_id=%s plan_id=%s status=%s"
    args: list[object] = [job_id, dataset_id, plan_snapshot_id, status]
    if progress is not None:
        msg += " progress=%s"
        args.append(progress)
    logger.info(msg, *args)


def _fail_job(db: Session, job: AnalysisJob, message: str, model_row: AIModel | None = None) -> None:
    job.status = "failed"
    job.error_message = message[:4000]
    job.finished_at = datetime.now(timezone.utc)
    db.add(job)
    if model_row is not None and getattr(model_row, "id", None):
        mr = db.query(AIModel).filter(AIModel.id == model_row.id).first()
        if mr is not None and mr.status == "running":
            mr.status = "failed"
            mr.note = message[:2000]
            db.add(mr)
    db.commit()
    _log_job(job.id, job.dataset_id, job.plan_snapshot_id, "failed", job.progress)


def run_analysis_job(job_id: int) -> None:
    db: Session = SessionLocal()
    job: AnalysisJob | None = None
    model_row: AIModel | None = None
    try:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            logger.warning("analysis_job missing job_id=%s", job_id)
            return

        snap = db.query(PlanSnapshot).filter(PlanSnapshot.id == job.plan_snapshot_id).first()
        if not snap:
            _fail_job(db, job, "Plan snapshot bulunamadı.")
            return
        if snap.dataset_id != job.dataset_id:
            _fail_job(db, job, "Job dataset_id plan ile uyuşmuyor.")
            return
        if snap.status != "approved":
            _fail_job(
                db,
                job,
                json.dumps(
                    {"error": "plan_not_approved", "current_status": snap.status},
                    ensure_ascii=False,
                ),
            )
            return

        try:
            _, column_map, validated_plan = validated_plan_from_snapshot_payload(dict(snap.payload_json or {}))
        except AnalysisExecutionError as exc:
            _fail_job(db, job, json.dumps(exc.detail, ensure_ascii=False))
            return

        _log_job(job.id, job.dataset_id, job.plan_snapshot_id, "running", 5)
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.progress = 5
        job.error_message = None
        db.add(job)
        db.commit()

        template_name = str(validated_plan.template)

        job.progress = 20
        db.add(job)
        db.commit()

        model_row = AIModel(
            dataset_id=job.dataset_id,
            template=template_name,
            column_map=column_map,
            metrics=None,
            status="running",
        )
        db.add(model_row)
        db.commit()
        db.refresh(model_row)

        job.progress = 40
        db.add(job)
        db.commit()

        result = run_analysis_training(
            db,
            dataset_id=job.dataset_id,
            template_name=template_name,
            column_map=column_map,
            validated_plan=validated_plan,
            model_row=model_row,
        )

        job.progress = 100
        job.status = "completed"
        job.result_model_run_id = model_row.id
        _sum = result.get("summary")
        job.result_summary = _sum[:8000] if isinstance(_sum, str) else None
        job.finished_at = datetime.now(timezone.utc)
        job.error_message = None
        db.add(job)
        db.commit()
        _log_job(job.id, job.dataset_id, job.plan_snapshot_id, "completed", 100)

    except AnalysisExecutionError as exc:
        if job is not None:
            _fail_job(db, job, json.dumps(exc.detail, ensure_ascii=False), model_row)
        logger.exception("analysis_job AnalysisExecutionError job_id=%s", job_id)
    except Exception as exc:
        if job is not None:
            _fail_job(db, job, str(exc), model_row)
        logger.exception("analysis_job unexpected error job_id=%s", job_id)
    finally:
        db.close()
