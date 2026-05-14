"""Asenkron analiz job durumu ve sonuç: GET /jobs/{id}, GET /jobs/{id}/result."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import AIModel, AnalysisJob

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobStatusResponse(BaseModel):
    job_id: int
    dataset_id: int
    plan_snapshot_id: int = Field(description="Plan snapshot kimliği (URL'deki plan_id ile aynı)")
    status: str
    progress: int
    result_model_run_id: int | None = None
    error_message: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    j = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
    if not j:
        raise HTTPException(status_code=404, detail="Job bulunamadı.")
    return JobStatusResponse(
        job_id=j.id,
        dataset_id=j.dataset_id,
        plan_snapshot_id=j.plan_snapshot_id,
        status=j.status,
        progress=j.progress,
        result_model_run_id=j.result_model_run_id,
        error_message=j.error_message,
        created_at=_iso(j.created_at),
        started_at=_iso(j.started_at),
        finished_at=_iso(j.finished_at),
    )


@router.get("/{job_id}/result")
def get_job_result(job_id: int, db: Session = Depends(get_db)):
    """Tamamlanan job için POST /analyze ile uyumlu sonuç gövdesi."""
    j = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
    if not j:
        raise HTTPException(status_code=404, detail="Job bulunamadı.")
    if j.status == "failed":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "job_failed",
                "message": "İş başarısız oldu.",
                "error_message": j.error_message,
            },
        )
    if j.status != "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "job_not_completed",
                "status": j.status,
                "progress": j.progress,
                "message": "Sonuç henüz hazır değil; GET /jobs/{job_id} ile durumu izleyin.",
            },
        )
    if not j.result_model_run_id:
        raise HTTPException(status_code=500, detail="Job tamamlandı ancak model_run_id eksik.")
    mr = db.query(AIModel).filter(AIModel.id == j.result_model_run_id).first()
    if not mr:
        raise HTTPException(status_code=404, detail="Model kaydı bulunamadı.")
    metrics = mr.metrics if isinstance(mr.metrics, dict) else {}
    top_dw = metrics.get("data_warning") if isinstance(metrics, dict) else None
    return {
        "model_id": mr.id,
        "template": mr.template,
        "metrics": mr.metrics,
        "summary": j.result_summary,
        "data_warning": top_dw if isinstance(top_dw, str) and top_dw else None,
    }
