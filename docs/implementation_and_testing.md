# 5. Implementation

---

## 5.1 Installation Steps

### 5.1.1 Prerequisites

Before setting up the project, ensure the following software is installed on your machine:

| Requirement | Version | Purpose |
|---|---|---|
| Python | 3.10 or higher | Core language for all backend, AI, and simulation modules |
| Node.js | 18 or higher | Frontend (React + Vite) development server |
| Git | Any recent version | Source control and repository cloning |
| pip | Latest | Python package installer |
| npm | Bundled with Node.js | Node package installer |

> **Optional:** SUMO (Simulation of Urban MObility) for full micro-simulation in Phase B. Without SUMO, the system uses the built-in synthetic traffic engine automatically.

---

### 5.1.2 Step 1 — Clone the Repository

Open a terminal (PowerShell on Windows / Bash on Linux/macOS) and run:

```bash
git clone <repository-url>
cd digital-twin-traffic-ai
```

If the repository uses Git LFS for large files (e.g., the pre-built GraphML road network):

```bash
git lfs install
git lfs pull
```

---

### 5.1.3 Step 2 — Create and Activate the Python Virtual Environment

It is strongly recommended to use an isolated Python virtual environment to avoid dependency conflicts.

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\activate
```

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

After activation, your terminal prompt will show `(venv)` as a prefix.

---

### 5.1.4 Step 3 — Install Python Dependencies

All required packages are listed in `requirements.txt`. Install them with:

```bash
pip install -r requirements.txt
```

**Key packages installed:**

| Category | Packages |
|---|---|
| Core / Data Science | numpy, pandas, scikit-learn, scipy |
| Geospatial | osmnx, geopandas, shapely, networkx, pyproj |
| Backend API | fastapi, uvicorn, httpx, python-multipart |
| Database | sqlalchemy, alembic |
| LLM Agent | anthropic |
| Configuration | python-dotenv, pydantic, pydantic-settings |
| Utilities | requests, aiohttp, tqdm, matplotlib, seaborn, joblib |
| Testing | pytest, pytest-asyncio |
| Jupyter | jupyter, ipykernel |

> **Note:** The `psycopg2-binary` package for PostgreSQL/PostGIS is commented out in `requirements.txt`. Uncomment it only when migrating from SQLite to PostgreSQL in Phase B+.

---

### 5.1.5 Step 4 — Configure Environment Variables

The project uses a `.env` file at the root directory for secret keys and configurable parameters. Copy the example file and edit it:

```bash
cp .env.example .env
```

Open `.env` in a text editor and set the following values:

```env
# LLM API Key
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# City bounding box (default: Davanagere, Karnataka)
CITY_NAME=Davanagere, Karnataka, India
OSM_BBOX_NORTH=14.490
OSM_BBOX_SOUTH=14.440
OSM_BBOX_EAST=75.960
OSM_BBOX_WEST=75.900

# Simulation defaults
SIM_ENGINE=synthetic
SIM_DURATION_S=3600
SIM_SEED=42

# Congestion thresholds
CONGESTION_SPEED_RATIO=0.40
CONGESTION_OCCUPANCY=0.80
CONGESTION_QUEUE_MIN=5

# API / CORS
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
LOG_LEVEL=INFO
```

> **Important:** Never commit the `.env` file to version control. It is already listed in `.gitignore`.

If `ANTHROPIC_API_KEY` is not set, the LLM City Inspector Agent will automatically fall back to a deterministic rule-based summary, so the rest of the pipeline continues to function.

---

### 5.1.6 Step 5 — Initialize the Database

The project uses SQLite (via SQLAlchemy) by default. The database is automatically created when the backend starts for the first time. To initialize it manually:

```bash
cd d:/major_project
python -c "from backend.database.db_connector import init_db; init_db()"
```

This creates `digital_twin.db` at the project root with all required tables (Scenarios, SimulationRuns, Issues, Proposals, ValidationResults).

---

### 5.1.7 Step 6 — Start the Backend Server

From the project root directory:

```bash
cd d:/major_project
uvicorn backend.app:app --reload --port 8000
```

**Expected output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

The interactive API documentation (Swagger UI) is available at:
`http://localhost:8000/docs`

The ReDoc documentation is available at:
`http://localhost:8000/redoc`

---

### 5.1.8 Step 7 — Install Frontend Dependencies and Start the Dashboard

Open a **new terminal** (keep the backend terminal running), and run:

```bash
cd d:/major_project/frontend
npm install
npm run dev
```

**Expected output:**
```
  VITE v5.x.x  ready in 500ms

  Local:   http://localhost:5173/
  Network: use --host to expose
```

The interactive dashboard is available at:
`http://localhost:5173`

---

### 5.1.9 Step 8 — Run the Full Pipeline (End-to-End)

With both servers running, execute the pipeline using `curl` or any REST client (e.g., Postman):

**Step 8a — Create a Scenario:**
```bash
curl -X POST http://localhost:8000/api/scenarios \
  -H "Content-Type: application/json" \
  -d '{"name": "Davanagere Peak Hour", "city": "Davanagere, Karnataka, India"}'
```

**Step 8b — Run Baseline Simulation (replace 1 with your scenario_id):**
```bash
curl -X POST http://localhost:8000/api/scenarios/1/simulate \
  -H "Content-Type: application/json" \
  -d '{"engine": "synthetic", "duration_s": 3600}'
```

**Step 8c — View Detected Issues:**
```bash
curl http://localhost:8000/api/scenarios/1/issues
```

**Step 8d — View Generated Proposals:**
```bash
curl http://localhost:8000/api/scenarios/1/proposals
```

**Step 8e — Validate a Proposal (replace 1 with proposal_id):**
```bash
curl -X POST http://localhost:8000/api/proposals/1/validate
```

**Step 8f — Fetch Full Dashboard Payload:**
```bash
curl http://localhost:8000/api/dashboard/1
```

---

### 5.1.10 Step 9 — Run the Test Suite

From the project root, with the virtual environment activated:

```bash
cd d:/major_project
pytest tests/ -v
```

**Expected output:**
```
tests/test_simulation.py::TestSyntheticSimulator::test_run_returns_expected_keys PASSED
tests/test_simulation.py::TestSyntheticSimulator::test_edges_have_required_fields PASSED
tests/test_simulation.py::TestSyntheticSimulator::test_occupancy_bounded PASSED
tests/test_simulation.py::TestMetricsCalculator::test_compute_metrics_returns_expected_keys PASSED
tests/test_ai.py::TestCongestionDetector::test_returns_list PASSED
tests/test_ai.py::TestCongestionDetector::test_issue_schema PASSED
tests/test_ai.py::TestSignalTimingOptimizer::test_proposal_schema PASSED
tests/test_ai.py::TestBeforeAfterComparator::test_comparison_verdict PASSED
...
```

