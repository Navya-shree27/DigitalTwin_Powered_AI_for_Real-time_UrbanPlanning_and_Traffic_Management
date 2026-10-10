"""
ml/predict.py
──────────────
Production Inference Engine for Traffic Congestion Prediction.

Loads the persisted model and preprocessor, and generates real-time predictions
and probability distributions from incoming simulation telemetry.

Usage:
──────
    python -m ml.predict
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ml.preprocess import TrafficPreprocessor

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
DEFAULT_MODEL_PATH = MODELS_DIR / "traffic_model.joblib"
DEFAULT_PREPROCESSOR_PATH = MODELS_DIR / "preprocessor.joblib"

log = logging.getLogger("ml_predict")

CLASS_MAP = {0: "Low", 1: "Moderate", 2: "Severe"}


class TrafficPredictor:
    """
    Inference wrapper for the trained traffic model.
    """

    def __init__(
        self,
        model_path: Path | str = DEFAULT_MODEL_PATH,
        preprocessor_path: Path | str = DEFAULT_PREPROCESSOR_PATH,
    ):
        self.model_path = Path(model_path)
        self.preprocessor_path = Path(preprocessor_path)
        self._model = None
        self._preprocessor = None
        self._load()

    def _load(self) -> None:
        """Load trained model artifacts."""
        if not self.model_path.exists() or not self.preprocessor_path.exists():
            log.warning(
                f"Model artifacts not found at {self.model_path}. "
                "Predictor will run in fallback heuristic mode until trained."
            )
            return

        try:
            self._model = joblib.load(self.model_path)
            self._preprocessor = TrafficPreprocessor.load(self.preprocessor_path)
            log.info("TrafficPredictor successfully loaded model and preprocessor.")
        except Exception as e:
            log.error(f"Failed to load model artifacts: {e}")
            self._model = None
            self._preprocessor = None

    @property
    def is_ready(self) -> bool:
        return self._model is not None and self._preprocessor is not None

    def predict_batch(self, edge_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Enrich a list of edge telemetry dictionaries with ML predictions.
        """
        if not edge_records:
            return []

        if not self.is_ready:
            # Fallback heuristic if model not trained yet
            return self._heuristic_fallback(edge_records)

        df = pd.DataFrame(edge_records)
        X = self._preprocessor.transform(df)

        preds = self._model.predict(X)
        probs = self._model.predict_proba(X) if hasattr(self._model, "predict_proba") else None

        enriched = []
        for idx, record in enumerate(edge_records):
            rec = dict(record)
            pred_class = int(preds[idx])
            pred_label = CLASS_MAP.get(pred_class, "Unknown")

            if probs is not None:
                prob_dict = {
                    CLASS_MAP.get(c, str(c)): round(float(probs[idx][c]), 4)
                    for c in range(len(probs[idx]))
                }
                # Severe + 0.5*Moderate probability as risk score
                risk_score = round(
                    float(prob_dict.get("Severe", 0.0) + 0.4 * prob_dict.get("Moderate", 0.0)),
                    4
                )
            else:
                prob_dict = {pred_label: 1.0}
                risk_score = 0.9 if pred_class == 2 else (0.5 if pred_class == 1 else 0.1)

            rec["ml_congestion_level"] = pred_class
            rec["ml_congestion_label"] = pred_label
            rec["ml_congestion_probs"] = prob_dict
            rec["ml_risk_score"] = risk_score
            enriched.append(rec)

        return enriched

    def predict_single(self, edge_record: dict[str, Any]) -> dict[str, Any]:
        """Predict for a single edge record."""
        return self.predict_batch([edge_record])[0]

    def _heuristic_fallback(self, edge_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fallback when model artifacts are not present."""
        enriched = []
        for r in edge_records:
            rec = dict(r)
            occ = float(rec.get("occupancy", 0.0))
            if occ > 0.78:
                c, label, risk = 2, "Severe", 0.85
            elif occ > 0.50:
                c, label, risk = 1, "Moderate", 0.50
            else:
                c, label, risk = 0, "Low", 0.15

            rec["ml_congestion_level"] = c
            rec["ml_congestion_label"] = label
            rec["ml_congestion_probs"] = {label: 1.0}
            rec["ml_risk_score"] = risk
            enriched.append(rec)
        return enriched


# Global singleton
_predictor_instance: TrafficPredictor | None = None


def get_predictor() -> TrafficPredictor:
    global _predictor_instance
    if _predictor_instance is None:
        _predictor_instance = TrafficPredictor()
    return _predictor_instance


def predict_congestion(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Module-level helper for batch inference."""
    return get_predictor().predict_batch(edges)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test traffic ML inference.")
    args = parser.parse_args()

    # Test sample data points
    samples = [
        {
            "edge_id": "test_free_flow",
            "length_m": 250, "road_type": "primary", "lanes": 2, "speed_kph": 50,
            "capacity": 1800, "flow": 400, "speed_sim": 48, "density": 8.3,
            "queue_length": 0.0, "wait_time": 0.0, "travel_time": 18.7,
            "occupancy": 0.22, "speed_ratio": 0.96, "widenable": 1,
        },
        {
            "edge_id": "test_moderate",
            "length_m": 400, "road_type": "secondary", "lanes": 1, "speed_kph": 40,
            "capacity": 800, "flow": 520, "speed_sim": 26, "density": 20.0,
            "queue_length": 3.2, "wait_time": 14.5, "travel_time": 55.4,
            "occupancy": 0.65, "speed_ratio": 0.65, "widenable": 1,
        },
        {
            "edge_id": "test_severe_bottleneck",
            "length_m": 300, "road_type": "residential", "lanes": 1, "speed_kph": 30,
            "capacity": 400, "flow": 420, "speed_sim": 8.5, "density": 49.4,
            "queue_length": 14.0, "wait_time": 68.0, "travel_time": 127.0,
            "occupancy": 1.05, "speed_ratio": 0.28, "widenable": 0,
        },
    ]

    predictor = TrafficPredictor()
    results = predictor.predict_batch(samples)
    print("\n" + "="*60)
    print("Inference Test on Sample Edge Records:")
    print("="*60)
    for res in results:
        print(f"Edge: {res['edge_id']}")
        print(f"  Speed: {res['speed_sim']} km/h (free-flow {res['speed_kph']} km/h)")
        print(f"  Occupancy: {res['occupancy']:.1%}")
        print(f"  ML Predicted Class: {res['ml_congestion_label']} (Level {res['ml_congestion_level']})")
        print(f"  Class Probabilities: {res['ml_congestion_probs']}")
        print(f"  Risk Score: {res['ml_risk_score']}")
        print("-" * 60)
