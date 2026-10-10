# Digital Twin Powered AI for Real-Time Urban Planning and Traffic Management

**Course:** Major Project Phase 1 (BCS685)
**Department:** Computer Science and Engineering, BIET Davanagere
**Team:** Afifa M Makandar, Ayush R, Mohammad Salman R, Navya Shree A R
**Guide:** Dr. Usha G R

This document is the implementation blueprint for the project. It defines the architecture, technology stack, folder/file structure, and the responsibility of every module. It does **not** contain executable code — it is meant to be used as a reference while writing the actual codebase.

---

## 1. Project Summary

The system builds a real-time **Digital Twin** of a city's road network using OpenStreetMap data, runs it through a traffic micro-simulator (SUMO or CityFlow), and layers an **AI City Inspector Agent** on top. The agent studies the simulated traffic, finds problems (congestion, unsafe intersections, poor lane usage), and proposes fixes (signal retiming, lane changes, route diversions). Every proposed fix is re-simulated so its impact can be validated before being shown to a planner on an interactive dashboard, in a clear before/after comparison.

---

## 2. Goals Derived from the Objectives

1. Build a realistic, simulation-ready urban network from open map data.
2. Run a multi-agent AI pipeline that analyzes the simulation and produces ranked issues.
3. Generate concrete, data-driven renovation proposals for each issue.
4. Re-simulate proposals and quantify the improvement.
5. Present everything through an interactive 2D/3D dashboard.

---

## 3. High-Level Architecture

The pipeline follows the same five stages shown in the project's methodology diagram:

| Stage | Name | Responsibility |
|---|---|---|
| 1 | Data Ingestion | Pull OpenStreetMap roads, buildings, and height data for the target area |
| 2 | Simulation Engine | Convert map data into a SUMO/CityFlow network and run traffic simulation |
| 3a | LLM Agent (City Inspector) | Reasons over simulation telemetry to interpret and summarize urban issues |
| 3b | Issue Detection | Rule-based and statistical detectors that flag congestion, unsafe intersections, poor lane use |
| 3c | AI Proposal Generator | Converts detected issues into concrete interventions (signal timing, lane changes, diversions) |
| 4 | Simulation Validation | Re-runs the simulation with proposals applied and computes before/after metrics |
| 5 | Interactive Dashboard | Visualizes the map, issues, proposals, and metrics for the end user |

Stages 3a, 3b, and 3c run in parallel on the same simulation output and converge into Stage 4.

---

## 4. Technology Stack

### Core / Simulation
- **Language:** Python 3.10
- **Map data:** OpenStreetMap, fetched via Overpass API / OSMnx
- **Network conversion:** SUMO's `netconvert` / `osmWebWizard`, or CityFlow's map converter
- **Traffic simulation:** SUMO (with TraCI for live control) or CityFlow
- **AI / ML:** PyTorch, NumPy, Pandas, Scikit-learn
- **LLM agent layer:** An LLM API (e.g., Claude or GPT) orchestrated through a lightweight agent framework, used purely for reasoning/summarization over structured simulation metrics — not for controlling the simulation directly
- **Geospatial processing:** GeoPandas, Shapely

### Backend
- **API layer:** FastAPI (preferred) or Flask
- **Database:** PostgreSQL with PostGIS (preferred for geospatial queries) or SQLite for early prototyping
- **Task orchestration:** A simple job queue (e.g., Celery + Redis) if simulations need to run asynchronously

### Frontend
- **Framework:** React (with Node.js tooling)
- **Mapping/visualization:** Deck.gl or Mapbox GL JS for 2D/3D map rendering; Recharts or Chart.js for metric charts

### Dev Tooling
- VS Code / PyCharm, Jupyter Notebook, Git, Docker (optional, for environment consistency)

---

## 5. Repository / Code Structure

