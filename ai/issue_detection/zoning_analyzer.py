"""
ai/issue_detection/zoning_analyzer.py
───────────────────────────────────────
Detects land-use imbalance (mono-use zoning) in city zones using the
normalized Shannon entropy index from published urban-planning research.

Equation (equ.md §5)
─────────────────────
    ENT = -sum(P_i * ln(P_i)) / ln(k)

Where:
    P_i = proportion of land-use type i in the zone.
    k   = number of distinct land-use types in the zone.

A zone with ENT < ENTROPY_THRESHOLD is flagged as a zoning_imbalance issue.

Data source: OSMnx geometries_from_place() with landuse tags.
If OSMnx or the landuse data is unavailable, the analyzer returns an
empty list so the rest of the pipeline is unaffected.

References
──────────
    - New Methods for Assessing Land Use (Entropy index).
    - The Hidden Characteristics of Land-Use Mix Indices.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

log = logging.getLogger("zoning_analyzer")

# ── Thresholds ────────────────────────────────────────────────────────────────
ENTROPY_THRESHOLD = 0.35   # Zones below this ENT are flagged as mono-use
ENTROPY_MODERATE  = 0.55   # Zones below this but above threshold = moderate

# Landuse tags OSM uses that we care about
RELEVANT_USES = {
    "residential", "commercial", "industrial", "retail",
    "mixed", "civic", "institutional", "educational",
    "recreation_ground", "park", "cemetery", "farmland",
    "forest", "meadow", "grass", "allotments",
}

# Human-readable labels for OSM landuse values
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

# Complement suggestions: given dominant use → what to add
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


# ── Entropy math (equ.md §5) ──────────────────────────────────────────────────

def land_use_entropy(area_by_type: dict[str, float]) -> float:
    """
    Compute normalized Shannon entropy for a set of land-use areas.

    Parameters
    ──────────
    area_by_type : {"residential": 4000, "commercial": 2000, ...}

    Returns
    ───────
    float in [0, 1].  0 = single-use.  1 = perfectly balanced.

    Source: equ.md §5 — Land-Use Mix Entropy.
    """
    positive = [a for a in area_by_type.values() if a > 0]
    if len(positive) <= 1:
        return 0.0

    total = sum(positive)
    proportions = [a / total for a in positive]

    raw_entropy = -sum(p * math.log(p) for p in proportions)
    return raw_entropy / math.log(len(proportions))


# ── Issue factory ─────────────────────────────────────────────────────────────

def _make_issue(
    issue_id: str,
    zone_idx: int,
    lat: float,
    lon: float,
    severity: str,
    dominant_use: str,
    current_ent: float,
    area_by_type: dict,
    zone_area_m2: float,
) -> dict:
    complement = COMPLEMENT_MAP.get(dominant_use, "commercial")
    description = (
        f"Zone {zone_idx} near ({lat:.4f}, {lon:.4f}) shows low land-use diversity "
        f"(ENT={current_ent:.2f}). Dominant use: {USE_LABELS.get(dominant_use, dominant_use)}. "
        f"Adding {USE_LABELS.get(complement, complement)} land use is recommended."
    )
    return {
        "issue_id":  issue_id,
        "type":      "zoning_imbalance",
        "severity":  severity,
        "location": {
            "lat":      lat,
            "lon":      lon,
            "zone_idx": zone_idx,
        },
        "metrics": {
            "current_ent":    round(current_ent, 4),
            "dominant_use":   dominant_use,
            "area_by_type":   {k: round(v, 1) for k, v in area_by_type.items()},
            "zone_area_m2":   round(zone_area_m2, 1),
            "complement_use": complement,
        },
        "description": description,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Main analyzer class ───────────────────────────────────────────────────────

class ZoningAnalyzer:
    """
    Downloads OSM landuse polygons for the loaded network's bounding box and
    computes per-zone entropy.  Zones below ENTROPY_THRESHOLD are flagged.
    """

    def __init__(
        self,
        entropy_threshold: float = ENTROPY_THRESHOLD,
        entropy_moderate: float  = ENTROPY_MODERATE,
    ):
        self.entropy_threshold = entropy_threshold
        self.entropy_moderate  = entropy_moderate

    def analyze(self, telemetry: dict, scenario_id: int | None = None) -> list[dict]:
        """
        Run zoning entropy analysis.

        Parameters
        ──────────
        telemetry   : Standard simulation telemetry dict (used for bbox).
        scenario_id : Optional — used in issue IDs.

        Returns
        ───────
        List of IssueRecord dicts with type="zoning_imbalance".
        """
        # Derive bounding box from node telemetry
        nodes = telemetry.get("nodes", [])
        if not nodes:
            log.warning("ZoningAnalyzer: no nodes in telemetry — skipping.")
            return []

        lats = [n["lat"] for n in nodes if "lat" in n]
        lons = [n["lon"] for n in nodes if "lon" in n]
        if not lats or not lons:
            return []

        north, south = max(lats), min(lats)
        east,  west  = max(lons), min(lons)
        bbox = (north, south, east, west)   # OSMnx order

        # Download landuse geometries
        gdf = self._fetch_landuse(bbox)
        if gdf is None or gdf.empty:
            log.info("ZoningAnalyzer: no landuse data available — returning empty.")
            return []

        # Cluster polygons into zones (~500 m grid) and compute entropy per zone
        issues = self._detect_zones(gdf, scenario_id or 0)
        log.info(
            f"ZoningAnalyzer: {len(issues)} zoning_imbalance issues "
            f"detected (threshold ENT<{self.entropy_threshold})."
        )
        return issues

    # ── Private helpers ───────────────────────────────────────────────────────

    def _fetch_landuse(self, bbox: tuple[float, float, float, float]):
        """Download landuse GeoDataFrame. Returns None on any error."""
        try:
            import osmnx as ox
        except ImportError:
            log.warning("OSMnx not installed — zoning analysis unavailable.")
            return None

        try:
            north, south, east, west = bbox
            gdf = ox.features_from_bbox(
                bbox=(north, south, east, west),
                tags={"landuse": True},
            )
            # Filter to relevant polygon features only
            gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
            gdf["landuse"] = gdf.get("landuse", "").fillna("").astype(str)
            gdf = gdf[gdf["landuse"].isin(RELEVANT_USES)]
            # Project to local UTM so we can compute area in m²
            gdf = gdf.to_crs(gdf.estimate_utm_crs())
            gdf["area_m2"] = gdf.geometry.area
            # Back to WGS84 for centroids
            gdf_wgs = gdf.to_crs(epsg=4326)
            gdf["centroid_lat"] = gdf_wgs.geometry.centroid.y
            gdf["centroid_lon"] = gdf_wgs.geometry.centroid.x
            return gdf
        except Exception as exc:
            log.warning(f"ZoningAnalyzer._fetch_landuse error: {exc}")
            return None

    def _detect_zones(self, gdf, scenario_id: int) -> list[dict]:
        """
        Grid the landuse polygons into 500 m² cells and compute entropy per cell.
        Returns issue records for cells with ENT below the threshold.
        """
        try:
            import numpy as np
        except ImportError:
            return []

        lats = gdf["centroid_lat"].values
        lons = gdf["centroid_lon"].values

        if len(lats) == 0:
            return []

        # Simple 0.005° grid (~500 m at equatorial latitudes)
        CELL = 0.005
        min_lat = lats.min(); max_lat = lats.max()
        min_lon = lons.min(); max_lon = lons.max()

        issues = []
        zone_idx = 0

        lat_bins = [min_lat + i * CELL for i in range(int((max_lat - min_lat) / CELL) + 2)]
        lon_bins = [min_lon + i * CELL for i in range(int((max_lon - min_lon) / CELL) + 2)]

        for i in range(len(lat_bins) - 1):
            for j in range(len(lon_bins) - 1):
                lat0, lat1 = lat_bins[i], lat_bins[i + 1]
                lon0, lon1 = lon_bins[j], lon_bins[j + 1]

                mask = (
                    (lats >= lat0) & (lats < lat1) &
                    (lons >= lon0) & (lons < lon1)
                )
                cell_gdf = gdf[mask]
                if cell_gdf.empty:
                    continue

                # Sum area by land use type
                area_by_type: dict[str, float] = {}
                for _, row in cell_gdf.iterrows():
                    use  = row["landuse"]
                    area = row["area_m2"]
                    area_by_type[use] = area_by_type.get(use, 0.0) + area

                if len(area_by_type) == 0:
                    continue

                ent = land_use_entropy(area_by_type)

                if ent >= self.entropy_moderate:
                    continue  # Healthy zone — skip

                severity = "severe" if ent < self.entropy_threshold else "moderate"

                dominant_use = max(area_by_type, key=area_by_type.get)
                zone_center_lat = (lat0 + lat1) / 2
                zone_center_lon = (lon0 + lon1) / 2
                zone_area = sum(area_by_type.values())

                zone_idx += 1
                issues.append(_make_issue(
                    issue_id    = f"zone_{scenario_id}_{zone_idx}",
                    zone_idx    = zone_idx,
                    lat         = zone_center_lat,
                    lon         = zone_center_lon,
                    severity    = severity,
                    dominant_use= dominant_use,
                    current_ent = ent,
                    area_by_type= area_by_type,
                    zone_area_m2= zone_area,
                ))

        return issues


def detect_zoning_issues(telemetry: dict, scenario_id: int = 0, **kwargs) -> list[dict]:
    """Convenience wrapper."""
    return ZoningAnalyzer(**kwargs).analyze(telemetry, scenario_id=scenario_id)
