# Digital Twin — AI-Powered Real-Time Urban Planning & Traffic Management
## Feature Reference Document — Panel Presentation

> **City:** Davanagere / Hubballi, Karnataka, India  
> **Stack:** Python (FastAPI) · OSMnx · NetworkX · SQLite · React (frontend) · Claude AI (LLM)

---

## System Architecture Overview

> Matches the project architecture diagram exactly.

```
┌─────────────────────────────┐
│  1. OpenStreetMap Data      │  Roads, Buildings, Heights
│     (OSMnx + Overpass API)  │  → GraphML / GeoJSON
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│  2. SUMO / CityFlow         │  Traffic Simulation
│     (+ Synthetic BPR mode)  │  → Telemetry Dict (edges + nodes)
└──────┬───────┬──────────────┘
       │       │              \
  ┌────▼──┐  ┌─▼──────────┐  ┌─▼─────────────────┐
  │ 3a.   │  │ 3b. Issue  │  │ 3c. AI Proposal    │
  │ LLM   │  │ Detection  │  │ Generator          │
  │ Agent │  │ (3 types)  │  │ (3 proposal types) │
  └────┬──┘  └─┬──────────┘  └─┬─────────────────┘
       └────────┴───────────────┘
                     │
  ┌──────────────────▼──────────────────┐
  │  4. Simulation Validation &         │
  │     Metrics Comparison              │  Before/After KPI delta
  └──────────────────┬──────────────────┘
                     │
  ┌──────────────────▼──────────────────┐
  │  5. Interactive Dashboard           │
  │     2D Map · Metrics · Issues ·     │
  │     Proposals · Agent Narrative     │
  └─────────────────────────────────────┘
```

---

## Feature 1 — Road Network Ingestion (OSM to Network)

### What it does
Downloads the real road network of any configured city from **OpenStreetMap** via the Overpass API, cleans it, enriches it with traffic attributes (speed, capacity, lane count, road type), and exports it in three formats: `GraphML` (graph computation), `GeoJSON` (map rendering), and `JSON` (metadata).

### How it works
- Uses **OSMnx** to query OpenStreetMap data for a city bounding box or place name.
- Calculates per-edge capacity based on road type and lane count.
- Marks 10 specific real-world traffic signal nodes (by OSM node ID) as `highway=traffic_signals`.
- Raw OSM data is cached locally so repeat runs do not re-hit the Overpass API.

**Building Footprint Spatial Analysis (drives `widenable` flag):**
1. Queries OSM building polygons for the city bounding box via `ox.features_from_bbox(tags={"building": True})`.
2. Projects both road edges and building footprints to local UTM (metric coordinates).
3. Buffers each road edge by **5 metres** using Shapely geometry.
4. If any building intersects that 5m buffer → `widenable = False` on that edge.
5. Fallback heuristic (if Overpass timeout): residential/service streets assigned `widenable` by road-type probability.

This flag is the direct input to the Lane Reconfiguration Recommender (Feature 8).

### Why OSMnx and not alternatives
| Alternative | Reason rejected |
|---|---|
| HERE / Google Maps API | Paid, rate-limited, no raw graph export |
| Manual GIS shapefiles | Requires manual download per city, not reproducible |
| TIGER/LINZ road data | India-specific data quality is poor |
| **OSMnx** ✓ | Free, reproducible, full graph topology, built-in simplification |

### What it solves
Provides the real physical road network topology as the foundation for all simulation, detection, and proposal features. Without real topology, signal timing and diversion plans would be based on fictional geometry.

---

## Feature 2 — Traffic Simulation Engine

### What it does
Generates edge-level and node-level traffic telemetry for a simulated city network. Three engine modes are supported:

| Engine | Description |
|---|---|
| `synthetic` | Generates realistic telemetry from graph topology using BPR curves. No external tools needed. |
| `sumo` | Delegates to a live SUMO simulator process via TraCI (requires SUMO installed). |
| `cityflow` | Delegates to CityFlow microsimulator (Phase B+). |

