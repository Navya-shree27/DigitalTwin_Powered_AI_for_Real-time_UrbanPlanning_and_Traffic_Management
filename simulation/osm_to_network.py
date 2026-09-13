"""
simulation/osm_to_network.py
────────────────────────────
Downloads OpenStreetMap road-network data for the configured city area using
OSMnx, cleans it, enriches it with basic traffic attributes, and saves the
result as:
  • GeoJSON  → data/processed/network/network.geojson   (for the frontend map)
  • GraphML  → data/processed/network/network.graphml   (for Python graph ops)
  • JSON     → data/processed/network/network_meta.json (metadata / stats)

The downloaded raw OSM data is cached in data/raw/osm/ so subsequent runs
do not hit the Overpass API again.

Usage
─────
    python simulation/osm_to_network.py                    # uses .env settings
    python simulation/osm_to_network.py --city "Hubballi, Karnataka, India"
    python simulation/osm_to_network.py --bbox 14.43 75.90 14.49 75.95
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import networkx as nx
try:
    import osmnx as ox
except ImportError:
    ox = None

import pandas as pd
from dotenv import load_dotenv

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

RAW_DIR = ROOT / "data" / "raw" / "osm"
PROCESSED_DIR = ROOT / "data" / "processed" / "network"
CACHE_DIR = ROOT / "data" / "cache"

for d in (RAW_DIR, PROCESSED_DIR, CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("osm_to_network")


# ─────────────────────────────────────────────────────────────────────────────
# OSMnx configuration
# ─────────────────────────────────────────────────────────────────────────────

def _configure_osmnx() -> None:
    """Apply project-wide OSMnx settings."""
    if ox is None:
        raise RuntimeError(
            "OSMnx is not installed in the active Python environment. "
            "Please run the server inside the virtual environment: .\\venv\\Scripts\\Activate.ps1 "
            "or install osmnx using 'pip install osmnx'."
        )
    ox.settings.log_console = False
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(CACHE_DIR)
    ox.settings.timeout = 90
    ox.settings.overpass_endpoint = "https://overpass.kumi.systems/api/interpreter"
    ox.settings.memory = None  # use default memory


# ─────────────────────────────────────────────────────────────────────────────
# Download helpers
# ─────────────────────────────────────────────────────────────────────────────

def download_by_place(place_name: str) -> nx.MultiDiGraph:
    """Download the drivable road network for *place_name*."""
    # Normalize place name
    norm_name = place_name.lower().strip()
    if norm_name in ["bengaluru", "bangalore", "bengaluru, karnataka, india", "bangalore, karnataka, india"]:
        place_name = "Indiranagar, Bengaluru, Karnataka, India"
        log.info(f"Metropolitan query redirected to sub-district: {place_name!r} to avoid timeouts")

    log.info(f"Downloading road network for: {place_name!r}")

    # 1. Resolve exact coordinates via Google Maps Geocoding
    try:
        from backend.services import google_maps_service
        geo = google_maps_service.geocode_place(place_name)
        if geo.get("is_live_data") and geo.get("center"):
            lat = geo["center"]["lat"]
            lon = geo["center"]["lon"]
            log.info(f"Downloading road network via Google Maps Geocoded point: ({lat}, {lon}) with dist=1800m")
            G = ox.graph_from_point(
                (lat, lon),
                dist=1800,
                network_type="drive",
                simplify=True,
                retain_all=False
            )
            log.info(f"Downloaded graph — nodes: {G.number_of_nodes():,}, edges: {G.number_of_edges():,}")
            return G
    except Exception as geo_err:
        log.warning(f"Google Maps geocoded point download failed: {geo_err}. Trying standard place query...")

    # 2. Try standard graph_from_place
    try:
        G = ox.graph_from_place(
            place_name,
            network_type="drive",
            simplify=True,
            retain_all=False,
        )
        log.info(f"Downloaded graph — nodes: {G.number_of_nodes():,}, edges: {G.number_of_edges():,}")
        return G
    except Exception as err:
        log.warning(f"ox.graph_from_place({place_name!r}) failed: {err}. Trying OSMnx geocode point...")

    # 3. Final attempt: try OSMnx geocode to point
    try:
        point = ox.geocode(place_name)
        log.info(f"Downloading road network via OSMnx geocoded point: {point} with dist=1800m")
        G = ox.graph_from_point(point, dist=1800, network_type="drive", simplify=True, retain_all=False)
        log.info(f"Downloaded graph — nodes: {G.number_of_nodes():,}, edges: {G.number_of_edges():,}")
        return G
    except Exception as final_err:
        raise RuntimeError(f"Could not build road network for '{place_name}': {final_err}")


def download_by_bbox(
    north: float, south: float, east: float, west: float
) -> nx.MultiDiGraph:
    """Download the drivable road network within a bounding box."""
    log.info(f"Downloading road network for bbox N{north} S{south} E{east} W{west}")
    try:
        G = ox.graph_from_bbox(
            bbox=(north, south, east, west),
            network_type="drive",
            simplify=True,
            retain_all=False,
        )
    except TypeError:
        try:
            G = ox.graph_from_bbox(
                north=north, south=south, east=east, west=west,
                network_type="drive",
                simplify=True,
                retain_all=False,
            )
        except TypeError:
            G = ox.graph_from_bbox(
                north, south, east, west,
                network_type="drive",
                simplify=True,
                retain_all=False,
            )
    log.info(f"Downloaded graph — nodes: {G.number_of_nodes():,}, edges: {G.number_of_edges():,}")
    return G


# ─────────────────────────────────────────────────────────────────────────────
# Graph enrichment
# ─────────────────────────────────────────────────────────────────────────────

def _detect_building_constraints(G: nx.MultiDiGraph, city: str | None = None, bbox: tuple | None = None) -> None:
    """
    Check building proximity to road edges using OSMnx features.
    If a building footprint is within 5 meters of the road center line,
    flag the edge with data["widenable"] = False.
    """
    log.info("Checking building proximity and road widening constraints …")

    # Initialize all edges to widenable=True by default
    for u, v, k, data in G.edges(data=True, keys=True):
        data["widenable"] = True

    try:
        from shapely.geometry import box
        # Query bounding box
        nodes_gdf = ox.graph_to_gdfs(G, nodes=True, edges=False)
        minx, miny, maxx, maxy = nodes_gdf.total_bounds

        log.info(f"Querying building shapes from OSM for bbox: {miny:.4f}, {minx:.4f}, {maxy:.4f}, {maxx:.4f}")

        # Limit large area queries to prevent Overpass timeouts
        area_deg = (maxx - minx) * (maxy - miny)
        if area_deg > 0.06:
            raise ValueError("Area too large for building queries (> 25 sq km).")

        buildings = ox.features_from_bbox(
            north=maxy + 0.001,
            south=miny - 0.001,
            east=maxx + 0.001,
            west=minx - 0.001,
            tags={"building": True}
        )

        if buildings.empty:
            raise ValueError("No buildings found in bbox.")

        # Project both to local UTM for metric distance comparison
        G_proj = ox.project_graph(G)
        gdf_edges_proj = ox.graph_to_gdfs(G_proj, nodes=False, edges=True)
        buildings_proj = buildings.to_crs(gdf_edges_proj.crs)

        unwidenable_count = 0
        for idx, row in gdf_edges_proj.iterrows():
            edge_geom = row.geometry
            # Check for buildings within 5m buffer
            buffered_edge = edge_geom.buffer(5.0)
            candidates = buildings_proj.sindex.query(buffered_edge, predicate="intersects")
            if len(candidates) > 0:
                u, v, k = idx
                G[u][v][k]["widenable"] = False
                unwidenable_count += 1

        log.info(f"Detected building constraints: {unwidenable_count} / {G.number_of_edges()} edges are unwidenable.")

    except Exception as e:
        log.info(f"Could not check building footprints ({e}). Applying structural heuristic constraints.")
        # Fallback to realistic heuristics (residential/living streets are built up)
        unwidenable_count = 0
        import random
        rng = random.Random(42)
        for u, v, k, data in G.edges(data=True, keys=True):
            hw = data.get("road_type", "unclassified")
            if hw in ["residential", "living_street", "service"]:
                widenable = rng.random() > 0.85
            elif hw in ["tertiary", "secondary"]:
                widenable = rng.random() > 0.60
            else:
                widenable = True
            data["widenable"] = widenable
            if not widenable:
                unwidenable_count += 1
        log.info(f"Heuristic constraints applied: {unwidenable_count} / {G.number_of_edges()} edges are unwidenable.")


def enrich_graph(
    G: nx.MultiDiGraph,
    city: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> nx.MultiDiGraph:
    """
    Add / normalise traffic-relevant attributes on every edge:
      - speed_kph       free-flow speed (km/h)
      - travel_time     free-flow travel time (s)
      - lanes           number of lanes (defaults to 1)
      - capacity        estimated vehicles/hour (lanes × 1800)
      - road_type       simplified highway type string
      - widenable       boolean spatial building constraint
    """
    log.info("Enriching graph with traffic attributes …")

    G = ox.add_edge_speeds(G)      # infers speed_kph from OSM maxspeed / highway type
    G = ox.add_edge_travel_times(G)  # travel_time from length / speed_kph

    highway_capacity = {
        "motorway": 2200, "trunk": 1800, "primary": 1400,
        "secondary": 1000, "tertiary": 700, "residential": 400,
        "unclassified": 500, "living_street": 200,
    }

    for u, v, k, data in G.edges(data=True, keys=True):
        # Lanes
        raw_lanes = data.get("lanes", 1)
        if isinstance(raw_lanes, list):
            raw_lanes = raw_lanes[0]
        try:
            lanes = int(raw_lanes)
        except (TypeError, ValueError):
            lanes = 1
        data["lanes"] = max(1, lanes)

        # Road type
        hw = data.get("highway", "unclassified")
        if isinstance(hw, list):
            hw = hw[0]
        data["road_type"] = str(hw)

        # Capacity
        base_cap = highway_capacity.get(hw, 600)
        data["capacity"] = base_cap * data["lanes"]

    # Detect building constraints (Phase B/C feature)
    _detect_building_constraints(G, city, bbox)

    log.info("Graph enrichment complete.")
    return G


# ─────────────────────────────────────────────────────────────────────────────
# Export helpers
# ─────────────────────────────────────────────────────────────────────────────

def save_graphml(G: nx.MultiDiGraph, path: Path) -> None:
    ox.save_graphml(G, filepath=str(path))
    log.info(f"Saved GraphML → {path}")


def save_geojson(G: nx.MultiDiGraph, path: Path) -> None:
    """Save edges as GeoJSON (line geometries) for frontend rendering."""
    gdf_edges = ox.graph_to_gdfs(G, nodes=False, edges=True)
    gdf_edges = gdf_edges.reset_index()

    # Keep only serialisable columns
    keep_cols = [
        "geometry", "name", "highway", "road_type",
        "lanes", "length", "speed_kph", "travel_time", "capacity",
        "oneway", "u", "v", "key", "widenable",
    ]
    cols = [c for c in keep_cols if c in gdf_edges.columns]
    gdf_edges = gdf_edges[cols]

    # Stringify list-valued columns
    for col in gdf_edges.columns:
        if col == "geometry":
            continue
        gdf_edges[col] = gdf_edges[col].apply(
            lambda x: x[0] if isinstance(x, list) else x
        )

    gdf_edges.to_file(str(path), driver="GeoJSON")
    log.info(f"Saved GeoJSON  → {path}")


def save_nodes_geojson(G: nx.MultiDiGraph, path: Path) -> None:
    """Save nodes as GeoJSON (point geometries) for intersection markers.

    Includes OSM tags that are needed by the frontend:
      - osmid, geometry, street_count  — always present
      - highway     — 'traffic_signals' for signalized intersections
      - designation — named junction identifier (e.g. 'Aruna Theatre Junction')
      - name        — fallback display name
    """
    gdf_nodes = ox.graph_to_gdfs(G, nodes=True, edges=False).reset_index()

    # Base columns always exported
    cols = ["osmid", "geometry", "street_count"]

    # Optional OSM tag columns — include if present in the dataset
    for optional_col in ("highway", "designation", "name", "ref"):
        if optional_col in gdf_nodes.columns:
            cols.append(optional_col)

    gdf_nodes = gdf_nodes[cols]

    # Stringify list-valued columns (OSMnx sometimes returns lists for multi-value tags)
    for col in gdf_nodes.columns:
        if col == "geometry":
            continue
        gdf_nodes[col] = gdf_nodes[col].apply(
            lambda x: x[0] if isinstance(x, list) else x
        )

    gdf_nodes.to_file(str(path), driver="GeoJSON")
    log.info(f"Saved nodes GeoJSON → {path}  ({len(gdf_nodes)} nodes, "
             f"{(gdf_nodes.get('highway', pd.Series()) == 'traffic_signals').sum()} traffic signals)")


def save_metadata(G: nx.MultiDiGraph, path: Path, source: str) -> dict:
    """Save a JSON metadata file with graph statistics."""
    nodes_gdf, edges_gdf = ox.graph_to_gdfs(G)
    meta = {
        "source": source,
        "generated_at": pd.Timestamp.now().isoformat(),
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "total_length_km": round(edges_gdf["length"].sum() / 1000, 2),
        "avg_speed_kph": round(edges_gdf["speed_kph"].mean(), 1),
        "bbox": {
            "north": float(nodes_gdf.geometry.y.max()),
            "south": float(nodes_gdf.geometry.y.min()),
            "east":  float(nodes_gdf.geometry.x.max()),
            "west":  float(nodes_gdf.geometry.x.min()),
        },
        "crs": "EPSG:4326",
    }
    path.write_text(json.dumps(meta, indent=2))
    log.info(f"Saved metadata  → {path}")
    return meta


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def build_network(
    city: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    force_rebuild: bool = False,
    scenario_id: int | None = None,
) -> dict:
    """
    High-level function: download, enrich, and save the road network.
    Returns the metadata dict.

    Called by:
      • simulation/simulation_runner.py  (programmatic)
      • CLI  (python simulation/osm_to_network.py)
      • backend route  (POST /api/scenarios)
    """
    _configure_osmnx()

    if scenario_id:
        scenario_dir = PROCESSED_DIR / str(scenario_id)
        scenario_dir.mkdir(parents=True, exist_ok=True)
        graphml_path = scenario_dir / "network.graphml"
        geojson_path = scenario_dir / "network.geojson"
        nodes_path   = scenario_dir / "nodes.geojson"
        meta_path    = scenario_dir / "network_meta.json"
    else:
        graphml_path = PROCESSED_DIR / "network.graphml"
        geojson_path = PROCESSED_DIR / "network.geojson"
        nodes_path   = PROCESSED_DIR / "nodes.geojson"
        meta_path    = PROCESSED_DIR / "network_meta.json"

    target_source = f"bbox:{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}" if bbox else (city or os.getenv("CITY_PLACE_NAME", "Davanagere, Karnataka, India"))

    # If processed network for the exact target_source already exists and rebuild is not forced, skip download
    if not force_rebuild and graphml_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            if meta.get("source") == target_source:
                log.info(f"Processed network for {target_source!r} (Scenario {scenario_id}) already exists. Loading from cache …")
                return meta
        except Exception as e:
            log.warning(f"Failed reading cache metadata: {e}")

    t0 = time.time()

    # ── Download ──────────────────────────────────────────────────────────────
    if bbox:
        north, south, east, west = bbox
        G = download_by_bbox(north, south, east, west)
        source = f"bbox:{north},{south},{east},{west}"
    else:
        place = city or os.getenv("CITY_PLACE_NAME", "Davanagere, Karnataka, India")
        G = download_by_place(place)
        source = place

    # ── Enrich ────────────────────────────────────────────────────────────────
    G = enrich_graph(G, city, bbox)

    # ── Save ──────────────────────────────────────────────────────────────────
    save_graphml(G, graphml_path)
    save_geojson(G, geojson_path)
    save_nodes_geojson(G, nodes_path)
    meta = save_metadata(G, meta_path, source)

    # Pre-build city signals GeoJSON to avoid writes on subsequent GET requests
    if scenario_id:
        try:
            from backend.api.routes_dashboard import get_signals_geojson
            get_signals_geojson(scenario_id=scenario_id, refresh=True)
            log.info(f"Pre-built signals GeoJSON for Scenario {scenario_id}.")
        except Exception as sig_err:
            log.warning(f"Could not pre-build signals GeoJSON during network creation: {sig_err}")

    elapsed = time.time() - t0
    log.info(f"Network build complete in {elapsed:.1f}s — {meta['nodes']} nodes, {meta['edges']} edges.")
    return meta


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build road network from OpenStreetMap data.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--city", type=str, help="Place name (e.g. 'Davanagere, Karnataka, India')")
    group.add_argument(
        "--bbox", nargs=4, metavar=("NORTH", "SOUTH", "EAST", "WEST"),
        type=float, help="Bounding box as four floats"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force rebuild even if processed network already exists"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    bbox = tuple(args.bbox) if args.bbox else None
    meta = build_network(city=args.city, bbox=bbox, force_rebuild=args.force)
    print(json.dumps(meta, indent=2))