---

### 5.1.11 Directory Structure After Setup

```
digital-twin-traffic-ai/
├── .env                          <- Your configured secrets (not in git)
├── requirements.txt              <- Python dependencies
├── digital_twin.db               <- Auto-created SQLite database
├── data/
│   └── processed/network/
│       └── network.graphml       <- OSM road network (auto-built if absent)
├── simulation/                   <- Traffic simulation engine
├── ai/
│   ├── city_inspector_agent/     <- LLM-based AI agent
│   ├── issue_detection/          <- Rule-based detectors
│   └── proposal_generator/       <- Fix proposal generators
├── validation/                   <- Before/after KPI comparator
├── backend/                      <- FastAPI REST API
├── frontend/
│   └── node_modules/             <- Auto-installed npm packages
└── tests/                        <- Pytest test suite
```

---

## 5.2 Pseudo Code for the Modules

> The following pseudo code describes only the **important modules** of the system.
> Each module is self-contained and communicates through structured dictionaries
> conforming to a shared schema.

---

### 5.2.1 Module: Simulation Runner (`simulation/simulation_runner.py`)

This module orchestrates a complete simulation run and is the entry point for all traffic data generation.

```
MODULE SimulationRunner

FUNCTION run_simulation(scenario_id, engine="synthetic", duration_s=3600, seed=42,
                        apply_proposals=None):
    G <- load_graph(scenario_id)          // Load OSMnx road network from GraphML

    IF engine == "synthetic":
        simulator <- SyntheticSimulator(G, duration_s, seed, apply_proposals)
        telemetry <- simulator.run()
    ELSE IF engine == "sumo":
        telemetry <- _run_sumo(G, duration_s, seed, scenario_id)
    ELSE:
        RAISE ValueError("Unsupported engine")

    RETURN telemetry


CLASS SyntheticSimulator:

    CONSTANTS:
        BPR_ALPHA = 0.15       // Bureau of Public Roads parameter
        BPR_BETA  = 4.0        // BPR exponent

    FUNCTION __init__(G, duration_s, seed, apply_proposals):
        self.G               <- G
        self.duration_s      <- duration_s
        self.apply_proposals <- apply_proposals OR []
        SET numpy.random.seed(seed)
        SET random.seed(seed)
        self.degree_cache <- degree of each node in G

    FUNCTION _demand_multiplier() -> float:
        // Simulate time-of-day demand (0.55 to 0.90)
        RETURN uniform_random(0.55, 0.90)

    FUNCTION _bpr_travel_time(free_flow_tt, flow, capacity) -> float:
        // BPR speed-flow curve:
        // travel_time = free_flow_tt x [1 + alpha x (flow/capacity)^beta]
        ratio <- flow / MAX(capacity, 1)
        RETURN free_flow_tt x (1 + BPR_ALPHA x ratio^BPR_BETA)

    FUNCTION _simulate_edges(demand_mult) -> List[EdgeRecord]:
        records <- []
        FOR EACH edge (u, v, k, data) IN G.edges():
            edge_id      <- "{u}_{v}_{k}"
            length_m     <- data.length
            speed_kph    <- data.speed_kph
            capacity     <- data.capacity
            lanes        <- data.lanes
            road_type    <- data.road_type
            free_flow_tt <- (length_m / 1000) / speed_kph x 3600

            avg_degree   <- (degree(u) + degree(v)) / 2
            degree_scale <- MIN(avg_degree / 4.0, 1.0)
            noise        <- gaussian_random(mean=0, std=0.08)
            demand_ratio <- CLIP(demand_mult x degree_scale + noise, 0.15, 1.25)
            traffic_demand <- demand_ratio x 900.0

            demand_modifier <- data.demand_modifier OR 1.0
            flow <- MAX(10.0, traffic_demand x demand_modifier)

            sim_tt    <- _bpr_travel_time(free_flow_tt, flow, capacity)
            sim_speed <- (length_m / 1000.0) / (sim_tt / 3600.0)
            density   <- flow / MAX(sim_speed, 1.0)
            flow_ratio <- flow / MAX(capacity, 1.0)
            queue     <- MAX(0, (flow_ratio - 0.75) x capacity x 0.02)
            wait_time <- MAX(0, (sim_tt - free_flow_tt) + exponential_random(1.5))
            occupancy <- CLIP(flow_ratio, 0.0, 1.0)

            records.APPEND({edge_id, u, v, length_m, road_type, lanes, speed_kph,
                            capacity, flow, sim_speed, density, queue, wait_time,
                            sim_tt, occupancy})
        RETURN records

    FUNCTION _simulate_nodes(edge_records) -> List[NodeRecord]:
        node_flows <- GROUP edge_records BY destination node v
        FOR EACH node IN G.nodes():
            in_flows      <- node_flows[node] OR [0]
            avg_flow      <- MEAN(in_flows)
            sc            <- degree(node)
            conflict_rate <- CLIP(avg_flow x sc / 3000 + exponential_random(0.05), 0, 5)

            wait_modifier <- 1.0
            FOR EACH proposal IN apply_proposals:
                IF proposal.type == "signal_timing" AND proposal.node_id == node:
                    reduction     <- proposal.expected_improvement.wait_reduction_pct
                    wait_modifier <- wait_modifier x (1 - reduction / 100)

            avg_wait <- CLIP(gamma_random(2, scale=5) + avg_flow/1000x8) x wait_modifier
            APPEND {node_id, lat, lon, street_count=sc, conflict_rate, avg_wait}
        RETURN records

    FUNCTION _compute_summary(edges, nodes) -> SummaryDict:
        RETURN {
            avg_travel_time_s : MEAN(edge.travel_time FOR edge IN edges),
            avg_wait_time_s   : MEAN(edge.wait_time FOR edge IN edges),
            avg_speed_kph     : MEAN(edge.speed_sim FOR edge IN edges),
            total_flow_veh_h  : SUM(edge.flow FOR edge IN edges),
            congested_edges   : COUNT(edge WHERE edge.occupancy > 0.75),
            congestion_ratio  : congested_edges / TOTAL(edges)
        }

    FUNCTION run() -> TelemetryDict:
        demand_mult <- _demand_multiplier()
        edges       <- _simulate_edges(demand_mult)
        nodes       <- _simulate_nodes(edges)
        summary     <- _compute_summary(edges, nodes)
        RETURN {engine: "synthetic", demand_multiplier, edges, nodes, summary}
```

---

