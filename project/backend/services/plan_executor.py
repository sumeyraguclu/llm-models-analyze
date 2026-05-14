from __future__ import annotations

import inspect
from typing import Any

import pandas as pd

from cleaning.registry import CLEANING_REGISTRY
from features.registry import FEATURE_REGISTRY


def _validate_column_map(df: pd.DataFrame, column_map: dict[str, str]) -> None:
    missing = [col for col in column_map.values() if col not in df.columns]
    if missing:
        raise ValueError(f"column_map DataFrame'de bulunmayan kolonlar içeriyor: {missing}")


def _validate_cleaning_steps(cleaning_plan: list[str]) -> None:
    unknown = [step for step in cleaning_plan if step not in CLEANING_REGISTRY]
    if unknown:
        raise ValueError(
            f"Bilinmeyen cleaning step(leri): {unknown}. Geçerliler: {list(CLEANING_REGISTRY.keys())}"
        )


def _validate_feature_plan(feature_plan: str) -> None:
    if feature_plan not in FEATURE_REGISTRY:
        raise ValueError(
            f"Bilinmeyen feature_plan: {feature_plan}. Geçerliler: {list(FEATURE_REGISTRY.keys())}"
        )


def execute_analysis_plan(df: pd.DataFrame, plan: dict[str, Any]) -> pd.DataFrame:
    """
    Executes an analysis plan safely using pre-registered functions only.

    Plan schema (minimum):
      - column_map: dict[str, str]  (standard_key -> df column name)
      - cleaning_plan: list[str]
      - feature_plan: str
    """
    if not isinstance(plan, dict):
        raise ValueError("analysis_plan bir dict olmalı.")

    column_map = plan.get("column_map")
    cleaning_plan = plan.get("cleaning_plan", [])
    feature_plan = plan.get("feature_plan")

    if not isinstance(column_map, dict):
        raise ValueError("analysis_plan.column_map zorunlu ve dict olmalı.")
    if not isinstance(cleaning_plan, list) or not all(isinstance(x, str) for x in cleaning_plan):
        raise ValueError("analysis_plan.cleaning_plan list[str] olmalı.")
    if not isinstance(feature_plan, str) or not feature_plan:
        raise ValueError("analysis_plan.feature_plan zorunlu ve string olmalı.")

    _validate_column_map(df, column_map)
    _validate_cleaning_steps(cleaning_plan)
    _validate_feature_plan(feature_plan)

    options = plan.get("options", {}) or {}
    if not isinstance(options, dict):
        raise ValueError("analysis_plan.options dict olmalı.")

    out = df.copy()
    for step_name in cleaning_plan:
        func = CLEANING_REGISTRY[step_name]
        if len(inspect.signature(func).parameters) >= 3:
            out = func(out, column_map, options)
        else:
            out = func(out, column_map)

    feature_func = FEATURE_REGISTRY[feature_plan]
    if len(inspect.signature(feature_func).parameters) >= 3:
        out = feature_func(out, column_map, options)
    else:
        out = feature_func(out, column_map)
    if not isinstance(out, pd.DataFrame):
        raise ValueError("feature_plan fonksiyonu DataFrame döndürmeli.")

    return out

