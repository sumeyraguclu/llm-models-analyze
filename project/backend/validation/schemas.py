from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ValidationMetrics(BaseModel):
    row_count: int = Field(..., ge=0)
    estimated_customer_count: int = Field(0, ge=0)
    date_parse_rate: float = Field(0.0, ge=0.0, le=1.0)
    null_customer_id_rate: float = Field(0.0, ge=0.0, le=1.0)
    negative_quantity_rate: float = Field(0.0, ge=0.0, le=1.0)
    non_positive_price_rate: float = Field(0.0, ge=0.0, le=1.0)
    duplicate_rate: float = Field(0.0, ge=0.0, le=1.0)
    history_days: int | None = Field(None, ge=0)
    transactions_per_customer: float | None = Field(None, ge=0.0)
    zero_quantity_rate: float = Field(0.0, ge=0.0, le=1.0)
    churn_data_sufficient: bool = Field(
        False,
        description="Churn şablonu için kabaca yeterli benzersiz müşteri ve satır hacmi (öneri eşiği).",
    )


class UpliftValidationMetrics(ValidationMetrics):
    """Uplift şablonu validation metrikleri (churn alanları varsayılan 0)."""

    treatment_parse_rate: float = Field(0.0, ge=0.0, le=1.0)
    outcome_parse_rate: float = Field(0.0, ge=0.0, le=1.0)
    treatment_group_count: int = Field(0, ge=0)
    treatment_group_size: int = Field(0, ge=0)
    control_group_size: int = Field(0, ge=0)
    outcome_rate: float = Field(0.0, ge=0.0, le=1.0)
    event_date_parse_rate: float = Field(0.0, ge=0.0, le=1.0)
    optional_features_matched: int = Field(0, ge=0)
    uplift_data_sufficient: bool = Field(
        False,
        description="Uplift için kabaca yeterli satır ve grup dengesi (öneri eşiği).",
    )


class ValidationReport(BaseModel):
    is_valid: bool
    errors: list[str]
    warnings: list[str]
    metrics: ValidationMetrics
    resolved_columns: dict[str, str | None] = Field(
        default_factory=dict,
        description="Hibrit eşleştirici ile çözülen standart kolon adları (CSV başlığı).",
    )


class QualityBreakdown(BaseModel):
    identity_quality: float = Field(..., ge=0.0, le=100.0)
    date_quality: float | None = Field(None, ge=0.0, le=100.0)
    transaction_quality: float | None = Field(None, ge=0.0, le=100.0)
    customer_depth: float | None = Field(None, ge=0.0, le=100.0)
    duplicate_quality: float | None = Field(None, ge=0.0, le=100.0)
    distribution_sanity: float | None = Field(None, ge=0.0, le=100.0)
    treatment_quality: float | None = Field(None, ge=0.0, le=100.0)
    outcome_quality: float | None = Field(None, ge=0.0, le=100.0)
    group_balance: float | None = Field(None, ge=0.0, le=100.0)
    optional_feature_quality: float | None = Field(None, ge=0.0, le=100.0)


class QualityScoreResponse(BaseModel):
    overall_score: float = Field(..., ge=0.0, le=100.0)
    level: Literal["good", "warning", "poor"]
    breakdown: QualityBreakdown
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "identity_quality": 0.25,
            "date_quality": 0.25,
            "transaction_quality": 0.20,
            "customer_depth": 0.15,
            "duplicate_quality": 0.10,
            "distribution_sanity": 0.05,
        }
    )