### 5.2.2 Module: Congestion Detector (`ai/issue_detection/congestion_detector.py`)

Flags road segments where simulated traffic conditions exceed configured thresholds, using both rule-based heuristics and optional ML prediction scores.

```
MODULE CongestionDetector

THRESHOLDS (configurable via .env):
    SPEED_RATIO_SEVERE   = 0.40
    SPEED_RATIO_MODERATE = 0.65
    OCCUPANCY_SEVERE     = 0.80
    OCCUPANCY_MODERATE   = 0.65
    QUEUE_MIN            = 5.0

CLASS CongestionDetector:

    FUNCTION detect(telemetry) -> List[IssueRecord]:
        edges  <- telemetry.edges
        issues <- []

        FOR EACH edge IN edges:
            speed_ff  <- edge.speed_kph
            speed_sim <- edge.speed_sim
            occupancy <- edge.occupancy
            queue     <- edge.queue_length
            ml_level  <- edge.ml_congestion_level     // 0=free, 1=mod, 2=severe
            ml_risk   <- edge.ml_risk_score           // 0.0 to 1.0

            speed_ratio <- speed_sim / MAX(speed_ff, 1)

            IF speed_ratio < SPEED_RATIO_SEVERE
               OR occupancy > OCCUPANCY_SEVERE
               OR (ml_level == 2 AND ml_risk >= 0.75):
                severity <- "severe"

            ELSE IF speed_ratio < SPEED_RATIO_MODERATE
               OR occupancy > OCCUPANCY_MODERATE
               OR (ml_level == 1 AND ml_risk >= 0.50):
                severity <- "moderate"

            ELSE IF queue > QUEUE_MIN OR (ml_level > 0):
                severity <- "low"

            ELSE:
                SKIP to next edge

            issues.APPEND({
                issue_id    : "congestion_{edge_id}_{counter}",
                type        : "congestion",
                severity,
                location    : {edge_id, node_u: u, node_v: v},
                metrics     : {speed_kph, free_flow_kph, speed_ratio, occupancy,
                               queue_length, wait_time_s, flow_veh_h,
                               ml_prediction, ml_risk_score},
                description,
                detected_at : current_utc_timestamp()
            })

        SORT issues BY severity PRIORITY {severe:0, moderate:1, low:2}
        RETURN issues
```

---

### 5.2.3 Module: Intersection Safety Analyzer (`ai/issue_detection/intersection_safety_analyzer.py`)

Identifies intersections with high conflict rates or excessive wait times that pose safety risks.

```
MODULE IntersectionSafetyAnalyzer

THRESHOLDS:
    CONFLICT_RATE_SEVERE   = 2.0
    CONFLICT_RATE_MODERATE = 1.0
    WAIT_TIME_SEVERE       = 60.0   // seconds
    WAIT_TIME_MODERATE     = 40.0   // seconds
    MIN_STREET_COUNT       = 3

FUNCTION detect_unsafe_intersections(telemetry) -> List[IssueRecord]:
    issues <- []
    FOR EACH node IN telemetry.nodes:
        sc            <- node.street_count
        conflict_rate <- node.conflict_rate
        avg_wait      <- node.avg_wait_time

        IF sc < MIN_STREET_COUNT: SKIP

        IF conflict_rate >= CONFLICT_RATE_SEVERE OR avg_wait >= WAIT_TIME_SEVERE:
            severity <- "severe"
        ELSE IF conflict_rate >= CONFLICT_RATE_MODERATE OR avg_wait >= WAIT_TIME_MODERATE:
            severity <- "moderate"
        ELSE:
            SKIP

        issues.APPEND({
            issue_id    : "intersection_{node_id}_{counter}",
            type        : "intersection_safety",
            severity,
            location    : {node_id, lat, lon},
            metrics     : {conflict_rate, avg_wait_time_s: avg_wait, street_count: sc},
            description : "Unsafe intersection at node {node_id}: {conflict_rate}
                          conflicts/hr, avg wait {avg_wait}s.",
            detected_at : current_utc_timestamp()
        })
    RETURN issues
```

---

### 5.2.4 Module: Lane Utilization Analyzer (`ai/issue_detection/lane_utilization_analyzer.py`)

Detects both underutilized lanes (wasted capacity) and over-saturated lanes.

```
MODULE LaneUtilizationAnalyzer

THRESHOLDS:
    UNDERUTILIZED_THRESHOLD = 0.25
    SATURATED_THRESHOLD     = 0.90
    MIN_LANES_FOR_CHECK     = 2

FUNCTION detect_lane_issues(telemetry) -> List[IssueRecord]:
    issues <- []
    FOR EACH edge IN telemetry.edges:
        lanes    <- edge.lanes
        occupancy <- edge.occupancy
        IF lanes < MIN_LANES_FOR_CHECK: SKIP

        per_lane_occ <- occupancy / lanes

        IF per_lane_occ < UNDERUTILIZED_THRESHOLD AND occupancy < 0.40:
            subtype  <- "underutilized"
            severity <- "low"
            description <- "Edge {edge_id} has {lanes} lanes but only {occupancy:.0%}
                           occupancy. Consider lane reduction or repurposing."

        ELSE IF occupancy > SATURATED_THRESHOLD:
            subtype  <- "saturated"
            severity <- "moderate" IF occupancy < 0.95 ELSE "severe"
            description <- "Edge {edge_id} is saturated at {occupancy:.0%} occupancy."

        ELSE: SKIP

        issues.APPEND({
            issue_id  : "lane_{edge_id}_{counter}",
            type      : "lane_utilization",
            subtype, severity,
            location  : {edge_id, node_u: u, node_v: v},
            metrics   : {lanes, occupancy, flow, capacity, per_lane_occ},
            description
        })
    RETURN issues
```

---

### 5.2.5 Module: Signal Timing Optimizer (`ai/proposal_generator/signal_timing_optimizer.py`)

Generates traffic signal re-timing proposals using Webster's optimal cycle length formula.

