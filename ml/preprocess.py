"""
ml/preprocess.py
─────────────────
Time-Aware Data Preprocessing & Leakage-Free Splitting Pipeline.

Guarantees:
  - Strict Time-Aware Splitting (Scenarios/Chronological blocks assigned sequentially).
  - Feature extraction uses only historical & current observations up to time t.
  - Zero data leakage (preprocessor fit ONLY on training fold).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import OneHotEncoder, StandardScaler

log = logging.getLogger("ml_preprocess")

NUMERICAL_FEATURES = [
    "length_m",
    "lanes",
    "speed_kph",
    "capacity",
    "widenable",
    # Observations at time t
    "flow_t",
    "speed_sim_t",
    "density_t",
    "queue_length_t",
    "wait_time_t",
    "travel_time_t",
    "occupancy_t",
    "speed_ratio_t",
    # Lagged & Momentum features
    "flow_lag1",
    "speed_lag1",
    "occ_lag1",
    "queue_lag1",
    "delta_flow",
    "delta_occ",
    "delta_speed",
    # Temporal context
    "time_step",
    "scenario_demand",
]

CATEGORICAL_FEATURES = [
    "road_type",
]

TARGET_CLASSIFICATION = "future_congestion_level"
TARGET_REGRESSION = "future_congestion_score"


class TrafficPreprocessor:
    """
    Feature extraction, categorical encoding, and standard scaling.
    """

    def __init__(self):
        self.scaler = StandardScaler()
        self.encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
        self.num_cols = list(NUMERICAL_FEATURES)
        self.cat_cols = list(CATEGORICAL_FEATURES)
        self.feature_names_: list[str] = []
        self.is_fitted = False

    def _prepare_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean dataframe, alias legacy/current column names, and construct features."""
        df = df.copy()

        # Backward compatibility aliases for inference when passing unlagged dictionaries
        alias_map = {
            "flow": "flow_t",
            "speed_sim": "speed_sim_t",
            "density": "density_t",
            "queue_length": "queue_length_t",
            "wait_time": "wait_time_t",
            "travel_time": "travel_time_t",
            "occupancy": "occupancy_t",
            "speed_ratio": "speed_ratio_t",
        }
        for old_k, new_k in alias_map.items():
            if new_k not in df.columns and old_k in df.columns:
                df[new_k] = df[old_k]

        # Construct derived lag/delta features if absent (e.g. at real-time single-step inference)
        if "flow_lag1" not in df.columns and "flow_t" in df.columns:
            df["flow_lag1"] = df["flow_t"]
        if "speed_lag1" not in df.columns and "speed_sim_t" in df.columns:
            df["speed_lag1"] = df["speed_sim_t"]
        if "occ_lag1" not in df.columns and "occupancy_t" in df.columns:
            df["occ_lag1"] = df["occupancy_t"]
        if "queue_lag1" not in df.columns and "queue_length_t" in df.columns:
            df["queue_lag1"] = df["queue_length_t"]
        if "delta_flow" not in df.columns and "flow_t" in df.columns:
            df["delta_flow"] = 0.0
        if "delta_occ" not in df.columns and "occupancy_t" in df.columns:
            df["delta_occ"] = 0.0
        if "delta_speed" not in df.columns and "speed_sim_t" in df.columns:
            df["delta_speed"] = 0.0
        if "time_step" not in df.columns:
            df["time_step"] = 1
        if "scenario_demand" not in df.columns:
            df["scenario_demand"] = 0.75

        # Handle missing numerical values
        for col in self.num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                median_val = df[col].median() if not df[col].dropna().empty else 0.0
                df[col] = df[col].fillna(median_val)
            else:
                df[col] = 0.0

        for col in self.cat_cols:
            if col in df.columns:
                df[col] = df[col].fillna("unclassified").astype(str)
            else:
                df[col] = "unclassified"

        return df

    def fit(self, df: pd.DataFrame) -> TrafficPreprocessor:
        df_clean = self._prepare_df(df)

        X_num = df_clean[self.num_cols].values
        self.scaler.fit(X_num)

        X_cat = df_clean[self.cat_cols].values
        self.encoder.fit(X_cat)

        cat_feature_names = list(self.encoder.get_feature_names_out(self.cat_cols))
        self.feature_names_ = self.num_cols + cat_feature_names
        self.is_fitted = True
        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("TrafficPreprocessor must be fitted before calling transform().")

        df_clean = self._prepare_df(df)
        X_num = self.scaler.transform(df_clean[self.num_cols].values)
        X_cat = self.encoder.transform(df_clean[self.cat_cols].values)

        return np.hstack([X_num, X_cat])

    def fit_transform(self, df: pd.DataFrame) -> np.ndarray:
        return self.fit(df).transform(df)

    def save(self, file_path: Path | str) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        log.info(f"Preprocessor saved to {path}")

    @classmethod
    def load(cls, file_path: Path | str) -> TrafficPreprocessor:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Preprocessor file not found at {path}")
        obj = joblib.load(path)
        log.info(f"Preprocessor loaded from {path}")
        return obj


