"""Asenkron analiz job durumu ve sonuç: GET /jobs/{id}, GET /jobs/{id}/result."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from dependencies.auth import CurrentUser
from models import AIModel
from services.ownership import require_owned_job, require_owned_model

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
def get_job(job_id: int, current_user: CurrentUser, db: Session = Depends(get_db)):
    j = require_owned_job(db, current_user, job_id)
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
def get_job_result(job_id: int, current_user: CurrentUser, db: Session = Depends(get_db)):
    """Tamamlanan job için POST /analyze ile uyumlu sonuç gövdesi."""
    j = require_owned_job(db, current_user, job_id)
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
    mr = require_owned_model(db, current_user, j.result_model_run_id)
    metrics = mr.metrics if isinstance(mr.metrics, dict) else {}
    top_dw = metrics.get("data_warning") if isinstance(metrics, dict) else None
    return {
        "model_id": mr.id,
        "template": mr.template,
        "metrics": mr.metrics,
        "summary": j.result_summary,
        "data_warning": top_dw if isinstance(top_dw, str) and top_dw else None,
    }


@router.get("/{job_id}/target-list")
def get_job_target_list(job_id: int, current_user: CurrentUser, db: Session = Depends(get_db)):
    """Tamamlanan uplift işi için hedef listesi (job metrics içinden)."""
    j = require_owned_job(db, current_user, job_id)
    if j.status != "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "job_not_completed",
                "status": j.status,
                "message": "Hedef listesi yalnızca tamamlanan işler için kullanılabilir.",
            },
        )
    if not j.result_model_run_id:
        raise HTTPException(status_code=500, detail="Job tamamlandı ancak model_run_id eksik.")
    mr = require_owned_model(db, current_user, j.result_model_run_id)
    if mr.template != "uplift":
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_uplift_job",
                "message": "Hedef listesi yalnızca uplift şablonu işleri için kullanılabilir.",
            },
        )
    metrics = mr.metrics if isinstance(mr.metrics, dict) else {}
    target_list = metrics.get("target_list")
    if not isinstance(target_list, list) or not target_list:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "target_list_unavailable",
                "message": "Bu iş için hedef listesi bulunamadı.",
            },
        )
    return [
        {
            "customer_id": row.get("customer_id"),
            "uplift_score": row.get("uplift_score"),
            "action_label": row.get("action_label"),
        }
        for row in target_list
        if isinstance(row, dict)
    ]


@router.get("/{job_id}/risk-list")
def get_job_risk_list(job_id: int, current_user: CurrentUser, db: Session = Depends(get_db)):
    """Tamamlanan churn işi için risk listesi (job metrics içinden)."""
    j = require_owned_job(db, current_user, job_id)
    if j.status != "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "job_not_completed",
                "status": j.status,
                "message": "Risk listesi yalnızca tamamlanan işler için kullanılabilir.",
            },
        )
    if not j.result_model_run_id:
        raise HTTPException(status_code=500, detail="Job tamamlandı ancak model_run_id eksik.")
    mr = require_owned_model(db, current_user, j.result_model_run_id)
    if mr.template != "churn":
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_churn_job",
                "message": "Risk listesi yalnızca churn şablonu işleri için kullanılabilir.",
            },
        )
    metrics = mr.metrics if isinstance(mr.metrics, dict) else {}
    risk_list = metrics.get("risk_list")
    if not isinstance(risk_list, list) or not risk_list:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "risk_list_unavailable",
                "message": "Bu iş için risk listesi bulunamadı.",
            },
        )
    return [
        {
            "customer_id": row.get("customer_id"),
            "churn_probability": row.get("churn_probability"),
            "risk_label": row.get("risk_label"),
        }
        for row in risk_list
        if isinstance(row, dict)
    ]


@router.get("/{job_id}/segment-list")
def get_job_segment_list(job_id: int, current_user: CurrentUser, db: Session = Depends(get_db)):
    """Tamamlanan segmentasyon işi için müşteri segment listesi (job metrics içinden)."""
    j = require_owned_job(db, current_user, job_id)
    if j.status != "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "job_not_completed",
                "status": j.status,
                "message": "Segment listesi yalnızca tamamlanan işler için kullanılabilir.",
            },
        )
    if not j.result_model_run_id:
        raise HTTPException(status_code=500, detail="Job tamamlandı ancak model_run_id eksik.")
    mr = require_owned_model(db, current_user, j.result_model_run_id)
    if mr.template != "segmentasyon":
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_segmentation_job",
                "message": "Segment listesi yalnızca segmentasyon şablonu işleri için kullanılabilir.",
            },
        )
    metrics = mr.metrics if isinstance(mr.metrics, dict) else {}
    segment_list = metrics.get("segment_list")
    if not isinstance(segment_list, list) or not segment_list:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "segment_list_unavailable",
                "message": "Bu iş için segment listesi bulunamadı.",
            },
        )
    return [
        {
            "customer_id": row.get("customer_id"),
            "segment_id": row.get("segment_id"),
            "segment_name": row.get("segment_name"),
        }
        for row in segment_list
        if isinstance(row, dict)
    ]