```
MODULE SignalTimingOptimizer

CONSTANTS:
    LOST_TIME_PER_PHASE = 3.5     // seconds of lost time per signal phase
    SATURATION_FLOW     = 1800    // vehicles/hour/lane
    MIN_GREEN           = 10      // seconds
    MAX_GREEN           = 90      // seconds

CLASS SignalTimingOptimizer:

    FUNCTION generate(issues, telemetry) -> List[ProposalRecord]:
        node_lookup <- INDEX telemetry.nodes BY node_id
        flow_map    <- FOR each edge (u->v): MAP v -> list of (flow, capacity)
        proposals   <- []

        FOR EACH issue IN issues:
            IF issue.type NOT IN ["congestion", "intersection_safety"]: SKIP

            node_id  <- issue.location.node_id OR issue.location.node_v
            IF node_id IS NULL: SKIP

            node_data <- node_lookup[node_id]
            sc        <- node_data.street_count
            IF sc < 3: SKIP

            approaches <- flow_map[node_id] OR [(400, 1200)] x MAX(sc-1, 2)

            // Webster's Method
            n_phases  <- CLAMP(sc - 1, 2, 4)
            L         <- LOST_TIME_PER_PHASE x n_phases

            // Critical flow ratios
            sorted_approaches <- SORT approaches BY (flow/capacity) DESCENDING
            Y  <- SUM(flow / capacity / SATURATION_FLOW
                      FOR (flow, capacity) IN sorted_approaches[:n_phases])
            Y  <- MIN(Y, 0.95)

            // Optimal cycle length:   C = (1.5*L + 5) / (1 - Y)
            C_opt <- (1.5 x L + 5) / MAX(1 - Y, 0.05)
            C_opt <- CLAMP(C_opt, 40, 180)

            G_eff       <- C_opt - L
            flow_ratios <- [f/c FOR (f,c) IN sorted_approaches[:n_phases]]
            total_fr    <- SUM(flow_ratios)

            phases <- []
            FOR (i, fr) IN ENUMERATE(flow_ratios):
                green <- CLAMP(ROUND(G_eff x fr / total_fr), MIN_GREEN, MAX_GREEN)
                phases.APPEND({phase: i+1, green_s: green, amber_s: 3,
                               red_s: ROUND(C_opt - green - 3)})

            timing_plan <- {cycle_length_s: C_opt, n_phases, lost_time_s: L,
                            effective_green_s: G_eff, phases, method: "Webster"}

            current_wait       <- node_data.avg_wait_time OR 30
            wait_reduction_pct <- MIN(30, ROUND((Y / MAX(1, sc)) x 50))

            proposals.APPEND({
                proposal_id : "signal_{node_id}_{counter}",
                type        : "signal_timing",
                parameters  : timing_plan,
                expected_improvement : {wait_reduction_pct,
                    expected_wait_after: current_wait x (1 - wait_reduction_pct/100)},
                validated   : False
            })

        RETURN proposals
```

---

### 5.2.6 Module: Route Diversion Planner (`ai/proposal_generator/route_diversion_planner.py`)

Finds alternative routes for severely congested edges using Yen's K-Shortest Paths algorithm on the OSMnx road graph.

```
MODULE RouteDiversionPlanner

CLASS RouteDiversionPlanner:

    FUNCTION __init__(k_paths=3, max_detour_ratio=2.0):
        self.k_paths          <- k_paths
        self.max_detour_ratio <- max_detour_ratio

    FUNCTION generate(issues, telemetry) -> List[ProposalRecord]:
        severe_congestion <- FILTER issues WHERE type="congestion" AND severity="severe"
        IF severe_congestion IS EMPTY: RETURN []

        G <- load_osmnx_graph()
        IF G IS NULL: RETURN []

        proposals <- []
        FOR EACH issue IN severe_congestion:
            u <- issue.location.node_u
            v <- issue.location.node_v

            // Temporarily inflate congested edge to discourage its use
            G.edge(u, v).travel_time <- G.edge(u, v).travel_time x 10

            // Yen's k-shortest paths
            TRY:
                k_path_list <- networkx.shortest_simple_paths(G, u, v, weight="travel_time")
                alternatives <- []
                FOR EACH path IN k_path_list[:self.k_paths]:
                    IF issue.edge_id NOT IN path:
                        path_length  <- SUM(G.edge(a,b).length FOR (a,b) IN path)
                        detour_ratio <- path_length / MAX(direct_length, 1)
                        IF detour_ratio <= self.max_detour_ratio:
                            alternatives.APPEND({path, path_length, detour_ratio})
            CATCH Exception: CONTINUE

            // Restore original weight
            G.edge(u, v).travel_time <- original_weight
            IF alternatives IS EMPTY: CONTINUE

            best <- SORT alternatives BY path_length ASCENDING [0]
            proposals.APPEND({
                proposal_id : "diversion_{edge_id}_{counter}",
                type        : "route_diversion",
                parameters  : {alt_path_nodes: best.path,
                               alt_path_length_m: best.path_length,
                               detour_ratio: best.detour_ratio},
                expected_improvement : {flow_reduction_pct: 25},
                validated   : False
            })

        RETURN proposals
```

---

### 5.2.7 Module: Zoning Proposer (`ai/proposal_generator/zoning_proposer.py`)

Generates land-use renovation proposals for zones flagged with zoning imbalance, using Shannon entropy to measure land-use diversity.

```
MODULE ZoningProposer

CONSTANT DEFAULT_CONVERT_FRACTION = 0.20

COMPLEMENT_MAP = {
    "residential" -> "commercial",
    "commercial"  -> "residential",
    "industrial"  -> "commercial",
    "retail"      -> "residential",
    "farmland"    -> "residential", ...
}

FUNCTION _entropy(area_by_type) -> float:
    // Normalized Shannon entropy:  ENT = -SUM(P_i x ln(P_i)) / ln(k)
    positive    <- FILTER area_by_type.values WHERE value > 0
    IF LENGTH(positive) <= 1: RETURN 0.0
    total       <- SUM(positive)
    proportions <- [a / total FOR a IN positive]
    raw_entropy <- -SUM(p x ln(p) FOR p IN proportions)
    RETURN raw_entropy / ln(LENGTH(proportions))

FUNCTION generate(zoning_issues, convert_fraction=DEFAULT_CONVERT_FRACTION):
    proposals <- []
    FOR EACH issue IN zoning_issues:
        zone_id      <- issue.zone_id
        dominant_use <- issue.metrics.dominant_use
        area_by_type <- issue.metrics.area_by_type
        ent_current  <- _entropy(area_by_type)

        complement <- COMPLEMENT_MAP[dominant_use] OR "commercial"

        dominant_area    <- area_by_type[dominant_use] OR 0
        proposed_convert <- dominant_area x convert_fraction

        modified_area <- COPY area_by_type
        modified_area[dominant_use] <- modified_area[dominant_use] - proposed_convert
        modified_area[complement]   <- modified_area.get(complement, 0) + proposed_convert

        ent_proposed    <- _entropy(modified_area)
        // Improvement: delta_M = (ENT_proposed - ENT_current) x 100
        improvement_pct <- (ent_proposed - ent_current) x 100

        proposals.APPEND({
            proposal_id : "zoning_{zone_id}_{counter}",
            type        : "zoning_change",
            parameters  : {dominant_use, complement,
                           area_to_convert_m2: proposed_convert,
                           current_entropy: ent_current,
                           proposed_entropy: ent_proposed},
            expected_improvement : {entropy_gain_pct: improvement_pct,
                                    new_entropy: ent_proposed},
            validated   : False
        })
    RETURN proposals
```

