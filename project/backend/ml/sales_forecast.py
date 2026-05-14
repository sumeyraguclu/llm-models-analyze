from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler


def _try_make_regressor():
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor

        return HistGradientBoostingRegressor(random_state=42)
    except Exception:
        from sklearn.linear_model import Ridge

        return Ridge(alpha=1.0, random_state=42)


class SalesForecastPipeline:
    def __init__(self):
        self.regressor = _try_make_regressor()
        self.model: Pipeline = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("reg", self.regressor),
            ]
        )

        self.is_fitted: bool = False
        self._label_encoder: LabelEncoder | None = None
        self._X_test: pd.DataFrame | None = None
        self._y_test: pd.Series | None = None
        self._last_metrics: dict | None = None

    def _prepare(self, df: pd.DataFrame, *, for_training: bool) -> tuple[pd.DataFrame, pd.Series | None]:
        if not isinstance(df, pd.DataFrame):
            raise ValueError("df bir pandas.DataFrame olmalı.")

        df = df.copy()
        required = ["date", "quantity", "price"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError("Eksik zorunlu kolon(lar): " + ", ".join(missing) + ".")

        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["day_of_week"] = df["date"].dt.dayofweek
        df["month"] = df["date"].dt.month
        df["day_of_month"] = df["date"].dt.day
        df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
        df = df.drop(columns=["date"])

        if "revenue" not in df.columns:
            df["revenue"] = pd.to_numeric(df["quantity"], errors="coerce") * pd.to_numeric(
                df["price"], errors="coerce"
            )

        y: pd.Series | None = None
        if for_training:
            y = pd.to_numeric(df["revenue"], errors="coerce")

        # category encoding (optional)
        if "category" in df.columns:
            if for_training:
                le = LabelEncoder()
                df["category"] = df["category"].astype(str).fillna("")
                df["category"] = le.fit_transform(df["category"])
                self._label_encoder = le
            else:
                if self._label_encoder is None:
                    raise ValueError("Model fit edilmeden category encode edilemez.")
                values = df["category"].astype(str).fillna("")
                known = set(self._label_encoder.classes_)
                safe = values.where(values.isin(list(known)), other="")
                df["category"] = self._label_encoder.transform(safe)

        X = df.drop(columns=["revenue"], errors="ignore")
        X = X.apply(pd.to_numeric, errors="coerce")
        X = X.select_dtypes(include=[np.number])
        if X.shape[1] == 0:
            raise ValueError("Model için kullanılabilir sayısal feature bulunamadı.")

        return X, y

    def fit(self, df: pd.DataFrame) -> None:
        X, y = self._prepare(df, for_training=True)
        assert y is not None

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=0.2,
            random_state=42,
        )

        self.model.fit(X_train, y_train)
        self.is_fitted = True
        self._X_test = X_test
        self._y_test = y_test
        self._last_metrics = None

    def predict(self, df: pd.DataFrame) -> dict:
        if not self.is_fitted:
            raise ValueError("predict() çağırmadan önce fit() çağrılmalı.")

        X, _ = self._prepare(df, for_training=False)
        preds = self.model.predict(X)
        preds = np.asarray(preds, dtype=float)

        return {
            "predictions": preds.tolist(),
            "mean_prediction": float(np.mean(preds)) if len(preds) else 0.0,
            "total_predicted_revenue": float(np.sum(preds)) if len(preds) else 0.0,
        }

    def metrics(self, df: pd.DataFrame) -> dict:
        if not self.is_fitted:
            raise ValueError("metrics() çağırmadan önce fit() çağrılmalı.")

        if self._X_test is None or self._y_test is None:
            raise ValueError("Test seti bulunamadı. Önce fit() çağrılmalı.")

        y_true = np.asarray(self._y_test, dtype=float)
        y_pred = np.asarray(self.model.predict(self._X_test), dtype=float)

        rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
        mae = float(mean_absolute_error(y_true, y_pred))
        r2 = float(r2_score(y_true, y_pred))
        mean_rev = float(np.mean(y_true)) if len(y_true) else 0.0

        result = {"rmse": rmse, "mae": mae, "r2": r2, "mean_revenue": mean_rev}
        self._last_metrics = result
        return result

    def summary(self) -> str:
        if not self._last_metrics:
            raise ValueError("summary() için önce metrics() çağrılmalı.")

        r2 = float(self._last_metrics["r2"])
        mean_rev = float(self._last_metrics["mean_revenue"])
        mean_rev_rounded = round(mean_rev, 3)
        r2_rounded = round(r2, 2)

        label = "iyi uyum" if r2 >= 0.8 else "orta uyum" if r2 >= 0.5 else "zayıf uyum"
        return f"Ortalama tahmini gelir: {mean_rev_rounded}. Model R²: {r2_rounded} ({label})."
