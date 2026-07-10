"""
scripts/regen_nodes.py
──────────────────────
Regenerates data/processed/network/nodes.geojson from the existing
network.graphml without re-downloading from OSM.

Run once from the project root:
    python scripts/regen_nodes.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import osmnx as ox
import pandas as pd

PROCESSED = ROOT / "data" / "processed" / "network"
graphml_path = PROCESSED / "network.graphml"
nodes_path   = PROCESSED / "nodes.geojson"

print(f"Loading graph from: {graphml_path}")
G = ox.load_graphml(str(graphml_path))
print(f"Loaded — {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

gdf_nodes = ox.graph_to_gdfs(G, nodes=True, edges=False).reset_index()
print(f"Node columns: {list(gdf_nodes.columns)}")

# Always export
cols = ["osmid", "geometry", "street_count"]

# Include all OSM tag columns that the frontend can use
for col in ("highway", "designation", "name", "ref"):
    if col in gdf_nodes.columns:
        cols.append(col)
        n_nonull = gdf_nodes[col].notna().sum()
        print(f"  Found '{col}' column — {n_nonull} non-null values")
    else:
        print(f"  '{col}' column not in data")

gdf_nodes = gdf_nodes[cols]

# Stringify list-valued columns
for col in gdf_nodes.columns:
    if col == "geometry":
        continue
    gdf_nodes[col] = gdf_nodes[col].apply(
        lambda x: x[0] if isinstance(x, list) else x
    )

gdf_nodes.to_file(str(nodes_path), driver="GeoJSON")
n_signals = 0
if "highway" in gdf_nodes.columns:
    n_signals = (gdf_nodes["highway"] == "traffic_signals").sum()
print(f"Saved: {nodes_path}")
print(f"{len(gdf_nodes)} nodes total, {n_signals} traffic_signals nodes")

# Print signal node details so we can verify
if n_signals > 0 and "highway" in gdf_nodes.columns:
    sigs = gdf_nodes[gdf_nodes["highway"] == "traffic_signals"]
    for _, row in sigs.iterrows():
        print(f"  Signal: osmid={row['osmid']}  lat={row.geometry.y:.6f}  lon={row.geometry.x:.6f}")