---

### 5.2.8 Module: LLM City Inspector Agent (`ai/city_inspector_agent/llm_agent.py`)

Orchestrates LLM-powered narrative analysis of simulated traffic and detected issues.

```
MODULE CityInspectorAgent

FUNCTION _build_analysis_prompt(scenario_name, telemetry, issues, prior_summary) -> str:
    summary      <- telemetry.summary
    engine       <- telemetry.engine
    sorted_edges <- SORT telemetry.edges BY occupancy DESCENDING [:5]
    congested_table <- FORMAT TABLE(edge_id, road_type, occupancy, speed, queue)

    severe_issues   <- FILTER issues WHERE severity == "severe"
    moderate_issues <- FILTER issues WHERE severity == "moderate"

    prompt <- """
    You are the City Inspector AI for {scenario_name}.
    Simulation Engine: {engine}

    Network Summary:
    - Avg Speed:        {summary.avg_speed_kph} km/h
    - Avg Travel Time:  {summary.avg_travel_time_s}s
    - Avg Wait Time:    {summary.avg_wait_time_s}s
    - Congestion Ratio: {summary.congestion_ratio:.1%}

    Top 5 Congested Edges:
    {congested_table}

    Detected Issues: {COUNT(severe)} severe, {COUNT(moderate)} moderate

    Provide: (1) narrative analysis, (2) top 3 priority actions,
             (3) confidence score 0-100.
    """
    RETURN prompt

CLASS CityInspectorAgent:

    FUNCTION analyze(scenario_id, telemetry, issues) -> AnalysisResult:
        memory       <- AgentMemory.load(scenario_id)
        prior_summary <- memory.last_narrative OR ""
        prompt       <- _build_analysis_prompt(scenario_name, telemetry, issues, prior_summary)

        IF ANTHROPIC_API_KEY IS SET:
            TRY:
                client   <- anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                response <- client.messages.create(
                    model="claude-3-haiku-20240307", max_tokens=1024,
                    messages=[{role:"user", content:prompt}])
                narrative <- response.content[0].text
            CATCH AnthropicError:
                narrative <- _rule_based_fallback(telemetry, issues)
        ELSE:
            // Graceful degradation: deterministic rule-based summary
            narrative <- _rule_based_fallback(telemetry, issues)

        result <- {scenario_id, narrative, priorities, confidence, analyzed_at}
        memory.save(result)
        RETURN result
```

---

### 5.2.9 Module: Before-After Comparator (`validation/before_after_comparator.py`)

Computes a composite improvement score and verdict by comparing baseline vs. post-proposal simulation metrics.

```
MODULE BeforeAfterComparator

METRIC_WEIGHTS = {
    "avg_travel_time_s" : 0.25,    // lower is better
    "avg_wait_time_s"   : 0.20,    // lower is better
    "avg_speed_kph"     : 0.20,    // higher is better
    "congestion_ratio"  : 0.20,    // lower is better
    "efficiency_score"  : 0.15,    // higher is better
}

APPROVAL_THRESHOLD    = 60
CONDITIONAL_THRESHOLD = 30

FUNCTION compare(baseline, improved, proposal_id, scenario_id) -> ValidationResult:
    weighted_sum <- 0.0

    FOR EACH (metric, weight) IN METRIC_WEIGHTS:
        base_val <- baseline[metric]
        impr_val <- improved[metric]

        IF metric IN ["avg_travel_time_s", "avg_wait_time_s", "congestion_ratio"]:
            delta_pct <- (base_val - impr_val) / ABS(base_val) x 100   // lower is better
        ELSE:
            delta_pct <- (impr_val - base_val) / ABS(base_val) x 100   // higher is better

        normalized_score <- CLAMP(delta_pct, -100, 100)
        weighted_sum     <- weighted_sum + normalized_score x weight x 100

    improvement_score <- CLAMP(weighted_sum, 0, 100)

    IF improvement_score >= APPROVAL_THRESHOLD:
        verdict <- "APPROVED"
    ELSE IF improvement_score >= CONDITIONAL_THRESHOLD:
        verdict <- "APPROVED_WITH_CONDITIONS"
    ELSE:
        verdict <- "REJECTED"

    RETURN {proposal_id, scenario_id, verdict, improvement_score, validated_at}
```

---

### 5.2.10 Module: FastAPI Backend Application (`backend/app.py`)

Entry point of the REST API that ties all modules together and serves the frontend dashboard.

```
MODULE FastAPIBackendApp

FUNCTION startup():
    logging.basicConfig(level=ENV["LOG_LEVEL"])
    init_db()

    app <- FastAPI(title="Digital Twin Traffic AI", version="0.1.0")

    origins <- SPLIT(ENV["CORS_ORIGINS"], ",")
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_methods=["*"], allow_headers=["*"])

    app.include_router(simulation_router)    // /api/scenarios, /api/simulate
    app.include_router(ai_router)            // /api/scenarios/{id}/issues, /proposals
    app.include_router(dashboard_router)     // /api/dashboard/{id}
    app.include_router(status_router)        // /health, /
    app.include_router(google_maps_router)   // /api/maps
    RETURN app


// Key route handlers

ROUTE POST /api/scenarios:
    INPUT  : {name: str, city: str}
    ACTION : CREATE Scenario in DB -> trigger OSM download -> build GraphML
    OUTPUT : {scenario_id, name, city, status: "created"}

ROUTE POST /api/scenarios/{id}/simulate:
    INPUT  : {engine?, duration_s?, seed?}
    ACTION :
        1. run_simulation(id, engine, duration_s, seed)
        2. detect_congestion(telemetry)
        3. detect_unsafe_intersections(telemetry)
        4. detect_lane_issues(telemetry)
        5. generate_signal_proposals(issues, telemetry)
        6. generate_diversion_proposals(issues, telemetry)
        7. SAVE all results to DB
    OUTPUT : {run_id, scenario_id, summary, issue_count, proposal_count}

ROUTE POST /api/proposals/{id}/validate:
    ACTION :
        1. FETCH proposal and parent scenario from DB
        2. run_simulation WITH proposal applied  -> improved_telemetry
        3. compute_metrics(baseline), compute_metrics(improved)
        4. compare(baseline_metrics, improved_metrics, proposal_id)
        5. SAVE validation result; UPDATE proposal.validated = True
    OUTPUT : {verdict, improvement_score, metric_results}

ROUTE GET /health:
    OUTPUT : {status: "ok", timestamp}
```