```
digital-twin-traffic-ai/
├── README.md
├── requirements.txt
├── package.json
├── .env.example
├── .gitignore
│
├── data/
│   ├── raw/
│   │   └── osm/                       # Raw OSM extracts (.osm / .pbf) for the chosen city area
│   ├── processed/
│   │   └── network/                   # Converted SUMO/CityFlow-ready network files
│   └── scenarios/                     # Saved traffic demand scenarios (peak hour, weekday, etc.)
│
├── simulation/
│   ├── osm_to_network.py              # Converts raw OSM data into a simulator-ready network
│   ├── sumo_config/
│   │   ├── network.net.xml            # Compiled SUMO road network
│   │   ├── routes.rou.xml             # Vehicle route/demand definitions
│   │   └── simulation.sumocfg         # SUMO simulation configuration
│   ├── cityflow_config/
│   │   └── config.json                # CityFlow simulation configuration (alternative engine)
│   ├── simulation_runner.py           # Orchestrates a full simulation run end-to-end
│   └── traci_interface.py             # Live read/write interface into a running SUMO simulation
│
├── agents/
│   ├── city_inspector_agent/
│   │   ├── llm_agent.py               # LLM-based reasoning agent that interprets simulation state
│   │   ├── prompts/
│   │   │   └── inspector_prompts.md   # Prompt templates used by the LLM agent
│   │   └── agent_memory.py            # Stores agent context/history across analysis cycles
│   │
│   ├── issue_detection/
│   │   ├── congestion_detector.py     # Flags congestion hotspots from traffic flow/speed data
│   │   ├── intersection_safety_analyzer.py   # Flags unsafe intersections from conflict/near-miss data
│   │   └── lane_utilization_analyzer.py      # Flags underused or overloaded lanes
│   │
│   └── proposal_generator/
│       ├── signal_timing_optimizer.py # Produces improved traffic-signal timing plans
│       ├── lane_change_recommender.py # Recommends lane reconfiguration changes
│       └── route_diversion_planner.py # Suggests alternate routing to relieve hotspots
│
├── validation/
│   ├── metrics_calculator.py          # Computes KPIs: avg. travel time, wait time, throughput, emissions
│   ├── before_after_comparator.py     # Diffs baseline vs. proposal-applied simulation metrics
│   └── report_generator.py            # Compiles a structured validation report per proposal
│
├── backend/
│   ├── app.py                         # API application entry point
│   ├── api/
│   │   ├── routes_simulation.py       # Endpoints to trigger/inspect simulation runs
│   │   ├── routes_agents.py           # Endpoints to trigger analysis and fetch issues/proposals
│   │   └── routes_dashboard.py        # Endpoints serving aggregated data to the frontend
│   ├── models/
│   │   └── schema.py                  # Data models for issues, proposals, metrics, scenarios
│   └── database/
│       └── db_connector.py            # Database connection and query helpers
│
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   │   ├── MapView/               # 2D/3D map rendering of the city network
│   │   │   ├── MetricsPanel/          # Displays KPI charts
│   │   │   ├── BeforeAfterToggle/     # Lets the user switch between baseline and proposal views
│   │   │   └── IssueList/             # Lists detected issues with severity and location
│   │   ├── pages/
│   │   │   └── Dashboard.jsx          # Main dashboard page composing the above components
│   │   ├── services/
│   │   │   └── apiClient.js           # Wrapper around backend API calls
│   │   └── App.jsx
│   └── package.json
│
├── notebooks/
│   └── exploratory_analysis.ipynb     # Ad-hoc data exploration and prototyping
│
├── tests/
│   ├── test_simulation.py
│   ├── test_agents.py
│   └── test_api.py
│
└── docs/
    ├── architecture.md
    └── api_reference.md
```

---

## 6. Module-by-Module Responsibility

### 6.1 Data Ingestion (`data/`, `simulation/osm_to_network.py`)
- Selects a bounded city area (bounding box or place name).
- Downloads roads, intersections, buildings, and height data from OpenStreetMap.
- Cleans and converts the raw map into a network format consumable by SUMO/CityFlow.
- Output: a versioned, simulator-ready network file stored under `data/processed/network/`.

### 6.2 Simulation Engine (`simulation/`)
- Loads the processed network and a chosen demand scenario.
- Runs the simulation for a fixed time window, recording per-edge, per-lane, and per-intersection telemetry (speed, queue length, waiting time, throughput).
- Exposes a live control interface (TraCI for SUMO) so proposed changes (e.g., new signal timings) can be applied and re-simulated without rebuilding the whole network.

### 6.3 City Inspector Agent — LLM layer (`agents/city_inspector_agent/`)
- Receives structured simulation summaries (not raw simulation logs) from the detection modules.
- Reasons about root causes, prioritizes which issues matter most, and produces a human-readable narrative summary for planners.
- Maintains short-term memory of prior analysis cycles so it can track whether previous proposals improved conditions.

### 6.4 Issue Detection (`agents/issue_detection/`)
- `congestion_detector.py`: identifies road segments/time windows where speed drops and queue length rises beyond a threshold.
- `intersection_safety_analyzer.py`: identifies intersections with high conflict potential based on simulated vehicle interactions.
- `lane_utilization_analyzer.py`: identifies lanes that are consistently empty or consistently saturated relative to their neighbors.
- Each detector outputs a structured issue record: location, type, severity, supporting metrics.

