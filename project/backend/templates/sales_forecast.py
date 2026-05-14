"""Satış / gelir tahmini şablonu (mevcut SalesForecastPipeline)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cleaning.registry import CLEANING_REGISTRY
from features.registry import FEATURE_REGISTRY
from ml.sales_forecast import SalesForecastPipeline

from templates.base import MlTemplate

if TYPE_CHECKING:
    from schemas.analysis_plan import AnalysisPlanSchema


class SalesForecastTemplate(MlTemplate):
    name = "satis_tahmini"
    dataset_type = "ecommerce_time_series"
    description = "Satış geliri tahmini"
    metric = "rmse"
    target = "revenue"
    minimum_rows = 50
    recommended_rows = 200

    @property
    def supported_models(self) -> tuple[str, ...]:
        return ("forecast_baseline",)

    @property
    def allowed_cleaning_steps(self) -> frozenset[str] | None:
        return frozenset(CLEANING_REGISTRY.keys())

    @property
    def allowed_feature_builders(self) -> frozenset[str] | None:
        return frozenset(FEATURE_REGISTRY.keys())

    def to_execution_dict(self) -> dict[str, Any]:
        return {
            "required": ["date", "quantity", "price"],
            "optional": ["category"],
            "required_raw": ["date", "quantity", "price"],
            "optional_raw": ["category", "customer_id"],
            "required_features": ["date", "quantity", "price"],
            "optional_features": ["category"],
            "target": "revenue",
            "model_class": SalesForecastPipeline,
            "metric": self.metric,
            "description": self.description,
        }

    def build_pipeline(self, validated_plan: AnalysisPlanSchema | None) -> SalesForecastPipeline:
        return SalesForecastPipeline()

    def validation_recommended_unique_customers(self) -> int:
        return 5

    def validation_recommended_tx_rows(self) -> int:
        return 200

    def compute_training_data_sufficient(
        self,
        *,
        is_valid: bool,
        estimated_customer_count: int,
        row_count: int,
    ) -> bool:
        """Tarih serisi için satır hacmine öncelik."""
        if not is_valid:
            return False
        return row_count >= self.validation_recommended_tx_rows()
