"""
ml/evaluate.py
───────────────
Model Evaluation & Metrics Generation.

Evaluates the persisted model on unseen test data, computes real metrics
(Accuracy, Precision, Recall, F1, Confusion Matrix), saves structured metrics
to results/model_metrics.json, and produces evaluation plots.

Usage:
──────
    python -m ml.evaluate
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import joblib
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from ml.preprocess import TrafficPreprocessor, prepare_train_test_data

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
log = logging.getLogger("ml_evaluate")

CLASS_NAMES = ["Low", "Moderate", "Severe"]


def evaluate_model(
    model_path: Path | str = MODELS_DIR / "traffic_model.joblib",
    preprocessor_path: Path | str = MODELS_DIR / "preprocessor.joblib",
    data_path: Path | str = DATA_PATH,
    results_dir: Path | str = RESULTS_DIR,
    random_state: int = 42,
) -> dict[str, Any]:
    """
    Run evaluation on the unseen test set and output genuine metrics.
    """
    m_path = Path(model_path)
    p_path = Path(preprocessor_path)
    d_path = Path(data_path)
    r_dir = Path(results_dir)
    r_dir.mkdir(parents=True, exist_ok=True)

    if not m_path.exists() or not p_path.exists():
        raise FileNotFoundError(f"Model or preprocessor missing. Please run `python -m ml.train_model` first.")

    log.info(f"Loading model from {m_path}...")
    model = joblib.load(m_path)
    preprocessor = TrafficPreprocessor.load(p_path)

    log.info(f"Loading evaluation dataset from {d_path}...")
    df = pd.read_csv(d_path)

    # Use identical split method to extract test partition
    data_split = prepare_train_test_data(df, test_size=0.20, val_size=0.10, random_state=random_state)
    test_df = data_split["test_df"]
    X_test = preprocessor.transform(test_df)
    y_test = data_split["y_test"]

    log.info(f"Evaluating on {len(X_test):,} unseen test samples...")
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test) if hasattr(model, "predict_proba") else None

    # Calculate metrics
    acc = float(accuracy_score(y_test, y_pred))
    p_macro = float(precision_score(y_test, y_pred, average="macro", zero_division=0))
    p_weighted = float(precision_score(y_test, y_pred, average="weighted", zero_division=0))
    r_macro = float(recall_score(y_test, y_pred, average="macro", zero_division=0))
    r_weighted = float(recall_score(y_test, y_pred, average="weighted", zero_division=0))
    f1_mac = float(f1_score(y_test, y_pred, average="macro", zero_division=0))
    f1_wt = float(f1_score(y_test, y_pred, average="weighted", zero_division=0))

    cm = confusion_matrix(y_test, y_pred)
    cls_report = classification_report(y_test, y_pred, target_names=CLASS_NAMES, output_dict=True)

    log.info(f"=== TEST SET EVALUATION RESULTS ===")
    log.info(f"Accuracy:           {acc:.4f} ({acc*100:.2f}%)")
    log.info(f"Precision (Macro):  {p_macro:.4f}")
    log.info(f"Recall (Macro):     {r_macro:.4f}")
    log.info(f"F1-Score (Macro):   {f1_mac:.4f}")
    log.info(f"F1-Score (Weighted):{f1_wt:.4f}")

    # Extract feature importances
    feature_importances = {}
    if hasattr(model, "feature_importances_"):
        names = preprocessor.feature_names_
        raw_fi = model.feature_importances_
        sorted_fi = sorted(zip(names, raw_fi), key=lambda x: x[1], reverse=True)
        feature_importances = {name: round(float(val), 5) for name, val in sorted_fi}

    # Save metrics JSON
    metrics_payload = {
        "evaluation_timestamp": pd.Timestamp.now().isoformat(),
        "model_type": type(model).__name__,
        "dataset_type": "SYNTHETIC_SIMULATION_DATA",
        "num_test_samples": int(len(y_test)),
        "num_classes": len(CLASS_NAMES),
        "class_names": CLASS_NAMES,
        "metrics": {
            "accuracy": round(acc, 4),
            "precision_macro": round(p_macro, 4),
            "precision_weighted": round(p_weighted, 4),
            "recall_macro": round(r_macro, 4),
            "recall_weighted": round(r_weighted, 4),
            "f1_score_macro": round(f1_mac, 4),
            "f1_score_weighted": round(f1_wt, 4),
        },
        "per_class_metrics": {
            k: {
                "precision": round(v.get("precision", 0), 4),
                "recall": round(v.get("recall", 0), 4),
                "f1_score": round(v.get("f1-score", 0), 4),
                "support": int(v.get("support", 0)),
            }
            for k, v in cls_report.items()
            if k in CLASS_NAMES
        },
        "confusion_matrix": cm.tolist(),
        "top_features": dict(list(feature_importances.items())[:10]),
    }

    metrics_file = r_dir / "model_metrics.json"
    metrics_file.write_text(json.dumps(metrics_payload, indent=2))
    log.info(f"Saved evaluation metrics to: {metrics_file}")

    # Plot Confusion Matrix
    cm_plot_file = r_dir / "confusion_matrix.png"
    plt.figure(figsize=(7, 6))
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=CLASS_NAMES,
        yticklabels=CLASS_NAMES,
        cbar=False,
    )
    plt.title(f"Confusion Matrix — Traffic Congestion Model\n(Accuracy: {acc*100:.1f}%, F1: {f1_mac:.3f})")
    plt.xlabel("Predicted Class")
    plt.ylabel("Ground Truth Class")
    plt.tight_layout()
    plt.savefig(cm_plot_file, dpi=200)
    plt.close()
    log.info(f"Saved confusion matrix plot to: {cm_plot_file}")

    # Plot Feature Importances
    if feature_importances:
        fi_plot_file = r_dir / "feature_importance.png"
        top_10 = list(feature_importances.items())[:10]
        f_names = [x[0] for x in top_10][::-1]
        f_vals = [x[1] for x in top_10][::-1]

        plt.figure(figsize=(9, 6))
        plt.barh(f_names, f_vals, color="#3b82f6")
        plt.title("Top 10 Feature Importances — Congestion Prediction")
        plt.xlabel("Gini Feature Importance")
        plt.tight_layout()
        plt.savefig(fi_plot_file, dpi=200)
        plt.close()
        log.info(f"Saved feature importance plot to: {fi_plot_file}")

    return metrics_payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate traffic machine learning model on test set.")
    parser.add_argument("--model", type=str, default=str(MODELS_DIR / "traffic_model.joblib"))
    parser.add_argument("--preprocessor", type=str, default=str(MODELS_DIR / "preprocessor.joblib"))
    parser.add_argument("--data", type=str, default=str(DATA_PATH))
    args = parser.parse_args()

    res = evaluate_model(model_path=args.model, preprocessor_path=args.preprocessor, data_path=args.data)
    print("\n" + "="*50)
    print(f"Model Evaluation Complete:")
    print(f"  Accuracy:  {res['metrics']['accuracy'] * 100:.2f}%")
    print(f"  Macro F1:  {res['metrics']['f1_score_macro']:.4f}")
    print(f"  Results in results/model_metrics.json")
    print("="*50 + "\n")
