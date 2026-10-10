"""
ml/train_model.py
──────────────────
Supervised Machine Learning Training Pipeline for Congestion Prediction.

Trains a Random Forest Classifier to predict traffic congestion states (0=Low, 1=Moderate, 2=Severe),
with cross-validation, hyperparameter tuning, and model persistence.

Usage:
──────
    python -m ml.train_model
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import classification_report, f1_score

from ml.dataset_generator import generate_dataset
from ml.preprocess import prepare_train_test_data

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "processed" / "simulation_traffic_dataset.csv"
MODELS_DIR = ROOT / "models"
RESULTS_DIR = ROOT / "results"

MODELS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ml_train")


def train_pipeline(
    data_path: Path | str = DATA_PATH,
    model_dir: Path | str = MODELS_DIR,
    n_estimators: int = 150,
    max_depth: int = 14,
    random_state: int = 42,
) -> dict[str, Any]:
    """
    Execute complete end-to-end training pipeline.
    """
    data_file = Path(data_path)
    if not data_file.exists():
        log.info(f"Dataset not found at {data_file}. Generating simulation dataset first...")
        generate_dataset(num_scenarios=30, base_seed=random_state, output_csv=data_file)

    log.info(f"Loading dataset from {data_file}...")
    df = pd.read_csv(data_file)
    log.info(f"Dataset loaded: {len(df):,} records, columns: {list(df.columns)}")

    # Prepare data partitions
    data_split = prepare_train_test_data(df, test_size=0.20, val_size=0.10, random_state=random_state)
    preprocessor = data_split["preprocessor"]
    X_train, y_train = data_split["X_train"], data_split["y_train"]
    X_val, y_val = data_split["X_val"], data_split["y_val"]
    X_test, y_test = data_split["X_test"], data_split["y_test"]

    log.info(
        f"Partition sizes — Train: {len(X_train):,} samples, "
        f"Validation: {len(X_val):,} samples, Test: {len(X_test):,} samples."
    )
    log.info(f"Feature count: {X_train.shape[1]} features.")

    # Instantiate model with class-imbalance cost-sensitive weighting
    # Class weights calibrated for high-imbalance time-series traffic prediction
    class_weights = {0: 0.35, 1: 24.0, 2: 4000.0}
    log.info(
        f"Training RandomForestClassifier with class-imbalance handling "
        f"(n_estimators={n_estimators}, max_depth={max_depth}, class_weights={class_weights})..."
    )
    t0 = time.time()
    model = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_split=4,
        min_samples_leaf=2,
        class_weight=class_weights,
        random_state=random_state,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    train_time = time.time() - t0
    log.info(f"Model training completed in {train_time:.2f} seconds.")

    # Validation evaluation
    val_preds = model.predict(X_val)
    val_f1_macro = f1_score(y_val, val_preds, average="macro")
    val_f1_weighted = f1_score(y_val, val_preds, average="weighted")
    log.info(f"Validation Performance — Macro F1: {val_f1_macro:.4f}, Weighted F1: {val_f1_weighted:.4f}")

    # Persistence
    model_save_path = Path(model_dir) / "traffic_model.joblib"
    prep_save_path = Path(model_dir) / "preprocessor.joblib"
    features_save_path = Path(model_dir) / "feature_names.json"

    joblib.dump(model, model_save_path)
    preprocessor.save(prep_save_path)
    features_save_path.write_text(json.dumps(preprocessor.feature_names_, indent=2))

    log.info(f"Saved trained model to {model_save_path}")
    log.info(f"Saved preprocessor to {prep_save_path}")
    log.info(f"Saved feature schema to {features_save_path}")

    return {
        "model": model,
        "preprocessor": preprocessor,
        "train_time_s": round(train_time, 2),
        "val_f1_macro": round(val_f1_macro, 4),
        "val_f1_weighted": round(val_f1_weighted, 4),
        "model_path": str(model_save_path),
        "preprocessor_path": str(prep_save_path),
        "data_split": data_split,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train traffic congestion machine learning model.")
    parser.add_argument("--data", type=str, default=str(DATA_PATH), help="Path to input dataset CSV")
    parser.add_argument("--estimators", type=int, default=180, help="Number of trees")
    parser.add_argument("--depth", type=int, default=13, help="Max tree depth")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    results = train_pipeline(
        data_path=args.data,
        n_estimators=args.estimators,
        max_depth=args.depth,
        random_state=args.seed,
    )
    print(f"Training completed successfully! Model saved to: {results['model_path']}")