### How it works — Synthetic Engine (Primary)

**Step 1 — Demand Multiplier**
A time-of-day demand level is sampled:
```
demand_mult ~ Uniform(0.55, 0.90)
```

**Step 2 — Flow Assignment**
Per-edge base demand is weighted by node degree (busier intersections → more demand):
```
demand_ratio = clip(demand_mult × degree_scale + noise, 0.15, 1.25)
flow = demand_ratio × 900  (vehicles/hour)
```

**Step 3 — BPR Speed–Flow Curve**
Travel time grows nonlinearly with flow-to-capacity ratio (Bureau of Public Roads model):

    T_sim = T_ff × [1 + α × (f/C)^β]

Where:
- T_ff = free-flow travel time (s)
- f = simulated flow (veh/h)
- C = edge capacity (veh/h)
- α = 0.15, β = 4.0 (standard BPR defaults)

**Step 4 — Derived Metrics**
```
density    = flow / sim_speed          (veh/km)
occupancy  = flow / capacity           (0–1 fraction)
queue      ≈ density × length_m / 1000
wait_time  ≈ queue / max(flow, 1) × 3600
```

### Why BPR and not alternatives
| Alternative | Reason rejected |
|---|---|
| Constant speed model | Ignores congestion — unrealistic |
| Greenshields linear | Oversimplified, poor at high V/C ratios |
| Davidson model | Numerically unstable near capacity |
| **BPR** ✓ | Industry standard (US HCM), well-validated, numerically stable |

### What it solves
Produces a complete edge-level + node-level traffic state (speed, flow, density, queue, occupancy) for every road segment in the city, enabling all downstream detection and optimization modules to operate.

---

## Feature 3 — Congestion Detection

### What it does
Scans simulation telemetry and flags road edges where traffic conditions exceed severity thresholds.

### How it works
For each road edge:

    Speed Ratio = v_sim / v_ff

Severity classification:

| Condition | Severity |
|---|---|
| Speed ratio < 0.40  OR  occupancy > 0.80 | **Severe** |
| Speed ratio < 0.65  OR  occupancy > 0.65 | **Moderate** |
| Queue length > 5 vehicles | **Low** |

### Why rule-based thresholds and not ML
- Speed ratio and occupancy thresholds are grounded in HCM (Highway Capacity Manual) standards.
- ML classifiers would require large labelled congestion datasets, which are unavailable for Tier-2 Indian cities.
- Rule-based approach is fully interpretable — important for city planner trust.

### What it solves
Automatically identifies which road segments are failing and at what severity level, in real time after each simulation run.

---

## Feature 4 — Intersection Safety Analyzer

### What it does
Flags signalized or multi-approach intersections (nodes) with elevated conflict potential or excessive wait times.

### How it works
For each node with ≥ 3 street connections:

| Condition | Severity |
|---|---|
| conflict_rate > 2.0/h  OR  avg_wait > 60s | **Severe** |
| conflict_rate > 1.0/h  OR  avg_wait > 35s | **Moderate** |
| conflict_rate > 0.5/h  OR  avg_wait > 20s | **Low** |

`conflict_rate` is simulated from node-level flow × approach count.

### What it solves
Surfaces unsafe intersections that are accident hotspots, enabling targeted signal retiming or geometric interventions rather than generic network-wide changes.

---

## Feature 5 — Lane Utilization Analyzer

### What it does
Detects two types of lane efficiency problems on multi-lane roads:
- **Saturated** — occupancy > 90% (lane is over capacity)
- **Underutilized** — occupancy < 20% on a road with ≥ 2 lanes (wasted infrastructure)

### What it solves
Identifies candidates for lane reconfiguration: roads where a lane could be added, removed, or repurposed (as bus lane / cycle lane / tidal flow).

---

## Feature 6 — Signal Timing Optimizer (Webster's Method)

### What it does
Generates revised traffic-signal timing plans for congested intersections using the classical Webster formula.

