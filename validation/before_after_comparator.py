"""
validation/before_after_comparator.py
───────────────────────────────────────
Compares baseline vs. proposal-applied simulation metrics and produces
a structured before/after diff.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("before_after_comparator")


def compare(
    baseline_metrics: dict,
    proposal_metrics: dict,
    proposal_id: str,
    scenario_id: int,
) -> dict:
    """
    Compute absolute and percentage deltas for every shared KPI metric.

    Parameters
    ──────────
    baseline_metrics  : KPI dict from metrics_calculator for the baseline run.
    proposal_metrics  : KPI dict from metrics_calculator for the proposal run.
    proposal_id       : ID of the proposal being validated.
    scenario_id       : Scenario this comparison belongs to.

    Returns
    ───────
    {
      "proposal_id": str,
      "scenario_id": int,
      "compared_at": str,
      "verdict":     "APPROVED" | "APPROVED_WITH_CONDITIONS" | "REJECTED",
      "summary":     str,
      "metrics": {
        "<kpi_name>": {
          "before":   float,
          "after":    float,
          "delta":    float,
          "delta_pct": float,
          "improved": bool,
        }, ...
      },
      "improvement_score": float,   # 0–100, higher = better
    }
    """
    metric_keys = [
        "avg_travel_time_s", "avg_wait_time_s", "avg_speed_kph",
        "congestion_ratio", "total_delay_s", "emissions_proxy",
        "efficiency_score", "throughput_index", "p85_travel_time_s",
    ]
    # For these metrics, lower is better
    lower_is_better = {
        "avg_travel_time_s", "avg_wait_time_s", "congestion_ratio",
        "total_delay_s", "emissions_proxy", "p85_travel_time_s",
    }

    metrics_diff = {}
    improvement_signals = []

    for key in metric_keys:
        before = baseline_metrics.get(key, 0)
        after  = proposal_metrics.get(key, 0)
        delta  = after - before
        delta_pct = (delta / max(abs(before), 1e-6)) * 100

        # Is this an improvement?
        if key in lower_is_better:
            improved = delta < 0
        else:
            improved = delta > 0

        improvement_signals.append(1 if improved else 0)

        metrics_diff[key] = {
            "before":    round(before, 4),
            "after":     round(after, 4),
            "delta":     round(delta, 4),
            "delta_pct": round(delta_pct, 2),
            "improved":  improved,
        }

    # Score: fraction of metrics that improved, weighted by magnitude
    improvement_score = round(
        (sum(improvement_signals) / max(len(improvement_signals), 1)) * 100, 1
    )

    # Verdict
    eff_before = baseline_metrics.get("efficiency_score", 50)
    eff_after  = proposal_metrics.get("efficiency_score", 50)
    eff_delta  = eff_after - eff_before

    if eff_delta >= 3 and improvement_score >= 60:
        verdict = "APPROVED"
    elif eff_delta >= 0 and improvement_score >= 40:
        verdict = "APPROVED_WITH_CONDITIONS"
    else:
        verdict = "REJECTED"

    summary = (
        f"Proposal {proposal_id}: {verdict}. "
        f"Efficiency score changed from {eff_before:.1f} → {eff_after:.1f} "
        f"({eff_delta:+.1f} pts). "
        f"{sum(improvement_signals)}/{len(improvement_signals)} KPIs improved. "
        f"Improvement score: {improvement_score}/100."
    )
    log.info(summary)

    return {
        "proposal_id":       proposal_id,
        "scenario_id":       scenario_id,
        "compared_at":       datetime.now(timezone.utc).isoformat(),
        "verdict":           verdict,
        "summary":           summary,
        "metrics":           metrics_diff,
        "improvement_score": improvement_score,
    }