### 6.5 AI Proposal Generator (`agents/proposal_generator/`)
- Consumes issue records and produces one or more candidate interventions per issue.
- `signal_timing_optimizer.py`: proposes revised green/red phase durations for affected intersections.
- `lane_change_recommender.py`: proposes adding, removing, or repurposing lanes.
- `route_diversion_planner.py`: proposes alternate routing to redistribute demand away from hotspots.
- Each proposal is tagged with the issue it addresses and an expected-impact hypothesis.

### 6.6 Simulation Validation (`validation/`)
- Applies each proposal to a copy of the network/scenario and re-runs the simulation.
- Computes the same KPIs as the baseline run (average travel time, wait time, throughput, emissions proxy).
- Produces a before/after comparison so only proposals with a genuine, measurable improvement are surfaced to the dashboard.

### 6.7 Backend API (`backend/`)
- Orchestrates the full pipeline: trigger ingestion, trigger simulation, trigger agent analysis, trigger validation.
- Persists scenarios, issues, proposals, and metrics so the frontend can query them without re-running the pipeline every time.
- Serves aggregated, dashboard-ready payloads (map geometry + issue markers + metrics) to the frontend.

### 6.8 Interactive Dashboard (`frontend/`)
- Renders the city network as a 2D/3D map with issue markers layered on top.
- Lets the planner select an issue to see its proposed fix(es) and expected impact.
- Provides a before/after toggle to visually and numerically compare baseline vs. proposed conditions.

---

## 7. Data Flow Summary

1. A target city area is selected and its OpenStreetMap data is ingested and converted into a network.
2. The network plus a demand scenario is run through the simulator to produce a baseline telemetry dataset.
3. The telemetry feeds three parallel analyses: the LLM Inspector Agent, the rule-based issue detectors, and (once issues exist) the proposal generator.
4. Each generated proposal is applied to a fresh simulation run for validation, producing before/after KPIs.
5. Validated proposals, issues, and metrics are persisted via the backend and rendered on the dashboard.

---

## 8. Suggested API Surface (Backend)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/scenarios` | Create a new simulation scenario from a map area and demand profile |
| POST | `/api/scenarios/{id}/simulate` | Run the baseline simulation for a scenario |
| GET | `/api/scenarios/{id}/issues` | Retrieve detected issues for a scenario |
| GET | `/api/scenarios/{id}/proposals` | Retrieve generated proposals for a scenario's issues |
| POST | `/api/proposals/{id}/validate` | Re-simulate with a proposal applied and return before/after metrics |
| GET | `/api/scenarios/{id}/metrics` | Retrieve baseline KPIs for dashboard charts |
| GET | `/api/dashboard/{scenario_id}` | Retrieve a single aggregated payload for the dashboard view |

---

## 9. System Requirements (from project documentation)

**Hardware**
- CPU: Intel Core i5 / Ryzen 5 or above
- RAM: 16 GB minimum
- Storage: 50 GB SSD
- GPU: NVIDIA GPU with 6 GB VRAM or above
- Stable internet connection

**Software**
- OS: Windows 11 / Ubuntu 22.04
- Python 3.10
- SUMO / CityFlow
- OpenStreetMap data tools
- PyTorch, NumPy, Pandas, Scikit-learn
- React / Node.js
- VS Code or PyCharm, Jupyter Notebook, Git

---

## 10. Suggested Development Phases

**Phase A — Foundation**
Set up the repository structure, environment, and dependency management. Acquire OpenStreetMap data for the target city/area and produce a working SUMO or CityFlow network.

**Phase B — Baseline Simulation**
Get a baseline traffic simulation running end-to-end with a realistic demand scenario, and confirm telemetry can be captured per edge/lane/intersection.

**Phase C — Detection Layer**
Implement the rule-based issue detectors (congestion, intersection safety, lane utilization) against the captured telemetry.

**Phase D — Agent + Proposal Layer**
Integrate the LLM City Inspector Agent for reasoning/summarization, then build the proposal generator modules.

**Phase E — Validation Layer**
Implement re-simulation of proposals and before/after KPI comparison.

**Phase F — Backend + Dashboard**
Build the API layer to orchestrate and persist the pipeline, then build the interactive dashboard for visualization.

**Phase G — Integration & Testing**
End-to-end testing across a full scenario, performance tuning, and documentation.

---

## 11. Notes for Implementation

- Keep the simulator (SUMO/CityFlow) decoupled from the AI layer: the AI modules should only ever consume structured telemetry/metrics, never depend on simulator-specific internals directly. This makes it possible to swap SUMO for CityFlow later without rewriting the agents.
- Treat "issue detection" and "proposal generation" as separate, composable stages rather than one monolithic module — this keeps the system explainable, since every proposal can be traced back to a specific detected issue.
- Persist every baseline and validated run so the dashboard can show historical before/after comparisons, not just the most recent one.