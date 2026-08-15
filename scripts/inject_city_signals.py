"""
inject_city_signals.py
─────────────────────────────────────────────────────────
Queries OSM Overpass API for real traffic_signals nodes
in Davanagere city centre and injects them into nodes.geojson
so the map always shows correct signal locations.

Run:  python scripts/inject_city_signals.py
"""

import json
import math
import sys
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODES_GEOJSON = ROOT / "data" / "processed" / "network" / "nodes.geojson"
NODE_MAPPING   = ROOT / "data" / "node_mapping.json"

# Davanagere city centre bounding box (tight — just the urban core)
BBOX = "14.43,75.89,14.49,75.96"   # south,west,north,east

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
QUERY = f"""
[out:json][timeout:30];
(
  node["highway"="traffic_signals"]({BBOX});
  node["highway"="crossing"]["crossing"="traffic_signals"]({BBOX});
);
out body;
"""


def fetch_overpass(query: str) -> list[dict]:
    payload = ("data=" + urllib.parse.quote(query)).encode()
    req = urllib.request.Request(
        OVERPASS_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read())
    return data.get("elements", [])


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def main():
    print("Fetching real traffic signals from Overpass API ...")
    try:
        osm_signals = fetch_overpass(QUERY)
        print(f"  Found {len(osm_signals)} OSM traffic_signal nodes.")
    except Exception as e:
        print(f"  Overpass query failed: {e}")
        osm_signals = []

    # Fall back to node_mapping.json if Overpass failed
    coord_signals = osm_signals
    if not coord_signals and NODE_MAPPING.exists():
        with open(NODE_MAPPING, encoding="utf-8") as f:
            mapping = json.load(f)
        coord_signals = [
            {"lat": m["lat"], "lon": m["lon"], "tags": {"name": m["name"]}}
            for m in mapping
        ]
        print(f"  Falling back to {len(coord_signals)} entries from node_mapping.json")

    if not coord_signals:
        print("No signal data available -- nothing to inject.")
        return

    print(f"Loading {NODES_GEOJSON} ...")
    with open(NODES_GEOJSON, encoding="utf-8") as f:
        nodes_data = json.load(f)

    features = nodes_data.get("features", [])
    print(f"  {len(features)} node features in GeoJSON.")

    # Also build a list of all node coordinates for fast nearest-search
    node_coords = []
    for idx, feat in enumerate(features):
        coords = (feat.get("geometry") or {}).get("coordinates", [])
        if len(coords) >= 2:
            node_coords.append((idx, coords[1], coords[0]))  # (idx, lat, lon)

    print(f"  Coord bounding box of nodes:")
    if node_coords:
        lats = [c[1] for c in node_coords]
        lons = [c[2] for c in node_coords]
        print(f"    lat: {min(lats):.4f} .. {max(lats):.4f}")
        print(f"    lon: {min(lons):.4f} .. {max(lons):.4f}")

    PROXIMITY_KM = 0.25   # 250 m — generous threshold for district-wide graph
    injected = 0

    for sig in coord_signals:
        sig_lat = sig.get("lat")
        sig_lon = sig.get("lon")
        sig_name = (sig.get("tags") or {}).get("name") or f"Signal #{sig.get('id', '?')}"
        if sig_lat is None or sig_lon is None:
            continue

        # Find the nearest node in the GeoJSON
        best_idx = None
        best_dist = float("inf")
        for idx, n_lat, n_lon in node_coords:
            d = haversine_km(sig_lat, sig_lon, n_lat, n_lon)
            if d < best_dist:
                best_dist = d
                best_idx = idx

        if best_idx is not None and best_dist < PROXIMITY_KM:
            props = features[best_idx].setdefault("properties", {})
            props["highway"] = "traffic_signals"
            if not props.get("designation"):
                props["designation"] = sig_name
            injected += 1
            print(f"  OK Matched '{sig_name}' -> osmid {props.get('osmid')} ({best_dist*1000:.0f}m)")
        else:
            nearest = best_dist * 1000 if best_idx is not None else float("inf")
            print(f"  MISS No node within 250m of '{sig_name}' ({sig_lat},{sig_lon}) nearest={nearest:.0f}m")

    print(f"\nInjected traffic_signals into {injected}/{len(coord_signals)} nodes.")

    if injected > 0:
        with open(NODES_GEOJSON, "w", encoding="utf-8") as f:
            json.dump(nodes_data, f, separators=(",", ":"))
        print(f"Saved updated {NODES_GEOJSON}")

    # Also update node_mapping.json with Overpass data if we got real OSM signals
    if osm_signals:
        mapping_out = [
            {
                "osmid": int(s["id"]),
                "name": (s.get("tags") or {}).get("name") or f"Signal #{s['id']}",
                "lat": s["lat"],
                "lon": s["lon"],
                "street_count": 3
            }
            for s in osm_signals
            if s.get("id") and s.get("lat") and s.get("lon")
        ]
        with open(NODE_MAPPING, "w", encoding="utf-8") as f:
            json.dump(mapping_out, f, indent=2)
        print(f"Updated node_mapping.json with {len(mapping_out)} real OSM signals.")


if __name__ == "__main__":
    main()
