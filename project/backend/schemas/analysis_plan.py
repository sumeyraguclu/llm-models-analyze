from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, field_validator, model_validator
from typing_extensions import Self

from cleaning.registry import CLEANING_REGISTRY
from features.registry import FEATURE_REGISTRY
from templates.registry import list_template_names

VALID_TEMPLATES = list(list_template_names())
VALID_CHURN_STRATEGIES = ["fixed_days", "quantile"]
UPLIFT_REQUIRED_COLUMN_MAP = ("customer_id", "treatment", "outcome")


class ChurnOptions(BaseModel):
    churn_strategy: Literal["fixed_days", "quantile"] = "fixed_days"
    churn_threshold_days: int = 90
    churn_quantile: float = 0.70

    @field_validator("churn_threshold_days")
    @classmethod
    def threshold_positive(cls, v: int):
        if v < 1 or v > 3650:
            raise ValueError("churn_threshold_days 1-3650 arasında olmalı")
        return v

    @field_validator("churn_quantile")
    @classmethod
    def quantile_range(cls, v: float):
        if v < 0.5 or v > 0.95:
            raise ValueError("churn_quantile 0.5-0.95 arasında olmalı")
        return v


class UpliftOptions(BaseModel):
    treatment_positive_value: int | float = 1
    outcome_positive_value: int | float = 1
    min_group_size: int = 50
    min_outcome_rate: float = 0.01
    model_type: Literal["t_learner", "two_model_uplift"] = "t_learner"

    @field_validator("min_group_size")
    @classmethod
    def min_group_positive(cls, v: int):
        if v < 1:
            raise ValueError("min_group_size en az 1 olmalı")
        return v

    @field_validator("min_outcome_rate")
    @classmethod
    def min_rate_range(cls, v: float):
        if v < 0.0 or v > 1.0:
            raise ValueError("min_outcome_rate 0.0-1.0 arasında olmalı")
        return v


class AnalysisPlanSchema(BaseModel):
    template: str
    column_map: dict[str, str]
    cleaning_steps: list[str] = []
    feature_plan: list[str] = []
    options: Optional[Union[ChurnOptions, UpliftOptions]] = None
    reasoning: Optional[str] = None
    dataset_type: Optional[str] = None
    confidence: float = 0.0
    requires_user_confirmation: bool = True
    missing_required_columns: list[str] = []
    warnings: list[str] = []

    @field_validator("template")
    @classmethod
    def valid_template(cls, v: str):
        if v not in VALID_TEMPLATES:
            raise ValueError(f"Geçersiz template: {v}. Geçerliler: {VALID_TEMPLATES}")
        return v

    @field_validator("column_map")
    @classmethod
    def column_map_values_non_empty_strings(cls, v: dict[str, str]):
        for k, val in v.items():
            if not isinstance(val, str) or not val.strip():
                raise ValueError(f"column_map değeri boş olamaz: {k!r}")
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, v: float):
        if v < 0.0 or v > 1.0:
            raise ValueError("confidence 0.0-1.0 arasında olmalı")
        return v

    @field_validator("missing_required_columns", "warnings")
    @classmethod
    def string_lists(cls, v: list[str]):
        out = [s.strip() for s in v if isinstance(s, str) and s.strip()]
        return out

    @field_validator("cleaning_steps")
    @classmethod
    def valid_cleaning_steps(cls, v: list[str]):
        unknown = [s for s in v if s not in CLEANING_REGISTRY]
        if unknown:
            raise ValueError(
                f"Bilinmeyen cleaning step'ler: {unknown}. Geçerliler: {list(CLEANING_REGISTRY.keys())}"
            )
        return v

    @model_validator(mode="after")
    def feature_plan_by_template(self) -> Self:
        if self.template == "uplift":
            unknown = [f for f in self.feature_plan if f not in FEATURE_REGISTRY]
            if unknown:
                raise ValueError(
                    f"Bilinmeyen feature plan: {unknown}. Geçerli: build_uplift_customer_features"
                )
            if len(self.feature_plan) > 1:
                raise ValueError("uplift feature_plan en fazla 1 adım içerebilir")
            if len(self.feature_plan) == 1 and self.feature_plan[0] != "build_uplift_customer_features":
                raise ValueError("uplift feature_plan: build_uplift_customer_features olmalı")
            return self

        unknown = [f for f in self.feature_plan if f not in FEATURE_REGISTRY]
        if unknown:
            raise ValueError(
                f"Bilinmeyen feature plan adımları: {unknown}. Geçerliler: {list(FEATURE_REGISTRY.keys())}"
            )
        if len(self.feature_plan) > 1:
            raise ValueError("feature_plan şimdilik en fazla 1 adım içerebilir")
        return self

    @model_validator(mode="after")
    def options_required_for_template(self) -> Self:
        if self.template == "churn" and self.options is None:
            self.options = ChurnOptions()
        if self.template == "uplift":
            if self.options is None:
                self.options = UpliftOptions()
            elif isinstance(self.options, dict):
                self.options = UpliftOptions.model_validate(self.options)
            elif not isinstance(self.options, UpliftOptions):
                self.options = UpliftOptions.model_validate(
                    self.options.model_dump() if hasattr(self.options, "model_dump") else self.options
                )
            if not self.feature_plan:
                self.feature_plan = ["build_uplift_customer_features"]
        return self

    @model_validator(mode="after")
    def uplift_required_column_map(self) -> Self:
        if self.template != "uplift":
            return self
        if self.missing_required_columns:
            return self
        missing = [
            k
            for k in UPLIFT_REQUIRED_COLUMN_MAP
            if k not in self.column_map or not str(self.column_map.get(k, "")).strip()
        ]
        if missing:
            raise ValueError(
                f"uplift column_map eksik zorunlu alanlar: {missing}. "
                "Eksikse missing_required_columns kullanın."
            )
        return self

    @model_validator(mode="after")
    def column_map_or_missing_report(self) -> Self:
        if not self.column_map and not self.missing_required_columns:
            raise ValueError(
                "column_map boşsa eksik zorunlu kolonları missing_required_columns içinde bildir"
            )
        return self
