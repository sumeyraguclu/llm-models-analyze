from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.metrics import silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.segmentation_personas import (
    PERSONA_HIGH_VALUE,
    SEGMENT_LIST_SIZE_MVP_WARNING,
    build_segment_outputs,
)


class SegmentationPipeline:
    def __init__(self):
        self.is_fitted: bool = False
        self.optimal_k: int | None = None
        self.model: KMeans | None = None
        self.preprocess: Pipeline = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
            ]
        )

        self._silhouette: float | None = None
        self._segment_name_map: dict[int, str] | None = None
        self._full_df: pd.DataFrame | None = None
        self._segment_ids: np.ndarray | None = None
        self._last_metrics: dict | None = None

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(df, pd.DataFrame):
            raise ValueError("df bir pandas.DataFrame olmalı.")

        df = df.copy()

        # If last_order_date is provided, derive days_since_last_order and drop it.
        if "last_order_date" in df.columns and "days_since_last_order" not in df.columns:
            df["last_order_date"] = pd.to_datetime(df["last_order_date"], errors="coerce")
            today = pd.Timestamp.today().normalize()
            df["days_since_last_order"] = (today - df["last_order_date"]).dt.days.astype("Int64")
            df = df.drop(columns=["last_order_date"])
        elif "last_order_date" in df.columns:
            df = df.drop(columns=["last_order_date"])

        # customer_id is not a feature
        if "customer_id" in df.columns:
            df = df.drop(columns=["customer_id"])

        required = ["total_spent", "order_count"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError("Eksik zorunlu kolon(lar): " + ", ".join(missing) + ".")

        # If days_since_last_order missing, create it (unknown recency); keep as NaN to be imputed.
        if "days_since_last_order" not in df.columns:
            df["days_since_last_order"] = np.nan

        X = df[["total_spent", "order_count", "days_since_last_order"]].copy()
        X = X.apply(pd.to_numeric, errors="coerce")
        return X

    @staticmethod
    def _is_high(value: float, median: float) -> bool:
        return value >= median

    def _build_segment_name_map(self, df_original: pd.DataFrame, segments: np.ndarray) -> dict[int, str]:
        temp = df_original.copy()
        if "customer_id" in temp.columns:
            temp = temp.drop(columns=["customer_id"])

        # Ensure columns exist (after _prepare derivation rules)
        if "last_order_date" in temp.columns and "days_since_last_order" not in temp.columns:
            temp["last_order_date"] = pd.to_datetime(temp["last_order_date"], errors="coerce")
            today = pd.Timestamp.today().normalize()
            temp["days_since_last_order"] = (today - temp["last_order_date"]).dt.days
        if "last_order_date" in temp.columns:
            temp = temp.drop(columns=["last_order_date"])
        if "days_since_last_order" not in temp.columns:
            temp["days_since_last_order"] = np.nan

        temp["__segment__"] = segments

        profiles = (
            temp.groupby("__segment__")[["total_spent", "order_count"]]
            .mean(numeric_only=True)
            .rename(columns={"total_spent": "mean_spent", "order_count": "mean_orders"})
        )

        spent_median = float(profiles["mean_spent"].median()) if not profiles.empty else 0.0
        orders_median = float(profiles["mean_orders"].median()) if not profiles.empty else 0.0

        mapping: dict[int, str] = {}
        for seg_id, row in profiles.iterrows():
            mean_spent = float(row["mean_spent"])
            mean_orders = float(row["mean_orders"])

            high_spent = self._is_high(mean_spent, spent_median)
            high_orders = self._is_high(mean_orders, orders_median)

            if high_spent and high_orders:
                mapping[int(seg_id)] = "VIP Müşteriler"
            elif high_spent and not high_orders:
                mapping[int(seg_id)] = "Büyük Alışveriş Yapanlar"
            elif (not high_spent) and high_orders:
                mapping[int(seg_id)] = "Sadık Müşteriler"
            else:
                mapping[int(seg_id)] = "Pasif Müşteriler"

        # If duplicates happen, make labels unique by suffixing
        used: dict[str, int] = {}
        unique_mapping: dict[int, str] = {}
        for seg_id, label in mapping.items():
            count = used.get(label, 0)
            used[label] = count + 1
            unique_mapping[seg_id] = label if count == 0 else f"{label} ({count + 1})"

        return unique_mapping

    def fit(self, df: pd.DataFrame) -> None:
        X_raw = self._prepare(df)
        X = self.preprocess.fit_transform(X_raw)

        best_k = None
        best_score = None
        best_model = None

        # silhouette requires at least 2 clusters and less than n_samples
        n_samples = X.shape[0]
        k_max = min(8, n_samples - 1) if n_samples > 2 else 2

        for k in range(2, k_max + 1):
            km = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = km.fit_predict(X)
            try:
                score = float(silhouette_score(X, labels))
            except Exception:
                score = float("-inf")

            if best_score is None or score > best_score:
                best_score = score
                best_k = k
                best_model = km

        if best_model is None or best_k is None or best_score is None or best_score == float("-inf"):
            raise ValueError("Optimal k belirlenemedi. Veri kümesi segmentasyona uygun olmayabilir.")

        self.model = best_model
        self.optimal_k = int(best_k)
        self._silhouette = float(best_score)

        segments = np.asarray(self.model.labels_, dtype=int)
        self._segment_ids = segments
        self._full_df = df.copy()
        persona_pack = build_segment_outputs(df, segments, optimal_k=int(best_k))
        self._segment_name_map = dict(persona_pack.get("segment_name_by_id") or {})

        self.is_fitted = True
        self._last_metrics = None

    def predict(self, df: pd.DataFrame) -> dict:
        if not self.is_fitted or self.model is None or self.optimal_k is None:
            raise ValueError("predict() çağırmadan önce fit() çağrılmalı.")

        X_raw = self._prepare(df)
        X = self.preprocess.transform(X_raw)
        seg_ids = self.model.predict(X)

        name_map = self._segment_name_map or {}
        labels = [name_map.get(int(i), f"Segment {int(i)}") for i in seg_ids]

        return {"segments": seg_ids.astype(int).tolist(), "segment_labels": labels, "optimal_k": int(self.optimal_k)}

    def metrics(self, df: pd.DataFrame) -> dict:
        if not self.is_fitted or self.model is None or self.optimal_k is None:
            raise ValueError("metrics() çağırmadan önce fit() çağrılmalı.")

        score_df = self._full_df if self._full_df is not None else df
        seg_ids = self._segment_ids
        if seg_ids is None:
            seg_ids = np.asarray(self.model.labels_, dtype=int)

        persona_pack = build_segment_outputs(score_df, seg_ids, optimal_k=int(self.optimal_k))

        segment_actions: dict[str, str] = {}
        for persona in persona_pack.get("segment_personas") or []:
            if not isinstance(persona, dict):
                continue
            name = str(persona.get("segment_name", ""))
            actions = persona.get("recommended_actions")
            if name and isinstance(actions, list) and actions:
                segment_actions[name] = str(actions[0])

        df_copy = score_df.copy()
        if "last_order_date" in df_copy.columns and "days_since_last_order" not in df_copy.columns:
            df_copy["last_order_date"] = pd.to_datetime(df_copy["last_order_date"], errors="coerce")
            today = pd.Timestamp.today().normalize()
            df_copy["days_since_last_order"] = (today - df_copy["last_order_date"]).dt.days
            df_copy = df_copy.drop(columns=["last_order_date"])
        elif "last_order_date" in df_copy.columns:
            df_copy = df_copy.drop(columns=["last_order_date"])
        if "days_since_last_order" not in df_copy.columns:
            df_copy["days_since_last_order"] = np.nan

        name_by_id = persona_pack.get("segment_name_by_id") or {}
        df_copy["__segment_label__"] = [name_by_id.get(int(s), f"Segment {int(s)}") for s in seg_ids]
        profiles = (
            df_copy.groupby("__segment_label__")[["total_spent", "order_count"]]
            .mean(numeric_only=True)
            .rename(columns={"total_spent": "mean_spent", "order_count": "mean_orders"})
        )
        segment_profiles = {
            str(seg_label): {
                "mean_spent": float(row["mean_spent"]),
                "mean_orders": float(row["mean_orders"]),
            }
            for seg_label, row in profiles.iterrows()
        }

        metric_warnings: list[str] = []
        if persona_pack.get("segment_list"):
            metric_warnings.append(
                "segment_list bu işin veri setindeki tüm müşterileri kapsar; yeni veri seti için yeni job gerekir."
            )
            metric_warnings.append(SEGMENT_LIST_SIZE_MVP_WARNING)

        result = {
            "silhouette_score": float(self._silhouette) if self._silhouette is not None else 0.0,
            "optimal_k": int(self.optimal_k),
            "segment_summary": persona_pack.get("segment_summary"),
            "segment_personas": persona_pack.get("segment_personas"),
            "segment_list": persona_pack.get("segment_list"),
            "segment_insights": persona_pack.get("segment_insights"),
            "segment_distribution": persona_pack.get("segment_distribution"),
            "segment_profiles": segment_profiles,
            "segment_actions": segment_actions,
            "metric_warnings": metric_warnings,
        }
        self._last_metrics = result
        return result

    def summary(self) -> str:
        if not self._last_metrics:
            raise ValueError("summary() için önce metrics() çağrılmalı.")

        dist: dict[str, int] = dict(self._last_metrics.get("segment_distribution", {}))
        total = sum(dist.values()) or 1
        largest_label = max(dist, key=dist.get) if dist else "Bilinmiyor"
        largest_pct = round((dist.get(largest_label, 0) / total) * 100, 1)
        vip_pct = round((dist.get(PERSONA_HIGH_VALUE, 0) / total) * 100, 1)

        return (
            f"Müşteriler {int(self._last_metrics['optimal_k'])} gruba ayrıldı. "
            f"En büyük grup: {largest_label} (%{largest_pct}). "
            f"VIP oranı: %{vip_pct}."
        )