### How it works

**Step 1 — Critical Flow Ratios**

    Y = Σ (q_i / s_i)

Where q_i = demand flow of critical movement i, s_i = saturation flow (1800 veh/h/lane, standard).

**Step 2 — Webster Optimal Cycle Length**

    C_opt = (1.5L + 5) / (1 − Y)

Where:
- L = total lost time per cycle = 3.5s × n_phases
- Y = sum of critical flow ratios (capped at 0.95)
- C_opt bounded to [40s, 180s] practical limits

**Step 3 — Green Time Allocation**
Effective green time distributed proportionally to approach flow ratios:

    g_i = G_eff × (y_i / Σy_j),   G_eff = C_opt − L

### Why Webster's formula and not alternatives
| Alternative | Reason rejected |
|---|---|
| Fixed-time HCM | Requires extensive field data collection |
| Reinforcement Learning (RL) | Requires training environment, large compute, long convergence |
| SCOOT/SCATS | Proprietary systems, require hardware integration |
| **Webster** ✓ | Analytically derived, globally validated benchmark, fast, interpretable |

### What it solves
Reduces intersection delay by allocating green time proportionally to actual demand. Expected wait reduction of up to 30% at over-saturated junctions.

---

## Feature 7 — Route Diversion Planner

### What it does
Finds alternative paths around severely congested road segments and emits diversion proposals.

### How it works
For each `severe` congestion issue:
1. Loads the full OSMnx road graph as a directed graph.
2. Inflates the congested edge's travel-time weight by **10×** to discourage routing through it.
3. Applies **Yen's K-shortest paths algorithm** (`networkx.shortest_simple_paths`) to find up to K=3 alternatives.
4. Filters: removes paths that still traverse the congested edge, and paths with detour ratio > 2.0×.
5. Selects the shortest valid alternative.

    Detour Ratio = alt_path_length / direct_path_length ≤ 2.0

### Why Yen's algorithm and not Dijkstra alone
- Single shortest path (Dijkstra) always finds the direct route through the congested edge.
- Yen's generates ranked alternatives explicitly avoiding the penalized edge.
- Computationally feasible for city-scale graphs with thousands of nodes.

### What it solves
Provides concrete actionable alternative route recommendations for traffic management centers during peak congestion events. Conservative 20% congestion reduction estimate on diverted edges.

---

## Feature 8 — Lane Reconfiguration Recommender

### What it does
Generates lane change proposals for edges flagged by the Lane Utilization Analyzer.

Three proposal subtypes:

| Subtype | Trigger | Action |
|---|---|---|
| `ADD_LANE` | Saturated + widenable | Add 1 lane. Capacity increase ≈ 100/n_lanes % |
| `REPURPOSE_LANE` | Saturated + **not** widenable (building constraints) | Dynamic lane control / bus priority |
| `REMOVE_LANE` | Underutilized (≥ 2 lanes) | Remove 1 lane, repurpose as cycle lane / green buffer |

**Key design decision:** The system checks a `widenable` flag per road segment derived from OSM building footprint proximity. If buildings prevent widening, the system automatically recommends bus priority or tidal flow instead of physical expansion.

### What it solves
Optimizes lane usage without blanket road-widening proposals. Enables city planners to reclaim underutilized asphalt for cycling infrastructure or greening.

---

## Feature 9 — City Inspector Agent (LLM)

### What it does
An LLM-powered AI agent (Claude 3.5 Sonnet / Ollama-hosted local LLM) that receives simulation telemetry and detected issues, and produces:
- A **human-readable narrative** analysis of network health.
- **Top 3–5 critical issues** with root-cause explanation.
- **Concrete intervention recommendations** targeted at city planners.
- **Trend commentary** comparing the current run to prior cycle memory.

