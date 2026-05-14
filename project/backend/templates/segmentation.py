"""Müşteri segmentasyonu şablonu (mevcut SegmentationPipeline)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cleaning.registry import CLEANING_REGISTRY
from features.registry import FEATURE_REGISTRY
from ml.segmentation import SegmentationPipeline

from templates.base import MlTemplate

if TYPE_CHECKING:
    from schemas.analysis_plan import AnalysisPlanSchema


class SegmentationTemplate(MlTemplate):
    name = "segmentasyon"
    dataset_type = "ecommerce_customer_features"
    description = "Müşteri segmentasyonu"
    metric = "silhouette"
    target = None
    minimum_rows = 30
    recommended_rows = 100

    @property
    def supported_models(self) -> tuple[str, ...]:
        return ("kmeans_silhouette",)

    @property
    def allowed_cleaning_steps(self) -> frozenset[str] | None:
        return frozenset(CLEANING_REGISTRY.keys())

    @property
    def allowed_feature_builders(self) -> frozenset[str] | None:
        return frozenset(FEATURE_REGISTRY.keys())

    def to_execution_dict(self) -> dict[str, Any]:
        return {
            "required": ["total_spent", "order_count"],
            "optional": ["last_order_date"],
            "required_raw": ["total_spent", "order_count"],
            "optional_raw": ["last_order_date", "customer_id"],
            "required_features": ["monetary", "frequency"],
            "optional_features": ["recency", "customer_id", "last_order_date"],
            "target": None,
            "model_class": SegmentationPipeline,
            "metric": self.metric,
            "description": self.description,
        }

    def build_pipeline(self, validated_plan: AnalysisPlanSchema | None) -> SegmentationPipeline:
        return SegmentationPipeline()

    def validation_recommended_unique_customers(self) -> int:
        return 30

    def validation_recommended_tx_rows(self) -> int:
        return 100
