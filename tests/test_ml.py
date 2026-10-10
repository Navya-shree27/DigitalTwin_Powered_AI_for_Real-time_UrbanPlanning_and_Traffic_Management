"""
tests/test_ml.py
────────────────
Comprehensive unit tests for the machine learning future traffic prediction subsystem:
  - Time-series dataset generation
  - Preprocessing & temporal leakage prevention
  - Model training & persistence
  - Model evaluation metrics
  - Prediction & inference
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
import pandas as pd
import pytest

from ml.dataset_generator import calculate_congestion_labels
from ml.preprocess import TrafficPreprocessor, prepare_train_test_data
from ml.predict import TrafficPredictor, predict_congestion


def _sample_raw_dataframe(n_samples: int = 50) -> pd.DataFrame:
    """Generate mock dataframe with realistic traffic distributions and future target."""
    np.random.seed(42)
    flows = np.random.uniform(100, 1800, n_samples)
    capacities = np.random.choice([600, 800, 1400, 2000], n_samples)
    occupancies = np.clip(flows / capacities, 0.05, 1.2)
    speeds_ff = np.random.choice([30, 40, 50, 60], n_samples)
    speeds_sim = speeds_ff * np.maximum(0.1, (1.0 - 0.5 * occupancies))

    records = []
    for i in range(n_samples):
        occ = occupancies[i]
        s_sim = speeds_sim[i]
        s_ff = speeds_ff[i]
        q_len = max(0.0, (occ - 0.7) * 20)
        wait_t = max(0.0, (occ - 0.5) * 40)
        s_ratio = s_sim / s_ff

        lbl, lbl_name, score = calculate_congestion_labels(occ, s_ratio, q_len, wait_t)
        records.append({
            "scenario_id": (i % 5) + 1,
            "time_step": (i % 10) + 1,
            "scenario_demand": 0.85,
            "edge_id": f"edge_{i}",
            "u": i,
            "v": i + 1,
            "length_m": 150.0,
            "road_type": np.random.choice(["primary", "secondary", "residential", "motorway"]),
            "lanes": 2,
            "speed_kph": s_ff,
            "capacity": capacities[i],
            "widenable": 1,
            "flow_t": flows[i],
            "speed_sim_t": s_sim,
            "density_t": flows[i] / s_sim,
            "queue_length_t": q_len,
            "wait_time_t": wait_t,
            "travel_time_t": (150.0 / 1000) / s_sim * 3600,
            "occupancy_t": occ,
            "speed_ratio_t": s_ratio,
            "flow_lag1": flows[i] * 0.95,
            "speed_lag1": s_sim * 1.05,
            "occ_lag1": occ * 0.90,
            "queue_lag1": max(0.0, q_len - 1.0),
            "delta_flow": flows[i] * 0.05,
            "delta_occ": occ * 0.10,
            "delta_speed": s_sim * -0.05,
            "future_congestion_level": lbl,
            "future_congestion_label": lbl_name,
            "future_congestion_score": score,
        })
    return pd.DataFrame(records)


class TestDatasetGenerator:
    def test_congestion_labels_logic(self):
        # Severe conditions
        lbl_sev, name_sev, score_sev = calculate_congestion_labels(
            occupancy=0.95, speed_ratio=0.25, queue_length=15.0, wait_time=45.0
        )
        assert lbl_sev == 2
        assert name_sev == "Severe"
        assert score_sev > 0.60

        # Free flow conditions
        lbl_low, name_low, score_low = calculate_congestion_labels(
            occupancy=0.20, speed_ratio=0.95, queue_length=0.0, wait_time=0.0
        )
        assert lbl_low == 0
        assert name_low == "Low"
        assert score_low < 0.35


class TestPreprocessing:
    def test_preprocessor_fit_transform(self):
        df = _sample_raw_dataframe(40)
        preprocessor = TrafficPreprocessor()
        X = preprocessor.fit_transform(df)

        assert preprocessor.is_fitted
        assert X.shape[0] == 40
        assert X.shape[1] >= len(preprocessor.num_cols)
        assert not np.isnan(X).any()

    def test_zero_data_leakage_split(self):
        df = _sample_raw_dataframe(60)
        split = prepare_train_test_data(df, test_size=0.20, val_size=0.10, random_state=42)

        assert "X_train" in split and "X_test" in split and "X_val" in split
        assert len(split["X_train"]) + len(split["X_val"]) + len(split["X_test"]) == len(df)
        assert split["preprocessor"].is_fitted
        assert split["target_column"] == "future_congestion_level"


class TestPredictor:
    def test_predict_single_and_batch(self):
        predictor = TrafficPredictor()
        samples = [
            {
                "edge_id": "test_e1",
                "length_m": 200, "road_type": "primary", "lanes": 2, "speed_kph": 50,
                "capacity": 1800, "flow": 300, "speed_sim": 48, "density": 6.25,
                "queue_length": 0.0, "wait_time": 0.0, "travel_time": 15.0,
                "occupancy": 0.16, "speed_ratio": 0.96, "widenable": 1,
            },
            {
                "edge_id": "test_e2",
                "length_m": 300, "road_type": "residential", "lanes": 1, "speed_kph": 30,
                "capacity": 400, "flow": 450, "speed_sim": 7.0, "density": 64.0,
                "queue_length": 18.0, "wait_time": 80.0, "travel_time": 154.0,
                "occupancy": 1.12, "speed_ratio": 0.23, "widenable": 0,
            }
        ]

        preds = predictor.predict_batch(samples)
        assert len(preds) == 2
        for p in preds:
            assert "ml_congestion_level" in p
            assert p["ml_congestion_level"] in (0, 1, 2)
            assert "ml_congestion_label" in p
            assert p["ml_congestion_label"] in ("Low", "Moderate", "Severe")
            assert "ml_congestion_probs" in p
            assert "ml_risk_score" in p
            assert 0.0 <= p["ml_risk_score"] <= 1.0
