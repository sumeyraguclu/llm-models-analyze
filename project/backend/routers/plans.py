"""Onaylanabilir plan anlık görüntüleri: GET /plans/{id}, POST /plans/{id}/approve, POST /plans/{id}/jobs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import AnalysisJob, Dataset, PlanSnapshot
from services.analysis_job_tasks import run_analysis_job

router = APIRouter(prefix="/plans", tags=["plans"])
logger = logging.getLogger(__name__)


class PlanSnapshotDetailResponse(BaseModel):
    id: int
    dataset_id: int
    status: str
    source: str
    created_at: datetime | None = None
    approved_at: datetime | None = None
    plan: dict = Field(description="Onaylanmış analysis_plan payload (immutable kopya)")
    mapping_confidence: dict | None = None
    warnings: list[str] = Field(default_factory=list)


@router.get("/{plan_id}", response_model=PlanSnapshotDetailResponse)
def get_plan_snapshot(plan_id: int, db: Session = Depends(get_db)):
    snap = db.query(PlanSnapshot).filter(PlanSnapshot.id == plan_id).first()
    if not snap:
        raise HTTPException(status_code=404, detail="Plan bulunamadı.")
    return PlanSnapshotDetailResponse(
        id=snap.id,
        dataset_id=snap.dataset_id,
        status=snap.status,
        source=snap.source,
        created_at=snap.created_at,
        approved_at=snap.approved_at,
        plan=dict(snap.payload_json or {}),
        mapping_confidence=dict(snap.mapping_confidence_json or {}) if snap.mapping_confidence_json else None,
        warnings=list(snap.warnings_json or []) if isinstance(snap.warnings_json, list) else [],
    )


@router.post("/{plan_id}/approve")
def approve_plan_snapshot(plan_id: int, db: Session = Depends(get_db)):
    snap = db.query(PlanSnapshot).filter(PlanSnapshot.id == plan_id).first()
    if not snap:
        raise HTTPException(status_code=404, detail="Plan bulunamadı.")
    if snap.status == "approved":
        return {
            "plan_id": snap.id,
            "status": snap.status,
            "approved_at": snap.approved_at.isoformat() if snap.approved_at else None,
            "message": "Plan zaten onaylı.",
        }
    if snap.status == "rejected":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "plan_rejected",
                "message": "Reddedilmiş plan yeniden onaylanamaz; yeni plan oluşturun.",
            },
        )

    snap.status = "approved"
    snap.approved_at = datetime.now(timezone.utc)
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return {
        "plan_id": snap.id,
        "status": snap.status,
        "approved_at": snap.approved_at.isoformat() if snap.approved_at else None,
    }


@router.post("/{plan_id}/reject")
def reject_plan_snapshot(plan_id: int, db: Session = Depends(get_db)):
    """Taslak planı reddet (immutable snapshot silinmez)."""
    snap = db.query(PlanSnapshot).filter(PlanSnapshot.id == plan_id).first()
    if not snap:
        raise HTTPException(status_code=404, detail="Plan bulunamadı.")
    if snap.status != "draft":
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_status", "message": f"Sadece draft reddedilebilir (mevcut: {snap.status})."},
        )
    snap.status = "rejected"
    db.add(snap)
    db.commit()
    return {"plan_id": snap.id, "status": snap.status}


class CreateAnalysisJobRequest(BaseModel):
    dataset_id: int = Field(..., gt=0, description="Job'un çalışacağı dataset (plan ile eşleşmeli).")


class CreateAnalysisJobResponse(BaseModel):
    job_id: int
    dataset_id: int
    plan_snapshot_id: int
    status: str


@router.post("/{plan_id}/jobs", response_model=CreateAnalysisJobResponse)
def create_analysis_job(
    plan_id: int,
    body: CreateAnalysisJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Onaylı plan için arka planda model eğitimi başlatır; hemen job_id döner."""
    snap = db.query(PlanSnapshot).filter(PlanSnapshot.id == plan_id).first()
    if not snap:
        raise HTTPException(status_code=404, detail="Plan bulunamadı.")
    if snap.dataset_id != body.dataset_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "dataset_mismatch",
                "message": "dataset_id bu planın dataset_id değeri ile aynı olmalı.",
                "expected_dataset_id": snap.dataset_id,
            },
        )
    if snap.status != "approved":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "plan_not_approved",
                "message": "Sadece onaylı planlar için job oluşturulabilir.",
                "current_status": snap.status,
            },
        )
    ds = db.query(Dataset).filter(Dataset.id == body.dataset_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset bulunamadı.")

    job = AnalysisJob(
        dataset_id=body.dataset_id,
        plan_snapshot_id=snap.id,
        status="queued",
        progress=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info(
        "analysis_job transition job_id=%s dataset_id=%s plan_id=%s status=queued",
        job.id,
        job.dataset_id,
        plan_id,
    )
    background_tasks.add_task(run_analysis_job, job.id)
    return CreateAnalysisJobResponse(
        job_id=job.id,
        dataset_id=job.dataset_id,
        plan_snapshot_id=job.plan_snapshot_id,
        status=job.status,
    )
