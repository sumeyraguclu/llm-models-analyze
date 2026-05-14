from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# Model yalnızca bu sayısal iş kolu feature'larını kullanır (metadata / hedef sızıntısı engeli)
FEATURE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "recency",
        "recency_days",
        "days_since_last_order",
        "frequency",
        "monetary",
        "order_count",
        "total_spent",
        "avg_order_value",
    }
)


@dataclass
class _PreparedData:
    X: pd.DataFrame
    y: pd.Series | None
    feature_names: list[str]


def _ordered_feature_columns(df: pd.DataFrame) -> list[str]:
    """Allowlist sırası; recency için tek kanon kolon seç."""
    have = set(df.columns)
    out: list[str] = []
    if "recency" in have:
        out.append("recency")
    elif "recency_days" in have:
        out.append("recency_days")
    elif "days_since_last_order" in have:
        out.append("days_since_last_order")
    for name in ("frequency", "monetary", "order_count", "total_spent", "avg_order_value"):
        if name in have:
            out.append(name)
    return [c for c in out if c in FEATURE_ALLOWLIST]


def _split_train_test(
    X: pd.DataFrame,
    y: pd.Series,
    dates: pd.Series | None,
    *,
    test_size: float = 0.2,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, str, list[str]]:
    split_warnings: list[str] = []
    n = len(X)
    min_temporal_valid = max(15, int(0.4 * n))

    if dates is not None and dates.notna().sum() >= min_temporal_valid:
        d = pd.to_datetime(dates, errors="coerce")
        meta = pd.DataFrame({"d": d, "y": y.values}, index=X.index)
        meta = meta.sort_values("d", na_position="first")
        n_test = max(1, int(len(meta) * test_size))
        if n_test < 5:
            split_warnings.append("Temporal split: test kümesi çok küçük (<5 gözlem).")
        test_idx = meta.index[-n_test:]
        train_idx = meta.index[:-n_test]
        return (
            X.loc[train_idx],
            X.loc[test_idx],
            y.loc[train_idx],
            y.loc[test_idx],
            "temporal_last_order_date",
            split_warnings,
        )

    if dates is None or dates.notna().sum() < min_temporal_valid:
        split_warnings.append(
            "Temporal split kullanılamıyor (last_order_date yok veya çok eksik); "
            "stratified split kullanıldı. Zaman bazlı sızıntı riski için tarih kolonu önerilir."
        )
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )
        strat = "stratified_random"
    except ValueError:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=None
        )
        strat = "random_no_stratify"
        split_warnings.append("Stratified split uygulanamadı (sınıf sayısı yetersiz); stratify olmadan bölündü.")

    return X_train, X_test, y_train, y_test, strat, split_warnings


def _class_distribution(y: pd.Series) -> dict[str, int]:
    out: dict[str, int] = {}
    for k, v in y.value_counts(dropna=False).items():
        key = "nan" if pd.isna(k) else str(int(k))
        out[key] = int(v)
    return out


def _baseline_metrics(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    *,
    recency_col: str | None,
) -> dict:
    """Majority class ve basit recency eşik (train medyanı) baseline."""
    if len(y_train) == 0 or len(y_test) == 0:
        return {
            "majority_class": {"accuracy": 0.0, "f1": 0.0, "predicted_class": 0},
            "recency_gt_median_train": {"accuracy": 0.0, "f1": 0.0, "threshold": None},
        }

    mode = y_train.mode(dropna=True)
    maj_cls = int(mode.iloc[0]) if len(mode) else 0
    y_maj = np.full(len(y_test), maj_cls, dtype=int)
    acc_maj = float(accuracy_score(y_test, y_maj))
    f1_maj = float(f1_score(y_test, y_maj, zero_division=0))

    thr: float | None = None
    if recency_col and recency_col in X_train.columns and recency_col in X_test.columns:
        r_tr = pd.to_numeric(X_train[recency_col], errors="coerce")
        thr = float(np.nanmedian(r_tr))
        r_te = pd.to_numeric(X_test[recency_col], errors="coerce")
        y_rec = (r_te > thr).fillna(False).astype(np.int64)
    else:
        y_rec = y_maj.copy()

    acc_rec = float(accuracy_score(y_test, y_rec))
    f1_rec = float(f1_score(y_test, y_rec, zero_division=0))

    return {
        "majority_class": {"accuracy": acc_maj, "f1": f1_maj, "predicted_class": maj_cls},
        "recency_gt_median_train": {"accuracy": acc_rec, "f1": f1_rec, "threshold": thr},
    }