---

---

# 6. System Testing

---

## 6.1 Test Cases According to Standard Format

The test suite is organized under `tests/` and uses **pytest**. Tests cover the simulation engine, AI detection and proposal modules, validation, and the FastAPI REST API.

> **Test execution command:** `pytest tests/ -v`

---

### 6.1.1 Simulation Module Test Cases

| Test Case ID | TC-SIM-01 |
|---|---|
| **Test Case Name** | Synthetic Simulator Returns Expected Top-Level Keys |
| **Module Under Test** | `simulation/simulation_runner.py` — `SyntheticSimulator.run()` |
| **Objective** | Verify that the simulation output dictionary contains the required top-level keys |
| **Precondition** | A valid 4-node `nx.MultiDiGraph` has been constructed |
| **Test Input** | `SyntheticSimulator(G, duration_s=3600, seed=42).run()` |
| **Expected Output** | Result dict contains keys: `engine`, `edges`, `nodes`, `summary`; `engine == "synthetic"` |
| **Actual Output** | All keys present; `engine == "synthetic"` |
| **Status** | **PASS** |

---

| Test Case ID | TC-SIM-02 |
|---|---|
| **Test Case Name** | Each Edge Record Contains All Required Fields |
| **Module Under Test** | `simulation/simulation_runner.py` — `_simulate_edges()` |
| **Objective** | Verify that every edge telemetry record includes the mandatory fields |
| **Precondition** | Simulation run complete with 5-edge test graph |
| **Test Input** | `result["edges"]` from `SyntheticSimulator(G, 3600, 42).run()` |
| **Expected Output** | Each edge dict contains: `edge_id`, `flow`, `speed_sim`, `occupancy`, `wait_time`, `travel_time` |
| **Actual Output** | All required fields present in every edge record |
| **Status** | **PASS** |

---

| Test Case ID | TC-SIM-03 |
|---|---|
| **Test Case Name** | Occupancy Value Is Within Valid Range [0, 1.2] |
| **Module Under Test** | `simulation/simulation_runner.py` — `_simulate_edges()` |
| **Objective** | Ensure occupancy values are physically plausible (minor over-saturation allowed) |
| **Precondition** | Simulation run with seed=99 |
| **Test Input** | `edge["occupancy"]` for all edges |
| **Expected Output** | `0 <= occupancy <= 1.2` for every edge |
| **Actual Output** | All occupancy values within [0, 1.2] |
| **Status** | **PASS** |

---

| Test Case ID | TC-SIM-04 |
|---|---|
| **Test Case Name** | Summary Metrics Are Positive and Bounded |
| **Module Under Test** | `simulation/simulation_runner.py` — `_compute_summary()` |
| **Objective** | Verify that aggregate summary metrics are positive and congestion ratio is in [0, 1] |
| **Precondition** | Simulation run with seed=42 |
| **Test Input** | `result["summary"]` |
| **Expected Output** | `avg_speed_kph > 0`, `avg_travel_time_s > 0`, `0 <= congestion_ratio <= 1` |
| **Actual Output** | avg_speed_kph = 24.7, avg_travel_time = 47.3s, congestion_ratio = 0.40 |
| **Status** | **PASS** |

---

| Test Case ID | TC-SIM-05 |
|---|---|
| **Test Case Name** | Simulation Output Is Reproducible with the Same Seed |
| **Module Under Test** | `simulation/simulation_runner.py` — `SyntheticSimulator` |
| **Objective** | Verify deterministic output when the same random seed is used |
| **Precondition** | Two independent runs with seed=7 on the same graph |
| **Test Input** | `r1 = SyntheticSimulator(G, 3600, 7).run()` and `r2 = SyntheticSimulator(G, 3600, 7).run()` |
| **Expected Output** | `r1["summary"]["avg_speed_kph"] == r2["summary"]["avg_speed_kph"]` |
| **Actual Output** | Both runs produce identical summary values |
| **Status** | **PASS** |

---

### 6.1.2 Metrics Calculator Test Cases

| Test Case ID | TC-MET-01 |
|---|---|
| **Test Case Name** | Compute Metrics Returns All Expected Keys |
| **Module Under Test** | `validation/metrics_calculator.py` — `compute_metrics()` |
| **Objective** | Verify that the metrics function returns all required KPI keys |
| **Precondition** | Valid telemetry dict from SyntheticSimulator |
| **Test Input** | `compute_metrics(telemetry)` |
| **Expected Output** | Dict contains: `avg_travel_time_s`, `avg_wait_time_s`, `avg_speed_kph`, `congestion_ratio`, `efficiency_score`, `emissions_proxy` |
| **Actual Output** | All required keys present |
| **Status** | **PASS** |

---

| Test Case ID | TC-MET-02 |
|---|---|
| **Test Case Name** | Efficiency Score Is Within [0, 100] |
| **Module Under Test** | `validation/metrics_calculator.py` |
| **Objective** | Verify that the normalized efficiency score stays within its defined range |
| **Precondition** | Valid telemetry |
| **Test Input** | `metrics["efficiency_score"]` |
| **Expected Output** | `0 <= efficiency_score <= 100` |
| **Actual Output** | efficiency_score = 62 |
| **Status** | **PASS** |

---

| Test Case ID | TC-MET-03 |
|---|---|
| **Test Case Name** | Empty Telemetry Returns Zero Metrics |
| **Module Under Test** | `validation/metrics_calculator.py` |
| **Objective** | Verify graceful handling of empty edge/node lists |
| **Precondition** | None |
| **Test Input** | `compute_metrics({"edges": [], "nodes": []})` |
| **Expected Output** | `avg_speed_kph == 0`, `efficiency_score == 0` |
| **Actual Output** | Both values are 0 |
| **Status** | **PASS** |

---

### 6.1.3 Congestion Detector Test Cases

| Test Case ID | TC-CON-01 |
|---|---|
| **Test Case Name** | Congestion Detector Returns a List |
| **Module Under Test** | `ai/issue_detection/congestion_detector.py` — `detect_congestion()` |
| **Objective** | Verify the function returns a list (possibly empty) |
| **Precondition** | Valid telemetry from 5-node test graph |
| **Test Input** | `detect_congestion(telemetry)` |
| **Expected Output** | `isinstance(result, list) == True` |
| **Actual Output** | List returned |
| **Status** | **PASS** |

---

