"""
validation/before_after_comparator.py
───────────────────────────────────────
Compares baseline vs. proposal-applied simulation metrics and produces
a structured before/after diff.

Equations used (all from equ.md)
─────────────────────────────────
  §7  ΔM = (M_baseline - M_proposed) / M_baseline × 100   (decrease metrics)
      ΔM = (M_proposed - M_baseline) / M_baseline × 100   (increase metrics)

  §3  Queue-reduction reward:
        r_t = α_abs(-Q_curr / N·Q_norm) + α_red(ΔQ / N·Q_norm)
        α_abs = 0.4,  α_red = 0.6

  §9  Acceptance rule:
        delay_reduction ≥ 5%
        queue_increase  ≤ 5%
        throughput_change ≥ -2%
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger("before_after_comparator")

# §3 RL reward coefficients (published values)
ALPHA_ABS = 0.4
ALPHA_RED = 0.6

# §9 Policy acceptance thresholds
MIN_DELAY_REDUCTION   = 0.05   # 5 % relative delay reduction
MAX_QUEUE_INCREASE    = 0.05   # 5 % relative queue increase
MIN_THROUGHPUT_CHANGE = -0.02  # throughput must not fall more than 2 %


# ── equ.md §7 ─────────────────────────────────────────────────────────────────

def percent_improvement(baseline: float, proposed: float, direction: str = "decrease") -> float:
    """
    Directional percent improvement (equ.md §7).

    direction='decrease' : metrics that should go down (delay, queue, travel time)
        ΔM = (M_baseline - M_proposed) / M_baseline × 100

    direction='increase' : metrics that should go up (speed, throughput)
        ΔM = (M_proposed - M_baseline) / M_baseline × 100
    """
    if baseline == 0:
        return 0.0
    if direction == "decrease":
        return ((baseline - proposed) / abs(baseline)) * 100
    if direction == "increase":
        return ((proposed - baseline) / abs(baseline)) * 100
    raise ValueError("direction must be 'decrease' or 'increase'")


# ── equ.md §3 ─────────────────────────────────────────────────────────────────

def queue_reduction_reward(
    baseline_queue: float,
    proposed_queue: float,
    q_norm: float,
    n_approaches: int = 1,
    alpha_abs: float = ALPHA_ABS,
    alpha_red: float = ALPHA_RED,
) -> float:
    """
    Published RL queue-reduction reward (equ.md §3).

        r_t = α_abs × (-Q_curr / N·Q_norm) + α_red × (ΔQ / N·Q_norm)
        α_abs = 0.4,  α_red = 0.6

    Here we treat the entire network as one zone (N=1) and use the
    baseline queue as Q_norm (the normalisation reference).

    Returns value in [-1, +1] range (positive = improvement).
    """
    n = max(n_approaches, 1)
    q_norm = max(q_norm, 1e-6)
    absolute_penalty = -(proposed_queue / (n * q_norm))
    reduction_reward = (baseline_queue - proposed_queue) / (n * q_norm)
    return round(alpha_abs * absolute_penalty + alpha_red * reduction_reward, 6)


# ── equ.md §9 ─────────────────────────────────────────────────────────────────

def renovation_is_acceptable(
    baseline_delay: float,
    proposed_delay: float,
    baseline_queue: float,
    proposed_queue: float,
    baseline_throughput: float,
    proposed_throughput: float,
    minimum_delay_reduction: float   = MIN_DELAY_REDUCTION,
    maximum_queue_increase:  float   = MAX_QUEUE_INCREASE,
    minimum_throughput_change: float = MIN_THROUGHPUT_CHANGE,
) -> bool:
    """
    Conservative acceptance rule (equ.md §9).

    A renovation is acceptable only when it:
      1. Reduces delay by at least minimum_delay_reduction (default 5 %)
      2. Does not increase queue by more than maximum_queue_increase (default 5 %)
      3. Does not drop throughput by more than |minimum_throughput_change| (default 2 %)

    The thresholds are project policy — not universal constants.
    """
    if baseline_delay <= 0 or baseline_queue < 0 or baseline_throughput <= 0:
        return False
    delay_change      = (baseline_delay     - proposed_delay)      / baseline_delay
    queue_change      = (proposed_queue     - baseline_queue)       / max(baseline_queue, 1e-6)
    throughput_change = (proposed_throughput - baseline_throughput) / baseline_throughput
    return (
        delay_change      >= minimum_delay_reduction
        and queue_change  <= maximum_queue_increase
        and throughput_change >= minimum_throughput_change
    )


# ── Main comparison function ───────────────────────────────────────────────────

def compare(
    baseline_metrics: dict,
    proposal_metrics: dict,
    proposal_id: str,
    scenario_id: int,
) -> dict:
    """
    Compute absolute and percentage deltas for every shared KPI metric.

    Uses equ.md §7 for all percent-improvement calculations.
    Uses equ.md §3 for queue-reduction reward.
    Uses equ.md §9 for the APPROVED / APPROVED_WITH_CONDITIONS / REJECTED verdict.

    Parameters
    ──────────
    baseline_metrics  : KPI dict from metrics_calculator for the baseline run.
    proposal_metrics  : KPI dict from metrics_calculator for the proposal run.
    proposal_id       : ID of the proposal being validated.
    scenario_id       : Scenario this comparison belongs to.

    Returns
    ───────
    {
      "proposal_id":   str,
      "scenario_id":   int,
      "compared_at":   str,
      "verdict":       "APPROVED" | "APPROVED_WITH_CONDITIONS" | "REJECTED",
      "summary":       str,
      "improvement_score": float,   # 0–100
      "queue_reduction_reward": float,  # equ.md §3
      "metrics": {
        "<kpi_name>": {
          "before":    float,
          "after":     float,
          "delta":     float,
          "delta_pct": float,   # uses equ.md §7
          "improved":  bool,
        }, ...
      },
    }
    """
    # Metrics where lower = better → use "decrease" direction in §7
    lower_is_better = {
        "avg_travel_time_s", "avg_wait_time_s", "congestion_ratio",
        "total_delay_s", "emissions_proxy", "p85_travel_time_s",
        "avg_delay_s", "noise_pollution_db",
        "weighted_intersection_delay",   # equ.md §1 — lower is better
    }
    # Metrics where higher = better → use "increase" direction in §7
    higher_is_better = {
        "avg_speed_kph", "throughput_index", "efficiency_score",
        "total_flow_veh_h",
        "delay_entropy",  # equ.md §2 — more balanced = better
    }

    metric_keys = list(lower_is_better | higher_is_better)

    metrics_diff: dict = {}
    improvement_signals: list[int] = []

    for key in metric_keys:
        before = baseline_metrics.get(key, 0) or 0
        after  = proposal_metrics.get(key, 0)  or 0
        delta  = after - before

        if key in lower_is_better:
            direction = "decrease"
            improved  = delta < 0
        else:
            direction = "increase"
            improved  = delta > 0

        # §7 — directional percent improvement
        delta_pct = percent_improvement(before, after, direction=direction)

        improvement_signals.append(1 if improved else 0)

        metrics_diff[key] = {
            "before":    round(before, 4),
            "after":     round(after, 4),
            "delta":     round(delta, 4),
            "delta_pct": round(delta_pct, 2),
            "improved":  improved,
            "equation":  "equ.md §7",
        }

    # §3 — Queue-reduction reward
    baseline_q  = baseline_metrics.get("avg_delay_s", 0) or 0
    proposed_q  = proposal_metrics.get("avg_delay_s",  0) or 0
    q_reward    = queue_reduction_reward(baseline_q, proposed_q, q_norm=max(baseline_q, 1.0))

    # Improvement score: fraction of metrics improved × 100
    improvement_score = round(
        (sum(improvement_signals) / max(len(improvement_signals), 1)) * 100, 1
    )

    # §9 — Acceptance rule determines verdict
    eff_before   = baseline_metrics.get("efficiency_score", 50) or 50
    eff_after    = proposal_metrics.get("efficiency_score",  50) or 50
    eff_delta    = eff_after - eff_before

    b_delay      = baseline_metrics.get("avg_delay_s",       0) or 0
    p_delay      = proposal_metrics.get("avg_delay_s",       0) or 0
    b_queue      = baseline_metrics.get("total_delay_s",     0) or 0
    p_queue      = proposal_metrics.get("total_delay_s",     0) or 0
    b_throughput = baseline_metrics.get("throughput_index",  1) or 1
    p_throughput = proposal_metrics.get("throughput_index",  1) or 1

    if renovation_is_acceptable(b_delay, p_delay, b_queue, p_queue, b_throughput, p_throughput):
        verdict = "APPROVED"
    elif eff_delta >= 0 and improvement_score >= 40:
        verdict = "APPROVED_WITH_CONDITIONS"
    else:
        verdict = "REJECTED"

    summary = (
        f"Proposal {proposal_id}: {verdict}. "
        f"Efficiency {eff_before:.1f} → {eff_after:.1f} ({eff_delta:+.1f} pts). "
        f"{sum(improvement_signals)}/{len(improvement_signals)} KPIs improved. "
        f"Score: {improvement_score}/100. "
        f"Queue-reduction reward (equ.md §3): {q_reward:+.4f}."
    )
    log.info(summary)

    return {
        "proposal_id":         proposal_id,
        "scenario_id":         scenario_id,
        "compared_at":         datetime.now(timezone.utc).isoformat(),
        "verdict":             verdict,
        "summary":             summary,
        "improvement_score":   improvement_score,
        "queue_reduction_reward": q_reward,  # equ.md §3
        "metrics":             metrics_diff,
        "equation_refs": {
            "delta_pct":      "equ.md §7 — Before/After ΔM",
            "queue_reward":   "equ.md §3 — Queue-Reduction Reward",
            "verdict_rule":   "equ.md §9 — Acceptance Rule",
        },
    }