class ChurnPipeline:
    def __init__(self, churn_days: int = 90):
        self.churn_days = int(churn_days)
        self.model: Pipeline = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("clf", RandomForestClassifier(n_estimators=100, random_state=42)),
            ]
        )

        self.is_fitted: bool = False
        self._feature_names: list[str] | None = None
        self._recency_col: str | None = None
        self._X_test: pd.DataFrame | None = None
        self._y_test: pd.Series | None = None
        self._y_train: pd.Series | None = None
        self._last_metrics: dict | None = None
        self._split_strategy: str | None = None
        self._split_warnings: list[str] = []
        self._baseline_metrics: dict | None = None
        self._train_size: int = 0
        self._test_size: int = 0

    def _validate_required_columns(self, df: pd.DataFrame) -> None:
        has_recency = any(c in df.columns for c in ["recency", "recency_days", "days_since_last_order"])
        has_last_order_date = "last_order_date" in df.columns
        if not (has_recency or has_last_order_date):
            raise ValueError(
                "Eksik zorunlu kolon: recency (veya last_order_date). "
                "Feature engineering sonrası recency beklenir; ham veride last_order_date kabul edilir."
            )

        has_spend = any(c in df.columns for c in ["monetary", "total_spent"])
        if not has_spend:
            raise ValueError("Eksik zorunlu kolon: monetary (veya total_spent).")

    def _prepare(self, df: pd.DataFrame, *, for_training: bool) -> _PreparedData:
        if not isinstance(df, pd.DataFrame):
            raise ValueError("df bir pandas.DataFrame olmalı.")

        df = df.copy()
        self._validate_required_columns(df)

        if "recency" in df.columns:
            df["recency"] = pd.to_numeric(df["recency"], errors="coerce")
        elif "recency_days" in df.columns:
            df["recency"] = pd.to_numeric(df["recency_days"], errors="coerce")
        elif "days_since_last_order" in df.columns:
            df["recency"] = pd.to_numeric(df["days_since_last_order"], errors="coerce")
        elif "last_order_date" in df.columns:
            df["last_order_date"] = pd.to_datetime(df["last_order_date"], errors="coerce")
            today = pd.Timestamp.today().normalize()
            df["recency"] = (today - df["last_order_date"]).dt.days
        else:
            raise ValueError("recency veya last_order_date bulunamadı.")

        if "churn" not in df.columns:
            churn_mask = pd.to_numeric(df["recency"], errors="coerce") > self.churn_days
            df["churn"] = churn_mask.fillna(False).astype(np.int64)

        y = None
        if for_training:
            y = df["churn"].fillna(0).astype(np.int64)

        feat_cols = _ordered_feature_columns(df)
        if not feat_cols:
            raise ValueError("Allowlist ile seçilebilen sayısal feature yok.")

        X = df[feat_cols].copy()
        X = X.apply(pd.to_numeric, errors="coerce")
        X = X.replace([np.inf, -np.inf], np.nan)
        X = X.dropna(axis=1, how="all")
        if X.shape[1] == 0:
            raise ValueError("Model için kullanılabilir sayısal feature kalmadı.")

        self._recency_col = "recency" if "recency" in X.columns else None
        if self._recency_col is None:
            if "recency_days" in X.columns:
                self._recency_col = "recency_days"
            elif "days_since_last_order" in X.columns:
                self._recency_col = "days_since_last_order"

        feature_names = list(X.columns)
        return _PreparedData(X=X, y=y, feature_names=feature_names)

    def fit(self, df: pd.DataFrame) -> None:
        prepared = self._prepare(df, for_training=True)
        assert prepared.y is not None

        dates = None
        if "last_order_date" in df.columns:
            dates = pd.to_datetime(df["last_order_date"], errors="coerce").reindex(prepared.X.index)

        X_train, X_test, y_train, y_test, strat, sw = _split_train_test(prepared.X, prepared.y, dates)
        self._split_strategy = strat
        self._split_warnings = list(sw)
        self._train_size = int(len(X_train))
        self._test_size = int(len(X_test))
        self._y_train = y_train

        self.model.fit(X_train, y_train)
        self.is_fitted = True
        self._feature_names = list(X_train.columns)
        self._X_test = X_test
        self._y_test = y_test

        self._baseline_metrics = _baseline_metrics(
            X_train,
            y_train,
            X_test,
            y_test,
            recency_col=self._recency_col,
        )
        self._last_metrics = None

    def predict(self, df: pd.DataFrame) -> dict:
        if not self.is_fitted:
            raise ValueError("predict() çağırmadan önce fit() çağrılmalı.")

        prepared = self._prepare(df, for_training=False)
        preds = self.model.predict(prepared.X)

        proba = None
        if hasattr(self.model, "predict_proba"):
            proba = self.model.predict_proba(prepared.X)[:, 1]
        else:
            proba = np.zeros_like(preds, dtype=float)

        churn_rate = float(np.mean(preds)) if len(preds) else 0.0
        return {
            "predictions": preds.astype(int).tolist(),
            "churn_probabilities": np.asarray(proba, dtype=float).tolist(),
            "churn_rate": churn_rate,
        }

    def metrics(self, df: pd.DataFrame) -> dict:
        if not self.is_fitted:
            raise ValueError("metrics() çağırmadan önce fit() çağrılmalı.")

        if self._X_test is None or self._y_test is None:
            raise ValueError("Test seti bulunamadı. Önce fit() çağrılmalı.")

        y_true = self._y_test
        y_pred = self.model.predict(self._X_test)

        acc = float(accuracy_score(y_true, y_pred))
        prec = float(precision_score(y_true, y_pred, zero_division=0))
        rec = float(recall_score(y_true, y_pred, zero_division=0))
        f1 = float(f1_score(y_true, y_pred, zero_division=0))
        churn_rate_pred = float(np.mean(y_pred)) if len(y_pred) else 0.0

        importances: dict[str, float] = {}
        try:
            clf = self.model.named_steps["clf"]
            raw = getattr(clf, "feature_importances_", None)
            if raw is not None:
                names = self._feature_names or []
                importances = {name: float(score) for name, score in zip(names, raw)}
        except Exception:
            importances = {}

        dist_test = _class_distribution(y_true)
        dist_train = _class_distribution(self._y_train) if self._y_train is not None else {}
        n_total = self._train_size + self._test_size
        baselines = dict(self._baseline_metrics or {})

        metric_warnings: list[str] = list(self._split_warnings)

        if self._test_size < 25:
            metric_warnings.append(
                f"Test seti küçük (n_test={self._test_size}); metrikler yüksek varyanslı olabilir."
            )
        if n_total > 0 and self._test_size / n_total < 0.05:
            metric_warnings.append("Test oranı toplam gözleme göre düşük; güven aralığı geniş olabilir.")

        n_pos = int((y_true == 1).sum())
        n_neg = int((y_true == 0).sum())
        minority_rate = min(n_pos, n_neg) / len(y_true) if len(y_true) else 0.0
        if minority_rate < 0.05:
            metric_warnings.append(
                "Test setinde churn sınıfı çok dengesiz (azınlık < %5); precision/recall dalgalı olabilir."
            )
        if minority_rate < 0.1:
            metric_warnings.append(
                "Dengesiz sınıflar: accuracy yanıltıcı olabilir; F1 ve iş metriklerine bakın."
            )

        maj_acc = float(baselines.get("majority_class", {}).get("accuracy", 0.0))
        if acc <= maj_acc + 0.005:
            metric_warnings.append(
                "Model doğruluğu majority-class baseline ile kıyaslanabilir veya daha düşük; "
                "basit bir kural yeterli olabilir."
            )

        rec_acc = float(baselines.get("recency_gt_median_train", {}).get("accuracy", 0.0))
        if acc <= rec_acc + 0.005 and self._recency_col:
            metric_warnings.append(
                "Model, train recency medyanı kural baseline'ından belirgin şekilde iyi değil."
            )

        if self._split_strategy and self._split_strategy != "temporal_last_order_date":
            metric_warnings.append(
                "Temporal split uygulanmadı; müşteri düzeyi veride bile zaman sızıntısı senaryolarını gözden geçirin."
            )

        if acc >= 0.999 and f1 >= 0.999:
            metric_warnings.append(
                "Perfect metrics detected; possible leakage, çok küçük test seti veya aşırı uyum — sonuçları doğrulayın."
            )

        result = {
            "accuracy": acc,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "feature_importances": importances,
            "churn_rate": churn_rate_pred,
            "class_distribution_test": dist_test,
            "class_distribution_train": dist_train,
            "train_size": self._train_size,
            "test_size": self._test_size,
            "split_strategy": self._split_strategy,
            "feature_columns_used": list(self._feature_names or []),
            "baselines": baselines,
            "metric_warnings": metric_warnings,
        }
        self._last_metrics = result
        return result

    def summary(self) -> str:
        if not self._last_metrics:
            raise ValueError("summary() için önce metrics() çağrılmalı.")

        m = self._last_metrics
        churn_rate_pct = round(float(m["churn_rate"]) * 100, 1)
        acc_pct = round(float(m["accuracy"]) * 100, 1)
        base = ""
        mw = m.get("metric_warnings") or []
        if isinstance(mw, list) and mw:
            base = f" Uyarı: {mw[0]}"
        return f"Müşterilerin yaklaşık %{churn_rate_pct}'ü churn riski taşıyor. Model doğruluğu: %{acc_pct}.{base}"