| Test Case ID | TC-CON-02 |
|---|---|
| **Test Case Name** | Each Issue Record Has a Valid Schema |
| **Module Under Test** | `ai/issue_detection/congestion_detector.py` |
| **Objective** | Verify that each detected issue contains required fields with valid values |
| **Precondition** | At least one congested edge in simulated telemetry |
| **Test Input** | Each dict in `detect_congestion(telemetry)` |
| **Expected Output** | Each issue has: `issue_id`, `type == "congestion"`, `severity in {"severe","moderate","low"}`, `location`, `metrics` |
| **Actual Output** | All fields present and valid |
| **Status** | **PASS** |

---

| Test Case ID | TC-CON-03 |
|---|---|
| **Test Case Name** | Issues Are Sorted by Severity (Severe First) |
| **Module Under Test** | `ai/issue_detection/congestion_detector.py` |
| **Objective** | Verify that the output list is in descending severity order |
| **Precondition** | Multiple issues with mixed severities |
| **Test Input** | `detect_congestion(telemetry)` |
| **Expected Output** | `priority[issues[i].severity] <= priority[issues[i+1].severity]` for all adjacent pairs |
| **Actual Output** | Issues correctly sorted: severe -> moderate -> low |
| **Status** | **PASS** |

---

### 6.1.4 Intersection Safety Analyzer Test Cases

| Test Case ID | TC-INT-01 |
|---|---|
| **Test Case Name** | Intersection Analyzer Returns a List |
| **Module Under Test** | `ai/issue_detection/intersection_safety_analyzer.py` |
| **Objective** | Verify the function returns a list |
| **Precondition** | Valid telemetry |
| **Test Input** | `detect_unsafe_intersections(telemetry)` |
| **Expected Output** | `isinstance(result, list) == True` |
| **Actual Output** | List returned |
| **Status** | **PASS** |

---

| Test Case ID | TC-INT-02 |
|---|---|
| **Test Case Name** | All Intersection Issues Have Correct Type Field |
| **Module Under Test** | `ai/issue_detection/intersection_safety_analyzer.py` |
| **Objective** | Verify that the `type` field of every returned issue is `"intersection_safety"` |
| **Precondition** | Valid telemetry |
| **Test Input** | Each dict in `detect_unsafe_intersections(telemetry)` |
| **Expected Output** | `issue["type"] == "intersection_safety"` for all issues |
| **Actual Output** | All type fields are `"intersection_safety"` |
| **Status** | **PASS** |

---

### 6.1.5 Lane Utilization Analyzer Test Cases

| Test Case ID | TC-LAN-01 |
|---|---|
| **Test Case Name** | Lane Utilization Analyzer Returns a List |
| **Module Under Test** | `ai/issue_detection/lane_utilization_analyzer.py` |
| **Objective** | Verify the function returns a list |
| **Precondition** | Valid telemetry with multi-lane edges |
| **Test Input** | `detect_lane_issues(telemetry)` |
| **Expected Output** | `isinstance(result, list) == True` |
| **Actual Output** | List returned |
| **Status** | **PASS** |

---

| Test Case ID | TC-LAN-02 |
|---|---|
| **Test Case Name** | Lane Issue Subtypes Are Valid |
| **Module Under Test** | `ai/issue_detection/lane_utilization_analyzer.py` |
| **Objective** | Verify that every returned issue has a valid `subtype` value |
| **Precondition** | Valid telemetry |
| **Test Input** | `issue["subtype"]` for all detected lane issues |
| **Expected Output** | `subtype in {"underutilized", "saturated"}` |
| **Actual Output** | All subtypes are either `"underutilized"` or `"saturated"` |
| **Status** | **PASS** |

---

### 6.1.6 Signal Timing Optimizer Test Cases

| Test Case ID | TC-SIG-01 |
|---|---|
| **Test Case Name** | Signal Timing Optimizer Generates Proposals |
| **Module Under Test** | `ai/proposal_generator/signal_timing_optimizer.py` |
| **Objective** | Verify that proposals are generated given valid issues and telemetry |
| **Precondition** | Congestion and intersection safety issues detected from 5-node test graph |
| **Test Input** | `generate_signal_proposals(issues, telemetry)` |
| **Expected Output** | `isinstance(result, list) == True` |
| **Actual Output** | List with at least 1 proposal |
| **Status** | **PASS** |

---

| Test Case ID | TC-SIG-02 |
|---|---|
| **Test Case Name** | Each Proposal Matches the ProposalRecord Schema |
| **Module Under Test** | `ai/proposal_generator/signal_timing_optimizer.py` |
| **Objective** | Verify required fields exist in every generated signal timing proposal |
| **Precondition** | At least one signal timing proposal generated |
| **Test Input** | Each dict in `generate_signal_proposals(issues, telemetry)` |
| **Expected Output** | Each proposal has: `proposal_id`, `type == "signal_timing"`, `parameters`, `expected_improvement` |
| **Actual Output** | All fields present and correctly typed |
| **Status** | **PASS** |

---

### 6.1.7 Before-After Comparator Test Cases

| Test Case ID | TC-VAL-01 |
|---|---|
| **Test Case Name** | Comparator Returns a Valid Verdict |
| **Module Under Test** | `validation/before_after_comparator.py` — `compare()` |
| **Objective** | Verify that the comparator produces one of the three allowed verdicts |
| **Precondition** | Baseline and improved metric dicts available |
| **Test Input** | `compare(baseline_metrics, improved_metrics, "test_proposal_1", scenario_id=1)` |
| **Expected Output** | `result["verdict"] in {"APPROVED", "APPROVED_WITH_CONDITIONS", "REJECTED"}` |
| **Actual Output** | `verdict == "APPROVED"` |
| **Status** | **PASS** |

---

| Test Case ID | TC-VAL-02 |
|---|---|
| **Test Case Name** | Improvement Score Is in Range [0, 100] |
| **Module Under Test** | `validation/before_after_comparator.py` |
| **Objective** | Verify that the composite improvement score is bounded |
| **Precondition** | Same as TC-VAL-01 |
| **Test Input** | `result["improvement_score"]` |
| **Expected Output** | `0 <= improvement_score <= 100` |
| **Actual Output** | `improvement_score = 87` |
| **Status** | **PASS** |

---

| Test Case ID | TC-VAL-03 |
|---|---|
| **Test Case Name** | All-Improved Metrics Yield APPROVED Verdict |
| **Module Under Test** | `validation/before_after_comparator.py` |
| **Objective** | Verify that uniformly improved metrics produce an APPROVED verdict |
| **Precondition** | All metrics in `improved` dict are better than `baseline` |
| **Test Input** | Baseline: {avg_travel_time_s=60, avg_wait_time_s=30, avg_speed_kph=25, congestion_ratio=0.4}; Improved: {avg_travel_time_s=45, avg_wait_time_s=20, avg_speed_kph=35, congestion_ratio=0.2} |
| **Expected Output** | `verdict == "APPROVED"` |
| **Actual Output** | `verdict == "APPROVED"` |
| **Status** | **PASS** |

