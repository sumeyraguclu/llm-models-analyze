"""
Bir ML şablonunun backend sözleşmesi.

Gerçek sınıflar bu soyutlamayı doldurur; `to_execution_dict()` mevcut
`run_analysis_training` ile uyumlu sözlük üretir.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from schemas.analysis_plan import AnalysisPlanSchema


class MlTemplate(ABC):
    """Tek şablon tanımı: veri beklentisi, executor sınırları, ML instantiation."""

    name: str
    dataset_type: str
    description: str
    metric: str
    target: str | None

    minimum_rows: int | None
    recommended_rows: int | None

    @property
    @abstractmethod
    def supported_models(self) -> tuple[str, ...]:
        """İleride çoklu model ailesi; şimdilik tek pipeline."""
        ...

    @abstractmethod
    def to_execution_dict(self) -> dict[str, Any]:
        """Eski `ml.templates.TEMPLATES[n]` ile aynı anahtarlar."""
        ...

    @abstractmethod
    def build_pipeline(self, validated_plan: AnalysisPlanSchema | None) -> Any:
        """Eğitim/metrics için pipeline örneği."""
        ...

    def validate_plan_steps(self, cleaning_steps: list[str], feature_plan: list[str]) -> None:
        """Şablona izin verilen cleaning/feature adımlarını kontrol et (varsayılan: tüm kayıtlı)."""
        allowed_c = self.allowed_cleaning_steps
        allowed_f = self.allowed_feature_builders
        if allowed_c is not None:
            unknown = [s for s in cleaning_steps if s not in allowed_c]
            if unknown:
                raise ValueError(
                    f"Bilinmeyen veya bu şablon için izin verilmeyen cleaning step: {unknown}. "
                    f"İzinliler: {sorted(allowed_c)}"
                )
        if allowed_f is not None:
            unk_f = [f for f in feature_plan if f not in allowed_f]
            if unk_f:
                raise ValueError(
                    f"Bilinmeyen veya bu şablon için izin verilmeyen feature_plan: {unk_f}. "
                    f"İzinliler: {sorted(allowed_f)}"
                )

    @property
    def allowed_cleaning_steps(self) -> frozenset[str] | None:
        """None = yalnızca global registry kuralları (legacy)."""
        return None

    @property
    def allowed_feature_builders(self) -> frozenset[str] | None:
        return None

    def postprocess_metrics(
        self,
        *,
        metrics: dict,
        prior_data_warning: str | None,
    ) -> tuple[str | None, dict]:
        """
        Metrik dict üzerinde şablona özel uyarı birleştirmesi (churn oranı vb.).
        Dönüş: (üst seviye data_warning, güncellenmiş metrics).
        """
        data_warning = prior_data_warning
        data_warning, metrics = self._apply_domain_metric_bias(metrics, data_warning)
        if isinstance(metrics, dict):
            parts: list[str] = []
            if data_warning:
                parts.append(data_warning)
            mlw = metrics.get("metric_warnings")
            if isinstance(mlw, list) and mlw:
                parts.append("ML güven: " + " | ".join(str(x) for x in mlw[:6]))
            metrics["data_warning"] = " ".join(parts) if parts else None
        return data_warning, metrics

    def _apply_domain_metric_bias(self, metrics: dict, data_warning: str | None) -> tuple[str | None, dict]:
        """Alt sınıflar (churn) domain-spesifik üst uyarıyı ayarlar."""
        return data_warning, metrics

    def validation_recommended_unique_customers(self) -> int:
        """GET validation içi öneri eşiği."""
        return 100

    def validation_recommended_tx_rows(self) -> int:
        return 500

    def compute_training_data_sufficient(
        self,
        *,
        is_valid: bool,
        estimated_customer_count: int,
        row_count: int,
    ) -> bool:
        """ValidationMetrics içindeki `churn_data_sufficient` doldurma (API adı geriye dönük)."""
        if not is_valid:
            return False
        return (
            estimated_customer_count >= self.validation_recommended_unique_customers()
            and row_count >= self.validation_recommended_tx_rows()
        )

    def validation_region_hint(self) -> str:
        """Uyarı metinlerinde kullanılacak şablon etiketi."""
        return self.name