### How it works
1. Builds a structured prompt from: top congested edges (by occupancy), all detected issues, and a memory summary from the previous cycle.
2. Calls Claude API (`claude-3-5-sonnet-20241022`, 1024 max tokens) or a local Ollama model.
3. Parses recommendations from the narrative (bullet-point heuristic extraction, capped at 8).
4. Stores a 300-character memory summary per scenario in `AgentMemory` for trend analysis.

**Graceful degradation:** If no API key is configured, a deterministic rule-based summary is generated instead — the pipeline never breaks.

### Why Claude / Anthropic and not alternatives
| Alternative | Reason rejected |
|---|---|
| GPT-4 (OpenAI) | Equivalent capability, secondary fallback available |
| BERT / smaller models | Cannot produce coherent multi-paragraph planning narratives |
| Hardcoded templates | Cannot adapt to variable combinations of issue types and severities |
| **Claude 3.5 Sonnet** ✓ | State-of-the-art reasoning, large context, structured output |

### What it solves
Translates complex numerical simulation data into actionable city-planner language. Bridges the gap between raw data and decision-making without requiring technical expertise.

---

## Feature 10 — KPI Metrics Calculator

### What it does
Computes a full suite of performance indicators from simulation telemetry after every run and stores them in the database.

### Metrics and Formulas

**Composite Congestion Score (multi-factor weighting):**

    S_cong = 0.3×delay + 0.3×queue_length + 0.2×stop_count + 0.2×travel_time_unreliability

An edge is congested if S_cong > 8.0 OR occupancy > 0.70.

**Emissions Proxy — simplified MOVES VSP model:**

    E = a×v + b×v³
    a = 0.0015  (rolling resistance + accessory)
    b = 0.000004  (aerodynamic drag)

**Noise Pollution Proxy:**

    N_dBA = 45 + 10×log10(max(flow, 1)) + 0.2×speed

**Weighted Intersection Delay — HCM-based (equ.md §1):**

    d'_I = Σ(td_i) / Σ(v_i × n_i)

Where td_i = total delay, v_i = flow rate, n_i = lane count for approach i.

**Delay Entropy — Shannon entropy (equ.md §2):**

    H_t = −Σ p_i × ln(p_i),   where p_i = td_i / Σ td_j

Higher entropy = delay spread across more movements (more equitable).
Lower entropy = delay concentrated on one approach (bottleneck).

**Level of Service (HCM standard):**

| Avg Wait (s) | LOS |
|---|---|
| ≤ 10 | A |
| ≤ 20 | B |
| ≤ 35 | C |
| ≤ 55 | D |
| ≤ 80 | E |
| > 80 | F |

**Efficiency Score (composite 0–100):**

    E_score = 100 − (congestion_ratio × 40) − (min(avg_wait, 60) / 60 × 30)

### What it solves
Gives city planners a single comprehensive dashboard of before/after comparison metrics to evaluate whether proposed interventions actually improve the network.

---

## Feature 11 — Before/After Validation

### What it does
Compares a baseline simulation run against a post-proposal simulation run to validate whether a proposal actually improved traffic conditions.

### Formula (equ.md §7)

For metrics that should **decrease** (delay, queue, travel time, emissions):

    ΔM = (M_baseline − M_proposed) / M_baseline × 100%

For metrics that should **increase** (throughput, speed):

    ΔM = (M_proposed − M_baseline) / M_baseline × 100%

**Acceptance rule:**  
A proposal is accepted only if it improves the target metric by ≥ 5% without causing > 5% regression in any other critical metric.

### What it solves
Closes the Digital Twin feedback loop. Proposals are not just generated — they are re-simulated and scored, making the system self-validating.

---

## Feature 12 — REST API Backend (FastAPI)

### What it does
Exposes all system capabilities over HTTP for the React frontend and external clients.

| Endpoint | Function |
|---|---|
| `POST /api/scenarios` | Create a new city scenario (triggers OSM download) |
| `POST /api/scenarios/{id}/simulate` | Run simulation (async background task) |
| `GET /api/dashboard/{id}` | Aggregated dashboard payload |
| `GET /api/dashboard/{id}/geojson` | Network GeoJSON for map rendering |
| `GET /api/scenarios/{id}/metrics` | KPI chart data |
| `POST /api/ai/analyze` | Trigger City Inspector Agent |
| `GET /api/scenarios/{id}/proposals` | Fetch all generated proposals |