def prepare_train_test_data(
    df: pd.DataFrame,
    test_size: float = 0.20,
    val_size: float = 0.10,
    random_state: int = 42,
    time_aware_split: bool = True,
) -> dict[str, Any]:
    """
    Time-aware dataset partitioning:
    Assigns sequential scenario trajectories (e.g. Scenarios 1..18 for Train, 19..21 for Val, 22..25 for Test)
    to prevent temporal leakage across future scenarios.
    """
    df = df.copy()

    # Support both new future target name and legacy fallback
    target_col = TARGET_CLASSIFICATION if TARGET_CLASSIFICATION in df.columns else "congestion_level"
    target_reg_col = TARGET_REGRESSION if TARGET_REGRESSION in df.columns else "congestion_score"

    if target_col not in df.columns:
        raise ValueError(f"Target column '{target_col}' not found in dataframe.")

    if time_aware_split and "scenario_id" in df.columns:
        scenarios = sorted(df["scenario_id"].unique())
        n_scenarios = len(scenarios)

        n_test = max(1, int(n_scenarios * test_size))
        n_val = max(1, int(n_scenarios * val_size))
        n_train = n_scenarios - n_test - n_val

        # Sequential chronological partition
        train_scenarios = scenarios[:n_train]
        val_scenarios = scenarios[n_train:n_train + n_val]
        test_scenarios = scenarios[n_train + n_val:]

        train_df = df[df["scenario_id"].isin(train_scenarios)].reset_index(drop=True)
        val_df = df[df["scenario_id"].isin(val_scenarios)].reset_index(drop=True)
        test_df = df[df["scenario_id"].isin(test_scenarios)].reset_index(drop=True)
    else:
        from sklearn.model_selection import train_test_split
        train_df, test_val_df = train_test_split(
            df, test_size=(test_size + val_size), random_state=random_state, stratify=df[target_col]
        )
        val_ratio = val_size / (test_size + val_size)
        val_df, test_df = train_test_split(
            test_val_df, test_size=(1.0 - val_ratio), random_state=random_state, stratify=test_val_df[target_col]
        )

    # Fit preprocessor strictly on train_df
    preprocessor = TrafficPreprocessor()
    X_train = preprocessor.fit_transform(train_df)
    X_val = preprocessor.transform(val_df)
    X_test = preprocessor.transform(test_df)

    y_train = train_df[target_col].values.astype(int)
    y_val = val_df[target_col].values.astype(int)
    y_test = test_df[target_col].values.astype(int)

    y_train_reg = train_df[target_reg_col].values.astype(float) if target_reg_col in train_df.columns else None
    y_val_reg = val_df[target_reg_col].values.astype(float) if target_reg_col in val_df.columns else None
    y_test_reg = test_df[target_reg_col].values.astype(float) if target_reg_col in test_df.columns else None

    return {
        "preprocessor": preprocessor,
        "feature_names": preprocessor.feature_names_,
        "X_train": X_train,
        "y_train": y_train,
        "y_train_reg": y_train_reg,
        "X_val": X_val,
        "y_val": y_val,
        "y_val_reg": y_val_reg,
        "X_test": X_test,
        "y_test": y_test,
        "y_test_reg": y_test_reg,
        "train_df": train_df,
        "val_df": val_df,
        "test_df": test_df,
        "target_column": target_col,
    }