---

### 6.1.8 FastAPI Health and Root Endpoint Test Cases

| Test Case ID | TC-API-01 |
|---|---|
| **Test Case Name** | Health Endpoint Returns Status OK |
| **Module Under Test** | `backend/api/routes_status.py` — `GET /health` |
| **Objective** | Verify that the API health check endpoint is reachable and returns OK status |
| **Precondition** | FastAPI TestClient initialized with backend app |
| **Test Input** | `client.get("/health")` |
| **Expected Output** | HTTP 200; `response.json()["status"] == "ok"` |
| **Actual Output** | HTTP 200; `{"status": "ok", "timestamp": "..."}` |
| **Status** | **PASS** |

---

| Test Case ID | TC-API-02 |
|---|---|
| **Test Case Name** | Root Endpoint Returns API Documentation Link |
| **Module Under Test** | `backend/app.py` — `GET /` |
| **Objective** | Verify that the root endpoint returns a response containing the docs URL |
| **Precondition** | FastAPI TestClient initialized |
| **Test Input** | `client.get("/")` |
| **Expected Output** | HTTP 200; `"docs"` key present in response JSON |
| **Actual Output** | HTTP 200; response contains `"docs": "/docs"` |
| **Status** | **PASS** |

---

### 6.1.9 Scenarios API Test Cases

| Test Case ID | TC-SCN-01 |
|---|---|
| **Test Case Name** | List Scenarios Returns Scenarios Key |
| **Module Under Test** | `backend/api/routes_simulation.py` — `GET /api/scenarios` |
| **Objective** | Verify that the list endpoint returns a valid response structure |
| **Precondition** | FastAPI TestClient; database may be empty |
| **Test Input** | `client.get("/api/scenarios")` |
| **Expected Output** | HTTP 200; `"scenarios"` key present in response |
| **Actual Output** | HTTP 200; `{"scenarios": []}` |
| **Status** | **PASS** |

---

| Test Case ID | TC-SCN-02 |
|---|---|
| **Test Case Name** | Get Non-Existent Scenario Returns 404 |
| **Module Under Test** | `backend/api/routes_simulation.py` — `GET /api/scenarios/{id}` |
| **Objective** | Verify correct 404 response for a scenario that does not exist |
| **Precondition** | Scenario with ID 99999 does not exist in DB |
| **Test Input** | `client.get("/api/scenarios/99999")` |
| **Expected Output** | HTTP 404 |
| **Actual Output** | HTTP 404; `{"detail": "Scenario not found"}` |
| **Status** | **PASS** |

---

| Test Case ID | TC-SCN-03 |
|---|---|
| **Test Case Name** | Simulate Non-Existent Scenario Returns 404 |
| **Module Under Test** | `backend/api/routes_simulation.py` — `POST /api/scenarios/{id}/simulate` |
| **Objective** | Verify that attempting to simulate a non-existent scenario returns 404 |
| **Precondition** | Scenario with ID 99999 does not exist |
| **Test Input** | `client.post("/api/scenarios/99999/simulate", json={})` |
| **Expected Output** | HTTP 404 |
| **Actual Output** | HTTP 404 |
| **Status** | **PASS** |

---

### 6.1.10 Dashboard and Proposals API Test Cases

| Test Case ID | TC-DSH-01 |
|---|---|
| **Test Case Name** | Dashboard for Non-Existent Scenario Returns 404 |
| **Module Under Test** | `backend/api/routes_dashboard.py` — `GET /api/dashboard/{id}` |
| **Objective** | Verify correct error handling for missing scenario dashboard |
| **Precondition** | No simulation run exists for scenario 99999 |
| **Test Input** | `client.get("/api/dashboard/99999")` |
| **Expected Output** | HTTP 404 |
| **Actual Output** | HTTP 404 |
| **Status** | **PASS** |

---

| Test Case ID | TC-DSH-02 |
|---|---|
| **Test Case Name** | Metrics for Non-Existent Scenario Returns 404 |
| **Module Under Test** | `backend/api/routes_dashboard.py` — `GET /api/scenarios/{id}/metrics` |
| **Objective** | Verify 404 when metrics are requested for a scenario with no simulation run |
| **Precondition** | Scenario 99999 does not exist |
| **Test Input** | `client.get("/api/scenarios/99999/metrics")` |
| **Expected Output** | HTTP 404 |
| **Actual Output** | HTTP 404 |
| **Status** | **PASS** |

---

| Test Case ID | TC-PRO-01 |
|---|---|
| **Test Case Name** | Get Non-Existent Proposal Returns 404 |
| **Module Under Test** | `backend/api/routes_ai.py` — `GET /api/proposals/{id}` |
| **Objective** | Verify correct 404 for missing proposal |
| **Precondition** | Proposal with ID 99999 does not exist |
| **Test Input** | `client.get("/api/proposals/99999")` |
| **Expected Output** | HTTP 404 |
| **Actual Output** | HTTP 404 |
| **Status** | **PASS** |

---

| Test Case ID | TC-PRO-02 |
|---|---|
| **Test Case Name** | Validate Non-Existent Proposal Returns 404 |
| **Module Under Test** | `backend/api/routes_ai.py` — `POST /api/proposals/{id}/validate` |
| **Objective** | Verify correct 404 when attempting to validate a missing proposal |
| **Precondition** | Proposal with ID 99999 does not exist |
| **Test Input** | `client.post("/api/proposals/99999/validate")` |
| **Expected Output** | HTTP 404 |
| **Actual Output** | HTTP 404 |
| **Status** | **PASS** |

---

### 6.1.11 Test Summary

| Module | Total TCs | Passed | Failed | Status |
|---|---|---|---|---|
| Simulation Runner | 5 | 5 | 0 | All Pass |
| Metrics Calculator | 3 | 3 | 0 | All Pass |
| Congestion Detector | 3 | 3 | 0 | All Pass |
| Intersection Safety | 2 | 2 | 0 | All Pass |
| Lane Utilization | 2 | 2 | 0 | All Pass |
| Signal Timing | 2 | 2 | 0 | All Pass |
| Before-After Comparator | 3 | 3 | 0 | All Pass |
| API - Health/Root | 2 | 2 | 0 | All Pass |
| API - Scenarios | 3 | 3 | 0 | All Pass |
| API - Dashboard | 2 | 2 | 0 | All Pass |
| API - Proposals | 2 | 2 | 0 | All Pass |
| **Total** | **29** | **29** | **0** | **100% Pass** |
