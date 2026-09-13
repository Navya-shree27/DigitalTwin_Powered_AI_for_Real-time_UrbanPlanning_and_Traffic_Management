"""
ai/proposal_generator/zoning_proposer.py
─────────────────────────────────────────
Generates land-use renovation proposals for zones flagged as zoning_imbalance
by the ZoningAnalyzer.

For each flagged zone, the proposer:
  1. Reads the current area_by_type distribution.
  2. Simulates adding the complement land-use at a proposed fraction.
  3. Computes the new ENT after the proposed change.
  4. Returns a ProposalRecord dict compatible with the Proposal DB table.

Entropy equation (equ.md §5):
    ENT = -sum(P_i * ln(P_i)) / ln(k)

Improvement equation (equ.md §7):
    ΔM = (ENT_proposed - ENT_current) / ENT_max * 100
       = (ENT_proposed - ENT_current) * 100  (since ENT_max = 1.0)
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

log = logging.getLogger("zoning_proposer")

# Fraction of zone area to recommend converting to the complement use
# (conservative default: 20 %)
DEFAULT_CONVERT_FRACTION = 0.20

# Complement suggestions (mirrors zoning_analyzer to avoid circular imports)
COMPLEMENT_MAP = {
    "residential":   "commercial",
    "commercial":    "residential",
    "industrial":    "commercial",
    "retail":        "residential",
    "farmland":      "residential",
    "forest":        "recreation_ground",
    "meadow":        "park",
    "grass":         "park",
    "allotments":    "residential",
    "educational":   "commercial",
    "institutional": "residential",
    "civic":         "residential",
    "cemetery":      "park",
}

USE_LABELS = {
    "residential":       "Residential",
    "commercial":        "Commercial",
    "industrial":        "Industrial",
    "retail":            "Retail",
    "mixed":             "Mixed-Use",
    "civic":             "Civic / Government",
    "institutional":     "Institutional",
    "educational":       "Educational",
    "recreation_ground": "Recreation",
    "park":              "Park / Green",
    "cemetery":          "Cemetery",
    "farmland":          "Farmland",
    "forest":            "Forest",
    "meadow":            "Meadow",
    "grass":             "Grass / Open",
    "allotments":        "Allotments",
}


# ── Entropy helpers ───────────────────────────────────────────────────────────

def _entropy(area_by_type: dict[str, float]) -> float:
    """Normalized Shannon entropy (equ.md §5)."""
    positive = [a for a in area_by_type.values() if a > 0]
    if len(positive) <= 1:
        return 0.0
    total = sum(positive)
    proportions = [a / total for a in positive]
    raw = -sum(p * math.log(p) for p in proportions)
    return raw / math.log(len(proportions))


def _simulate_addition(
    area_by_type: dict[str, float],
    complement_use: str,
    convert_fraction: float,
) -> dict[str, float]:
    """
    Build a proposed area dict by converting `convert_fraction` of the
    zone total area to `complement_use`.
    """
    total = sum(a for a in area_by_type.values() if a > 0)
    proposed = dict(area_by_type)
    add_area = total * convert_fraction
    proposed[complement_use] = proposed.get(complement_use, 0.0) + add_area
    return proposed


# ── Proposal factory ──────────────────────────────────────────────────────────

def _make_proposal(
    proposal_id: str,
    issue_id: str,
    lat: float,
    lon: float,
    zone_idx: int,
    dominant_use: str,
    complement_use: str,
    current_ent: float,
    proposed_ent: float,
    convert_fraction: float,
    zone_area_m2: float,
    area_by_type: dict,
) -> dict:
    ent_gain   = round(proposed_ent - current_ent, 4)
    delta_pct  = round(ent_gain * 100, 2)   # equ.md §7 (increase direction)
    add_area   = round(zone_area_m2 * convert_fraction, 1)
    dominant_label   = USE_LABELS.get(dominant_use,   dominant_use)
    complement_label = USE_LABELS.get(complement_use, complement_use)

    description = (
        f"Zone {zone_idx}: current land-use entropy is low (ENT={current_ent:.2f}). "
        f"Converting ~{int(convert_fraction * 100)}% of zone area "
        f"({add_area:.0f} m²) from {dominant_label} to {complement_label} "
        f"is expected to raise ENT to {proposed_ent:.2f} (+{delta_pct:.1f}%)."
    )

    return {
        "proposal_id": proposal_id,
        "type":        "zoning",
        "subtype":     f"{dominant_use}_to_{complement_use}",
        "issue_id":    issue_id,
        "location": {
            "lat":      lat,
            "lon":      lon,
            "zone_idx": zone_idx,
        },
        "description": description,
        "parameters": {
            "dominant_use":          dominant_use,
            "dominant_use_label":    dominant_label,
            "complement_use":        complement_use,
            "complement_use_label":  complement_label,
            "current_ent":           round(current_ent, 4),
            "proposed_ent":          round(proposed_ent, 4),
            "area_fraction_to_convert": round(convert_fraction, 3),
            "area_to_convert_m2":    add_area,
            "zone_area_m2":          round(zone_area_m2, 1),
            "area_by_type_current":  {k: round(v, 1) for k, v in area_by_type.items()},
        },
        "expected_improvement": {
            "entropy_gain":      round(ent_gain, 4),
            "entropy_gain_pct":  delta_pct,
            "rationale": (
                f"Converting {int(convert_fraction * 100)}% of zone to {complement_label} "
                f"raises normalized land-use entropy from {current_ent:.2f} → {proposed_ent:.2f} "
                f"(equ.md §5 — Shannon entropy, §7 — ΔM improvement metric)."
            ),
            "equation_ref": "equ.md §5 (Land-Use Mix Entropy), §7 (Before/After ΔM)",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "validated":    False,
    }


# ── Main proposer class ───────────────────────────────────────────────────────

class ZoningProposer:
    """
    Generates zoning renovation proposals for zoning_imbalance issues.
    One proposal is produced per flagged zone.
    """

    def __init__(
        self,
        convert_fraction: float = DEFAULT_CONVERT_FRACTION,
    ):
        self.convert_fraction = convert_fraction

    def generate(self, issues: list[dict]) -> list[dict]:
        """
        Parameters
        ──────────
        issues : All detected issues — only zoning_imbalance entries are processed.

        Returns
        ───────
        List of ProposalRecord dicts.
        """
        proposals = []
        counter   = 0

        for issue in issues:
            if issue.get("type") != "zoning_imbalance":
                continue

            loc          = issue.get("location", {})
            metrics      = issue.get("metrics", {})
            lat          = loc.get("lat", 0.0)
            lon          = loc.get("lon", 0.0)
            zone_idx     = loc.get("zone_idx", 0)
            dominant_use = metrics.get("dominant_use", "residential")
            current_ent  = metrics.get("current_ent", 0.0)
            area_by_type = metrics.get("area_by_type", {})
            zone_area    = metrics.get("zone_area_m2", 0.0)
            complement   = metrics.get("complement_use") or COMPLEMENT_MAP.get(dominant_use, "commercial")

            if not area_by_type:
                continue

            # Simulate the proposed addition
            proposed_areas = _simulate_addition(area_by_type, complement, self.convert_fraction)
            proposed_ent   = _entropy(proposed_areas)

            # Only emit a proposal if it actually improves entropy
            if proposed_ent <= current_ent:
                log.debug(f"Zone {zone_idx}: proposed change does not improve ENT — skipping.")
                continue

            counter += 1
            proposals.append(_make_proposal(
                proposal_id      = f"zoning_{zone_idx}_{counter}",
                issue_id         = issue["issue_id"],
                lat              = lat,
                lon              = lon,
                zone_idx         = zone_idx,
                dominant_use     = dominant_use,
                complement_use   = complement,
                current_ent      = current_ent,
                proposed_ent     = proposed_ent,
                convert_fraction = self.convert_fraction,
                zone_area_m2     = zone_area,
                area_by_type     = area_by_type,
            ))

        log.info(f"ZoningProposer: {len(proposals)} zoning proposals generated.")
        return proposals


def generate_zoning_proposals(issues: list[dict], **kwargs) -> list[dict]:
    """Convenience wrapper."""
    return ZoningProposer(**kwargs).generate(issues)
