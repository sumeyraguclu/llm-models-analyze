"""
Analyze / async job için paylaşılan model eğitim pipeline'ı (HTTP'den bağımsız).
"""

from __future__ import annotations

import pandas as pd
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

import database
from models import AIModel, Dataset
from schemas.analysis_plan import AnalysisPlanSchema
from services.analysis_plan_normalize import normalize_raw_analysis_plan_dict
from services.plan_executor import execute_analysis_plan
from templates.registry import ensure_template_registered, get_template_spec


class AnalysisExecutionError(Exception):
    """Pipeline hatası; HTTP katmanı status_code ile map eder."""

    def __init__(self, message: str, *, status_code: int = 400, detail: dict | None = None):
        super().__init__(message)
        self.status_code = int(status_code)
        self.detail = detail if detail is not None else {"message": message}


def run_analysis_training(
    db: Session,
    *,
    dataset_id: int,
    template_name: str,
    column_map: dict,
    validated_plan: AnalysisPlanSchema | None,
    model_row: AIModel,
) -> dict:
    """
    Ham veriyi yükler, feature üretir, modeli eğitir, AIModel satırını günceller.
    Başarıda: model_row.status=completed, metrics dolu.
    Hata: AnalysisExecutionError — çağıran model_row'u failed yapmalı.
    """
    try:
        template_spec = get_template_spec(template_name)
    except ValueError as exc:
        raise AnalysisExecutionError(
            str(exc),
            status_code=400,
            detail={"error": "unknown_template", "message": str(exc)},
        ) from exc
    template_cfg = template_spec.to_execution_dict()

    if validated_plan is not None:
        try:
            template_spec.validate_plan_steps(
                list(validated_plan.cleaning_steps or []),
                list(validated_plan.feature_plan or []),
            )
        except ValueError as exc:
            raise AnalysisExecutionError(
                str(exc),
                status_code=400,
                detail={"error": "plan_steps_rejected", "message": str(exc)},
            ) from exc

    if validated_plan is None:
        required_raw = set(template_cfg.get("required_raw", template_cfg.get("required", [])))
        mapped_targets = set(column_map.values())
        missing = sorted(required_raw - mapped_targets)
        if missing:
            raise AnalysisExecutionError(
                f"Eksik zorunlu kolon eşleşmeleri: {', '.join(missing)}",
                status_code=400,
                detail={
                    "error": "validation_failed",
                    "message": "Validasyon (feature engineering öncesi) başarısız.",
                    "missing": missing,
                },
            )

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise AnalysisExecutionError("Dataset bulunamadı.", status_code=404)

    query = text(f'SELECT * FROM "{dataset.table_name}"')
    df = pd.read_sql_query(query, database.engine)

    if validated_plan is not None:
        if len(validated_plan.feature_plan) != 1:
            raise AnalysisExecutionError(
                "feature_plan şu an tek bir adım içermeli (tek feature builder).",
                status_code=422,
                detail={"error": "Plan validasyon hatası"},
            )
        try:
            executor_plan = {
                "column_map": validated_plan.column_map,
                "cleaning_plan": validated_plan.cleaning_steps,
                "feature_plan": validated_plan.feature_plan[0],
                "options": validated_plan.options.model_dump() if validated_plan.options else {},
            }
            feature_df = execute_analysis_plan(df, executor_plan)
        except Exception as exc:
            raise AnalysisExecutionError(
                f"Feature engineering (plan execution) başarısız: {exc}",
                status_code=400,
                detail={"error": "feature_engineering_failed", "message": str(exc)},
            ) from exc

        required_features = set(template_cfg.get("required_features", template_cfg.get("required", [])))
        missing_after = sorted([c for c in required_features if c not in feature_df.columns])
        if missing_after:
            raise AnalysisExecutionError(
                f"Feature DF eksik kolonlar: {', '.join(missing_after)}",
                status_code=400,
                detail={
                    "error": "validation_failed",
                    "message": "Validasyon (feature engineering sonrası) başarısız.",
                    "missing_after": missing_after,
                },
            )
    else:
        renamed_cols = ", ".join([f'"{orig}" AS "{std}"' for orig, std in column_map.items()])
        rename_query = text(f'SELECT {renamed_cols} FROM "{dataset.table_name}"')
        feature_df = pd.read_sql_query(rename_query, database.engine)

    min_required = template_spec.minimum_rows
    if min_required is not None and len(feature_df) < min_required:
        raise AnalysisExecutionError(
            f"Bu analiz için en az {min_required} müşteri gerekli, mevcut: {len(feature_df)}.",
            status_code=400,
            detail={
                "error": "insufficient_data",
                "message": (
                    f"Bu analiz için en az {min_required} müşteri gerekli, "
                    f"mevcut: {len(feature_df)}."
                ),
                "suggestion": "Daha fazla satış verisi içeren bir CSV yükleyin.",
            },
        )

    data_warning: str | None = None
    recommended = template_spec.recommended_rows
    if recommended is not None and len(feature_df) < recommended:
        data_warning = (
            f"Düşük veri uyarısı: {len(feature_df)} kayıt var, "
            f"{recommended} önerilir. "
            f"Metrikler gerçek performansı yansıtmayabilir."
        )

    pipeline = template_spec.build_pipeline(validated_plan)

    try:
        pipeline.fit(feature_df)
        metrics = pipeline.metrics(feature_df)
        summary = pipeline.summary()
    except Exception as exc:
        raise AnalysisExecutionError(
            f"Model eğitimi başarısız: {exc}",
            status_code=500,
            detail={"error": "training_failed", "message": str(exc)},
        ) from exc

    if not isinstance(metrics, dict):
        metrics = {}
    data_warning, metrics = template_spec.postprocess_metrics(
        metrics=dict(metrics),
        prior_data_warning=data_warning,
    )

    model_row.metrics = metrics
    model_row.status = "completed"
    db.add(model_row)
    db.commit()
    db.refresh(model_row)

    return {
        "model_id": model_row.id,
        "template": template_name,
        "metrics": metrics,
        "summary": summary,
        "data_warning": data_warning,
    }


def validated_plan_from_snapshot_payload(plan_raw: dict) -> tuple[str, dict, AnalysisPlanSchema]:
    """PlanSnapshot.payload_json → template, column_map, şema."""
    template_name = plan_raw.get("template") or plan_raw.get("recommended_template")
    if not template_name:
        raise AnalysisExecutionError("Planda template alanı eksik.", status_code=400)
    try:
        ensure_template_registered(str(template_name))
    except ValueError as exc:
        raise AnalysisExecutionError(
            str(exc),
            status_code=400,
            detail={"error": "unknown_template", "message": str(exc)},
        ) from exc
    try:
        normalized = normalize_raw_analysis_plan_dict(dict(plan_raw or {}))
        validated_plan = AnalysisPlanSchema(**normalized)
    except ValidationError as e:
        raise AnalysisExecutionError(
            str(e),
            status_code=422,
            detail={"error": "Plan validasyon hatası", "detail": str(e)},
        ) from e
    column_map = validated_plan.column_map
    if not isinstance(column_map, dict) or not column_map:
        raise AnalysisExecutionError("Planda column_map gerekli.", status_code=400)
    return str(template_name), column_map, validated_plan