### Why FastAPI and not alternatives
| Alternative | Reason rejected |
|---|---|
| Flask | No built-in async, no automatic OpenAPI docs |
| Django REST | Heavyweight ORM coupling, overkill |
| Express (Node) | Python ML/simulation ecosystem unavailable in Node |
| **FastAPI** ✓ | Async-native, Pydantic validation, auto Swagger docs, Python ML integration |

### What it solves
Decouples the AI/simulation backend from the frontend, enabling a clean API-first architecture.

---

## Feature 13 — React Frontend Dashboard

### What it does
- **Live 2D Map (MapView — MapLibre GL JS):** Renders road network GeoJSON with edges colour-coded by congestion severity (green→yellow→red). Uses free OSM tiles, no API key required.
- **KPI Cards:** Displays current-run metrics (speed, wait, efficiency score, LOS, noise, emissions).
- **Issues Panel:** Lists all detected issues with severity badges (severe / moderate / low).
- **Proposals Panel:** Shows AI-generated proposals with expected improvement % estimates.
- **Agent Narrative:** Displays the LLM City Inspector's human-readable analysis.
- **Scenario Management:** Create, select, and compare multiple city scenarios.
- **Signal Override Mode:** Edit mode allowing manual signal node selection on the map.
- **Simulation Progress Overlay:** Real-time elapsed time and ETA while simulation runs in background.

> **Note on 3D:** The architecture diagram references "2D/3D Map". The current implementation uses **MapLibre GL JS in 2D mode** (no pitch, no building extrusion). 3D map capability is planned but not yet wired up in the codebase.

### What it solves
Makes the AI pipeline accessible to city planners without requiring any programming knowledge.

---

## Data Flow Summary

```
1. User creates scenario → OSM data downloaded → GraphML + GeoJSON built
2. User triggers simulation → BPR synthetic model (or SUMO) runs → Telemetry produced
3. Issue detectors run in parallel:
     • CongestionDetector         (edge-level — speed ratio, occupancy, queue)
     • IntersectionSafetyAnalyzer (node-level — conflict rate, wait time)
     • LaneUtilizationAnalyzer    (edge-level — over/under occupancy)
4. Proposal generators run:
     • SignalTimingOptimizer      → Webster optimal cycle + green time plans
     • RouteDiversionPlanner      → Yen's K-shortest alternative paths
     • LaneChangeRecommender      → ADD / REMOVE / REPURPOSE lane plans
5. KPI metrics computed → persisted to SQLite DB
6. City Inspector Agent (LLM) called → narrative + ranked recommendations
7. All results served via FastAPI → React dashboard renders
8. (Optional) User applies proposal → re-simulate → before/after validation
```

---

## Technology Choices — Summary Table

| Component | Technology Chosen | Key Reason |
|---|---|---|
| Road network | OSMnx + OpenStreetMap | Free, reproducible, real city topology |
| Simulation model | BPR Speed-Flow Curve | Industry standard, no external simulator dependency |
| Live simulation | SUMO + TraCI | Open-source, industry-grade microsimulator |
| Issue detection | Rule-based (HCM thresholds) | Interpretable, no training data needed |
| Signal timing | Webster's formula | Foundational traffic engineering standard |
| Route diversion | Yen's K-shortest paths | Finds true alternatives beyond direct path |
| LLM analysis | Claude 3.5 Sonnet | Best-in-class reasoning for planning narratives |
| Backend | FastAPI | Async, auto-docs, Python ML ecosystem |
| Database | SQLite | Zero-config, portable, sufficient for city-scale |
| Frontend | React + Map (GeoJSON) | Standard choice for geospatial dashboards |

---

*Document generated for panel presentation — September 2026*
