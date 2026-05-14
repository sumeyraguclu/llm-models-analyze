"""
Senkron model eğitimi: POST /analyze

Önerilen uzun koşular için: POST /plans/{plan_id}/jobs + GET /jobs/{job_id} (async).
Bu endpoint geriye dönük uyumluluk için korunur (mevcut frontend).
"""

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from database import get_db
from models import AIModel, Dataset, PlanSnapshot
from schemas.analysis_plan import AnalysisPlanSchema
from services.analysis_execution import (
    AnalysisExecutionError,
    run_analysis_training,
    validated_plan_from_snapshot_payload,
)
from services.analysis_plan_normalize import normalize_raw_analysis_plan_dict

router = APIRouter(tags=["analyze"])


class AnalyzeRequest(BaseModel):
    dataset_id: int = Field(..., gt=0)
    template: str | None = None
    column_map: dict[str, str] | None = None
    analysis_plan: dict | None = None
    plan_id: int | None = Field(None, description="Onaylı PlanSnapshot kimliği (önerilen akış).")

    @model_validator(mode="after")
    def _validate_plan_or_column_map(self):
        has_snapshot = self.plan_id is not None
        has_body_plan = self.analysis_plan is not None
        has_legacy_map = self.column_map is not None
        if has_snapshot and (has_body_plan or has_legacy_map):
            raise ValueError("plan_id ile analysis_plan veya column_map aynı istekte kullanılamaz.")
        if not has_snapshot and not has_body_plan and not has_legacy_map:
            raise ValueError("plan_id veya analysis_plan veya column_map gerekli.")
        return self


@router.post("/analyze", summary="Senkron model eğitimi (legacy + mevcut UI)")
def analyze(payload: AnalyzeRequest, db: Session = Depends(get_db)):
    try:
        validated_plan: AnalysisPlanSchema | None = None
        use_snapshot = payload.plan_id is not None

        if use_snapshot:
            snap = db.query(PlanSnapshot).filter(PlanSnapshot.id == payload.plan_id).first()
            if not snap:
                raise HTTPException(status_code=404, detail="plan_id ile eşleşen plan bulunamadı.")
            if snap.dataset_id != payload.dataset_id:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "dataset_mismatch",
                        "message": "Bu plan farklı bir datasete ait; dataset_id değerini kontrol edin.",
                    },
                )
            if snap.status != "approved":
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "plan_not_approved",
                        "message": (
                            "Bu plan henüz onaylanmadı. Önce POST /plans/<plan_id>/approve ile onaylayın "
                            "veya geliştirme amaçlı doğrudan analysis_plan gövdesi gönderin."
                        ),
                        "current_status": snap.status,
                    },
                )
            plan_raw = dict(snap.payload_json or {})
            template_name = plan_raw.get("template") or plan_raw.get("recommended_template")
            if payload.template and template_name and payload.template != template_name:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "template_mismatch",
                        "message": "Gönderilen template, onaylı plandaki şablon ile uyuşmuyor; template alanını kaldırın veya snapshot ile aynı gönderin.",
                    },
                )
            try:
                template_name, column_map, validated_plan = validated_plan_from_snapshot_payload(plan_raw)
            except AnalysisExecutionError as e:
                raise HTTPException(status_code=e.status_code, detail=e.detail) from e
        else:
            plan_raw = payload.analysis_plan or {}
            template_name = payload.template or plan_raw.get("template") or plan_raw.get("recommended_template")
            if not template_name:
                raise HTTPException(status_code=400, detail="template veya analysis_plan.recommended_template gerekli.")

            if payload.analysis_plan is not None:
                try:
                    normalized = normalize_raw_analysis_plan_dict(plan_raw)
                    validated_plan = AnalysisPlanSchema(**normalized)
                except ValidationError as e:
                    raise HTTPException(
                        status_code=422,
                        detail={"error": "Plan validasyon hatası", "detail": str(e)},
                    ) from e

                column_map = validated_plan.column_map
                if not isinstance(column_map, dict) or not column_map:
                    raise HTTPException(status_code=400, detail="analysis_plan.column_map gerekli.")
            else:
                column_map = payload.column_map
                if not isinstance(column_map, dict) or not column_map:
                    raise HTTPException(status_code=400, detail="column_map gerekli.")

        dataset = db.query(Dataset).filter(Dataset.id == payload.dataset_id).first()
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset bulunamadı.")

        model_row = AIModel(
            dataset_id=payload.dataset_id,
            template=template_name,
            column_map=column_map,
            metrics=None,
            status="running",
        )
        db.add(model_row)
        db.commit()
        db.refresh(model_row)

        try:
            return run_analysis_training(
                db,
                dataset_id=payload.dataset_id,
                template_name=template_name,
                column_map=column_map,
                validated_plan=validated_plan,
                model_row=model_row,
            )
        except AnalysisExecutionError as e:
            model_row.status = "failed"
            model_row.note = str(e.detail.get("message", str(e)))[:2000]
            db.add(model_row)
            db.commit()
            raise HTTPException(status_code=e.status_code, detail=e.detail) from e
        except HTTPException:
            raise
        except Exception as exc:
            model_row.status = "failed"
            model_row.note = str(exc)[:2000]
            db.add(model_row)
            db.commit()
            raise HTTPException(status_code=500, detail=f"Model eğitimi başarısız: {str(exc)}") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analyze hatası: {exc}") from exc
