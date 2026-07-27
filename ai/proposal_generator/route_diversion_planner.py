"""
ai/proposal_generator/route_diversion_planner.py
──────────────────────────────────────────────────────
Suggests alternate routing for severely congested road segments.

Algorithm
─────────
For each severely congested edge (u→v):
  1. Load the OSMnx road graph.
  2. Temporarily inflate the edge weight (travel time) to simulate discouraging it.
  3. Find the K-shortest alternative paths from u to v (Yen's algorithm via networkx).
  4. Select the best alternative that avoids the congested edge.
  5. Emit a proposal describing the diversion route.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

log = logging.getLogger("route_diversion_planner")

ROOT = Path(__file__).resolve().parent.parent.parent
GRAPHML_PATH = ROOT / "data" / "processed" / "network" / "network.graphml"


def _load_graph() -> nx.MultiDiGraph | None:
    try:
        import osmnx as ox
        return ox.load_graphml(str(GRAPHML_PATH))
    except Exception as e:
        log.warning(f"Could not load graph for route planning: {e}")
        return None


def _make_proposal(
    proposal_id, issue_id, edge_id, u, v,
    alt_path_nodes, alt_path_length, description, parameters, improvement,
):
    return {
        "proposal_id":          proposal_id,
        "type":                 "route_diversion",
        "issue_id":             issue_id,
        "location": {
            "edge_id": edge_id,
            "node_u":  u,
            "node_v":  v,
        },
        "description":          description,
        "parameters":           parameters,
        "expected_improvement": improvement,
        "generated_at":         datetime.now(timezone.utc).isoformat(),
        "validated":            False,
    }


class RouteDiversionPlanner:
    """
    Generate route diversion proposals for severely congested edges.
    Uses k-shortest paths on the OSMnx graph to find viable alternatives.
    """

    def __init__(self, k_paths: int = 3, max_detour_ratio: float = 2.0):
        self.k_paths         = k_paths
        self.max_detour_ratio = max_detour_ratio

    def generate(self, issues: list[dict], telemetry: dict) -> list[dict]:
        # Only generate diversions for severe congestion
        congestion_severe = [
            i for i in issues
            if i.get("type") == "congestion" and i.get("severity") == "severe"
        ]
        if not congestion_severe:
            log.info("No severe congestion issues — no route diversions needed.")
            return []

        G = _load_graph()
        proposals = []
        counter = 0

        for issue in congestion_severe[:10]:   # cap to avoid long compute
            loc     = issue.get("location", {})
            edge_id = loc.get("edge_id", "")
            u       = loc.get("node_u", 0)
            v       = loc.get("node_v", 0)
            metrics = issue.get("metrics", {})

            if not (u and v and G is not None):
                proposals.append(self._stub_proposal(issue, edge_id, u, v, counter))
                counter += 1
                continue

            # Find alternative paths
            try:
                # Use a simple DiGraph copy for k-shortest paths
                DG = nx.DiGraph()
                for pu, pv, data in G.edges(data=True):
                    w = data.get("travel_time", data.get("length", 100) / 10)
                    DG.add_edge(pu, pv, weight=w)

                # Inflate congested edge weight
                if DG.has_edge(u, v):
                    DG[u][v]["weight"] *= 10

                # Direct path length (for comparison)
                try:
                    direct_len = nx.shortest_path_length(DG, u, v, weight="weight")
                except nx.NetworkXNoPath:
                    direct_len = None

                # K-shortest paths generator
                path_generator = nx.shortest_simple_paths(DG, u, v, weight="weight")
                alt_paths = []
                for _ in range(self.k_paths + 2):
                    try:
                        alt_paths.append(next(path_generator))
                    except (StopIteration, nx.NetworkXNoPath):
                        break

                # Filter: skip paths through the congested edge
                valid_alts = []
                if len(alt_paths) > 1:
                    for path in alt_paths[1:]:
                        edges_in_path = list(zip(path[:-1], path[1:]))
                        if (u, v) not in edges_in_path:
                            path_len = sum(DG[a][b]["weight"] / 10 for a, b in edges_in_path)
                            if direct_len is None or path_len <= direct_len * self.max_detour_ratio:
                                valid_alts.append((path, path_len))

            except Exception as e:
                log.warning(f"Path search failed for edge {edge_id}: {e}")
                proposals.append(self._stub_proposal(issue, edge_id, u, v, counter))
                counter += 1
                continue

            if not valid_alts:
                log.info(f"No valid alternative found for edge {edge_id}.")
                continue

            best_path, best_len = valid_alts[0]
            counter += 1
            n_hops = len(best_path) - 1

            params = {
                "congested_edge":     edge_id,
                "type":               "route_diversion",
                "alt_path_nodes":     [int(n) for n in best_path],
                "alt_path_hops":      n_hops,
                "alt_path_weight":    round(best_len, 1),
            }
            improvement = {
                "rationale": (
                    f"Diverting traffic from saturated edge {edge_id} "
                    f"via {n_hops}-hop alternative path."
                ),
                "expected_congestion_reduction_pct": 20,  # conservative estimate
            }
            desc = (
                f"Divert traffic away from congested edge {edge_id} "
                f"(occupancy={metrics.get('occupancy', 0):.1%}) "
                f"via a {n_hops}-hop alternative route through {len(best_path)} nodes."
            )
            proposals.append(_make_proposal(
                proposal_id       = f"diversion_{edge_id}_{counter}",
                issue_id          = issue["issue_id"],
                edge_id           = edge_id,
                u                 = u,
                v                 = v,
                alt_path_nodes    = best_path,
                alt_path_length   = best_len,
                description       = desc,
                parameters        = params,
                improvement       = improvement,
            ))

        log.info(f"RouteDiversionPlanner: {len(proposals)} proposals generated.")
        return proposals

    def _stub_proposal(self, issue, edge_id, u, v, counter) -> dict:
        """Return a stub proposal when graph is unavailable or path search fails."""
        return {
            "proposal_id":  f"diversion_{edge_id}_{counter}",
            "type":         "route_diversion",
            "issue_id":     issue["issue_id"],
            "location":     {"edge_id": edge_id, "node_u": u, "node_v": v},
            "description":  f"Route diversion recommended for congested edge {edge_id} (path search pending network load).",
            "parameters":   {"edge": edge_id, "type": "route_diversion"},
            "expected_improvement": {"expected_congestion_reduction_pct": 15},
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "validated":    False,
        }


def generate_diversion_proposals(issues: list[dict], telemetry: dict, **kwargs) -> list[dict]:
    return RouteDiversionPlanner(**kwargs).generate(issues, telemetry)
