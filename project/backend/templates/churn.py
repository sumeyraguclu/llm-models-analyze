"""Churn şablonu — işlem tabanlı e‑ticaret + RFM feature pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cleaning.registry import CLEANING_REGISTRY
from features.registry import FEATURE_REGISTRY
from ml.churn import ChurnPipeline

from templates.base import MlTemplate

if TYPE_CHECKING:
    from schemas.analysis_plan import AnalysisPlanSchema


class ChurnTemplate(MlTemplate):
    name = "churn"
    dataset_type = "ecommerce_transactions"
    description = "Müşteri kaybı tahmini"
    metric = "accuracy"
    target = "churn"
    minimum_rows = 100
    recommended_rows = 500

    @property
    def supported_models(self) -> tuple[str, ...]:
        return ("churn_random_forest",)

    @property
    def allowed_cleaning_steps(self) -> frozenset[str] | None:
        return frozenset(CLEANING_REGISTRY.keys())

    @property
    def allowed_feature_builders(self) -> frozenset[str] | None:
        return frozenset(FEATURE_REGISTRY.keys())

    def to_execution_dict(self) -> dict[str, Any]:
        return {
            "required_raw": ["last_order_date", "total_spent"],
            "optional_raw": ["order_count", "customer_id"],
            "required_features": ["recency", "monetary"],
            "optional_features": [
                "frequency",
                "order_count",
                "total_spent",
                "avg_order_value",
                "customer_id",
                "last_order_date",
            ],
            "target": self.target,
            "model_class": ChurnPipeline,
            "metric": self.metric,
            "description": self.description,
        }

    def build_pipeline(self, validated_plan: AnalysisPlanSchema | None) -> ChurnPipeline:
        churn_days = 90
        if validated_plan is not None and validated_plan.options is not None:
            churn_days = int(validated_plan.options.churn_threshold_days)
        return ChurnPipeline(churn_days=churn_days)

    def validation_recommended_unique_customers(self) -> int:
        return 100

    def validation_recommended_tx_rows(self) -> int:
        return 500

    def _apply_domain_metric_bias(self, metrics: dict, data_warning: str | None) -> tuple[str | None, dict]:
        churn_rate = metrics.get("churn_rate") if isinstance(metrics, dict) else None
        try:
            churn_rate_f = float(churn_rate) if churn_rate is not None else None
        except Exception:
            churn_rate_f = None
        if churn_rate_f is not None:
            if churn_rate_f < 0.02:
                data_warning = "Churn oranı çok düşük (%2'nin altı). Eşik stratejisini gözden geçirin."
            elif churn_rate_f > 0.90:
                data_warning = "Churn oranı çok yüksek (%90'ın üstü). Veri kalitesini kontrol edin."
        return data_warning, metrics
