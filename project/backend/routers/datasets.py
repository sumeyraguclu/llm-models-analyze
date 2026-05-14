import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

import database

from database import get_db
from models import Dataset, PlanSnapshot
from services.analysis_plan_generation import generate_validated_analysis_plan
from validation.ecommerce_rules import validate_ecommerce_dataframe
from validation.quality_score import compute_quality_score

router = APIRouter(prefix="/datasets", tags=["datasets"])


class CreatePlanBody(BaseModel):
    user_goal: str | None = None


class PlanListItem(BaseModel):
    plan_id: int
    dataset_id: int
    status: str
    source: str
    template: str | None = None
    created_at: str | None = None
    approved_at: str | None = None


class PlanListResponse(BaseModel):
    dataset_id: int
    plans: list[PlanListItem]


@router.post("/{dataset_id}/plans")
def create_dataset_plan(
    dataset_id: int,
    body: CreatePlanBody | None = None,
    db: Session = Depends(get_db),
):
    """
    LLM ile analysis_plan üretir ve immutable PlanSnapshot olarak draft kaydeder.
    """
    _require_dataset(db, dataset_id)
    user_goal = body.user_goal if body else None
    plan_dump, mapping, warnings = generate_validated_analysis_plan(db, dataset_id, user_goal)

    snap = PlanSnapshot(
        dataset_id=dataset_id,
        payload_json=plan_dump,
        mapping_confidence_json=mapping,
        warnings_json=warnings,
        status="draft",
        source="llm",
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)

    return {
        "plan_id": snap.id,
        "dataset_id": dataset_id,
        "status": snap.status,
        "source": snap.source,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
        "plan": plan_dump,
        "mapping_confidence": mapping,
        "warnings": warnings,
    }


@router.get("/{dataset_id}/plans", response_model=PlanListResponse)
def list_dataset_plans(dataset_id: int, db: Session = Depends(get_db)):
    _require_dataset(db, dataset_id)
    rows = (
        db.query(PlanSnapshot)
        .filter(PlanSnapshot.dataset_id == dataset_id)
        .order_by(PlanSnapshot.created_at.desc())
        .all()
    )
    items: list[PlanListItem] = []
    for r in rows:
        payload = r.payload_json if isinstance(r.payload_json, dict) else {}
        tmpl = payload.get("template")
        items.append(
            PlanListItem(
                plan_id=r.id,
                dataset_id=r.dataset_id,
                status=r.status,
                source=r.source,
                template=str(tmpl) if tmpl is not None else None,
                created_at=r.created_at.isoformat() if r.created_at else None,
                approved_at=r.approved_at.isoformat() if r.approved_at else None,
            )
        )
    return PlanListResponse(dataset_id=dataset_id, plans=items)


def _require_dataset(db: Session, dataset_id: int) -> Dataset:
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset bulunamadı.")
    return ds


def _load_dataframe(dataset: Dataset) -> pd.DataFrame:
    query = text(f'SELECT * FROM "{dataset.table_name}"')
    return pd.read_sql_query(query, database.engine)


@router.get("/{dataset_id}/validation")
def get_dataset_validation(
    dataset_id: int,
    template: str = Query(
        "churn",
        description="Şablon kimliği (eşik ve yeterlilik metinleri buna göre): churn | segmentasyon | satis_tahmini",
    ),
    db: Session = Depends(get_db),
):
    """
    Deterministik e-ticaret işlem doğrulaması (pandas + kolon hibrit eşleştirme).
    LLM kullanılmaz; mevcut /analyze akışını değiştirmez.
    """
    dataset = _require_dataset(db, dataset_id)
    try:
        df = _load_dataframe(dataset)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Veri okunamadı: {exc}") from exc

    if df.empty:
        raise HTTPException(status_code=400, detail="Dataset tablosu boş.")

    report = validate_ecommerce_dataframe(df, template=template)
    return report.model_dump()


@router.get("/{dataset_id}/quality")
def get_dataset_quality(
    dataset_id: int,
    template: str = Query(
        "churn",
        description="Şablon kimliği (validation metrikleri buna göre hesaplanır).",
    ),
    db: Session = Depends(get_db),
):
    """0-100 kalite skoru ve alt bileşenler (validation metriklerinden türetilir)."""
    dataset = _require_dataset(db, dataset_id)
    try:
        df = _load_dataframe(dataset)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Veri okunamadı: {exc}") from exc

    if df.empty:
        raise HTTPException(status_code=400, detail="Dataset tablosu boş.")

    vr = validate_ecommerce_dataframe(df, template=template)
    quality = compute_quality_score(vr.metrics)
    return quality.model_dump()
