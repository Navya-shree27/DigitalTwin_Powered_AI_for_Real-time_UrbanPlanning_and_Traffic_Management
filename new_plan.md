# Traffic Digital Twin Sandbox --- Master Plan

## Objective

Build a production-grade traffic simulation sandbox for any city in
India that:

-   Automatically downloads road data from OpenStreetMap
-   Builds a SUMO simulation network
-   Generates or imports traffic demand
-   Runs a live visual simulation
-   Uses AI agents to analyze traffic behavior
-   Detects flaws in existing road planning
-   Allows users to modify roads, junctions, signals, and policies
-   Simulates proposed changes
-   Provides AI-generated recommendations and impact estimates

------------------------------------------------------------------------

# High-Level Architecture

``` text
User Web UI
     |
     v
Backend API (FastAPI)
     |
     +--> OSM Downloader
     +--> SUMO Network Builder
     +--> Traffic Demand Generator
     +--> Scenario Manager
     +--> AI Analysis Engine
     +--> Optimization Engine
     |
     v
SUMO + TraCI
     |
     v
Live Metrics Stream (WebSocket)
     |
     v
Frontend Visualization (Map + Charts + Simulation)
```

------------------------------------------------------------------------

# Core Technologies

  Component             Technology
  --------------------- -----------------------
  Backend API           FastAPI
  Frontend              Next.js + React
  Mapping               MapLibre GL / Leaflet
  Simulation            SUMO
  AI Agents             Python
  RL Framework          Stable-Baselines3
  Data Processing       Pandas / NumPy
  Geospatial            GeoPandas / OSMnx
  Optimization          OR-Tools
  Real-time Streaming   WebSockets
  Storage               PostgreSQL + PostGIS
  Deployment            Docker Compose

------------------------------------------------------------------------

# Project Structure

``` text
traffic-digital-twin/
├── backend/
├── frontend/
├── ai/
├── simulation/
├── data/
├── scenarios/
├── reports/
├── docker/
└── scripts/
```

------------------------------------------------------------------------

# Phase 1 --- Environment Setup

## Automatic Installation Script

Create:

``` text
scripts/setup.sh
scripts/setup.ps1
```

Install automatically:

-   Python 3.11+
-   SUMO
-   Java (if required by tools)
-   Git
-   Node.js
-   Docker

## Python Dependencies

``` bash
pip install fastapi uvicorn traci sumolib osmnx geopandas pandas numpy shapely scikit-learn stable-baselines3 ortools networkx
```

## Frontend Dependencies

``` bash
npm install next react react-dom maplibre-gl socket.io-client recharts
```

------------------------------------------------------------------------

# Phase 2 --- Automatic City Download

## User Input

``` json
{
  "city": "Bangalore",
  "bbox": [south, west, north, east]
}
```

## Download via OSMnx

``` python
import osmnx as ox

G = ox.graph_from_place("Bangalore, Karnataka, India", network_type="drive")
ox.save_graph_xml(G, "data/bangalore.osm")
```

------------------------------------------------------------------------

# Phase 3 --- Build SUMO Network

## Convert OSM to SUMO

``` bash
netconvert --osm-files data/bangalore.osm -o simulation/bangalore.net.xml
```

## Auto-clean network

Enable:

-   remove isolated edges
-   simplify junctions
-   guess traffic lights
-   infer lane counts

------------------------------------------------------------------------

# Phase 4 --- Generate Traffic Demand

## Synthetic Demand

``` bash
python $SUMO_HOME/tools/randomTrips.py -n simulation/bangalore.net.xml -o simulation/trips.trips.xml
```

``` bash
duarouter -n simulation/bangalore.net.xml -t simulation/trips.trips.xml -o simulation/routes.rou.xml
```

## Real Demand (Advanced)

Support:

-   GPS traces
-   bus routes
-   OD matrices
-   traffic counts
-   event-based demand

------------------------------------------------------------------------

# Phase 5 --- Live Simulation Engine

## Start SUMO

``` python
traci.start(["sumo-gui", "-c", "simulation/bangalore.sumocfg"])
```

## Stream Metrics

Every simulation step:

``` python
{
  "vehicle_count": 1250,
  "avg_speed": 18.4,
  "congested_edges": 42,
  "waiting_time": 3250
}
```

Send via WebSocket.

------------------------------------------------------------------------

# Phase 6 --- Visual Frontend

## Features

-   Interactive map
-   Live vehicle positions
-   Heatmap of congestion
-   Signal state visualization
-   Queue lengths
-   Playback controls
-   Time slider
-   Scenario comparison

## User Editing Tools

Allow users to:

-   Add/remove traffic signals
-   Change signal timing
-   Add lane
-   Remove lane
-   Change speed limit
-   Close road
-   Add flyover
-   Add one-way restriction
-   Remove junction
-   Add roundabout

Changes should generate a new scenario automatically.

------------------------------------------------------------------------

# Phase 7 --- AI Analysis Engine

## Detect Planning Flaws

### Signal Timing Issues

Detect:

-   excessive queue
-   green starvation
-   unbalanced phases

### Road Width Problems

Detect:

-   demand exceeds capacity
-   bottleneck formation
-   lane drop congestion

### Junction Issues

Detect:

-   unnecessary intersections
-   closely spaced signals
-   high-conflict junctions
-   inefficient turning movements

### Network Issues

Detect:

-   dead-end collectors
-   poor connectivity
-   excessive detours
-   overloaded corridors

------------------------------------------------------------------------

# Phase 8 --- AI Recommendation Engine

For each detected issue:

``` json
{
  "issue": "Signal at Silk Board causes 420s average delay",
  "recommendation": "Increase east-west green phase by 12 seconds",
  "expected_improvement": {
    "delay_reduction": "28%",
    "queue_reduction": "31%",
    "travel_time_reduction": "14%"
  }
}
```

------------------------------------------------------------------------

# Phase 9 --- Optimization Engine

## Automatic Experiments

For each issue:

1.  Clone scenario
2.  Apply modification
3.  Run simulation
4.  Measure impact
5.  Rank results

## Optimization Techniques

-   Genetic Algorithm
-   Simulated Annealing
-   Reinforcement Learning
-   Bayesian Optimization

------------------------------------------------------------------------

# Phase 10 --- AI Agents

## Signal Agent

Controls traffic lights dynamically.

## Routing Agent

Re-routes vehicles around congestion.

## Emergency Agent

Prioritizes ambulances/fire trucks.

## Infrastructure Agent

Proposes physical road modifications.

------------------------------------------------------------------------

# Phase 11 --- Sandbox Workflow

## Example

User selects:

``` text
Bangalore → Silk Board Junction
```

System automatically:

1.  Downloads map
2.  Builds network
3.  Generates traffic
4.  Starts simulation
5.  Detects congestion
6.  Suggests improvements
7.  Runs alternative scenarios
8.  Displays comparison

------------------------------------------------------------------------

# Phase 12 --- Output Reports

Generate:

``` text
reports/
├── current_network_report.md
├── congestion_report.md
├── signal_analysis.md
├── recommended_changes.md
└── best_scenario.md
```

## Example Output

``` text
Issue: Junction spacing too small
Location: Hosur Road
Impact: 18% additional delay

Recommended:
- Remove intermediate signal
- Convert to coordinated corridor

Expected:
- Delay: -22%
- Queue length: -30%
```

------------------------------------------------------------------------

# Phase 13 --- Simulation Accuracy

## Calibration

Tune:

-   acceleration
-   deceleration
-   reaction time
-   lane-changing behavior
-   speed distributions

## Validation

Compare against:

-   Google travel times
-   government traffic counts
-   GPS probe data

------------------------------------------------------------------------

# Phase 14 --- Performance Scaling

## City-Level Simulation

Use:

-   headless SUMO
-   distributed workers
-   tiled network partitions
-   asynchronous AI analysis

Target:

  City     Vehicles
  -------- ----------
  Small    10k
  Medium   50k
  Large    200k+

------------------------------------------------------------------------

# Phase 15 --- APIs

## Create Scenario

``` http
POST /scenario
```

## Run Simulation

``` http
POST /scenario/{id}/run
```

## Apply Modification

``` http
POST /scenario/{id}/modify
```

## Get AI Recommendations

``` http
GET /scenario/{id}/recommendations
```

------------------------------------------------------------------------

# Phase 16 --- Production Deployment

## Docker Compose

Services:

-   frontend
-   backend
-   postgres
-   redis
-   sumo-worker
-   ai-worker

## Cloud

Recommended:

-   AWS ECS
-   GCP Cloud Run
-   Azure Container Apps

------------------------------------------------------------------------

# Expected Final User Experience

``` text
1. User enters city name
2. Map loads automatically
3. Live traffic simulation starts
4. AI highlights problematic locations
5. User edits roads/signals
6. Simulation reruns instantly
7. AI compares before vs after
8. User exports report
```

------------------------------------------------------------------------

# Success Criteria

The project is considered complete when it can:

-   Simulate any Indian city from OSM automatically
-   Run live visual traffic simulation
-   Detect planning flaws automatically
-   Allow interactive road editing
-   Re-simulate proposed changes
-   Provide AI-generated recommendations
-   Estimate improvement percentages
-   Export professional analysis reports

------------------------------------------------------------------------

# Recommended Development Order

1.  OSM Download
2.  SUMO Network Build
3.  Live Simulation
4.  Frontend Visualization
5.  User Editing
6.  AI Analysis
7.  Recommendation Engine
8.  Optimization Engine
9.  RL Agents
10. Production Deployment

This order minimizes rework and produces a usable prototype early while
enabling progressively more advanced AI-driven traffic planning
capabilities.


---

# Existing Projects and Inspirations

This project combines capabilities that currently exist across several different platforms. The following projects should be used as architectural and feature references during development.

## 1. Eclipse SUMO

**Use for**
- Traffic simulation core
- Vehicle behavior modeling
- Signal control APIs
- Route assignment
- Traffic metrics generation

**Components to study**
- `sumo-gui`
- `TraCI`
- `sumolib`
- `netedit`

**Inspiration**
The entire simulation engine of the project will be built around SUMO.

---

## 2. OSMnx

**Use for**
- Automatic city download
- OpenStreetMap processing
- Road network extraction
- Geospatial analysis

**Inspiration**
Provides the “one-click import any Indian city” capability.

---

## 3. CARLA

**Use for**
- Interactive simulation sandbox
- Live visualization
- Scenario management
- Agent-based control

**Inspiration**
Reference for building an editable digital twin environment with AI agents.

---

## 4. Flow (UC Berkeley)

**Use for**
- Reinforcement learning with SUMO
- Multi-agent traffic control
- AI-driven signal optimization

**Inspiration**
Reference implementation for connecting RL agents to SUMO via TraCI.

---

## 5. CityFlow

**Use for**
- Large-scale city simulation
- High-performance traffic processing
- Multi-intersection optimization

**Inspiration**
Useful when scaling simulations to entire metropolitan regions.

---

## 6. PressLight

**Use for**
- RL-based traffic signal optimization
- Queue-aware control policies
- Reward function design

**Inspiration**
Basis for the “AI suggests better signal timings” feature.

---

## 7. CoLight

**Use for**
- Coordinated traffic signal control
- Graph neural network approaches

**Inspiration**
Useful for corridor-level and network-level signal coordination.

---

## 8. Aimsun

**Use for**
- Professional traffic engineering analysis
- Scenario comparison
- Capacity and bottleneck analysis
- Level-of-service evaluation

**Inspiration**
Benchmark for report quality and planning recommendations.

---

## 9. PTV Vissim

**Use for**
- Microscopic traffic modeling
- Signal timing evaluation
- Infrastructure testing

**Inspiration**
Reference for simulation fidelity and engineering workflows.

---

## 10. MATSim

**Use for**
- City-scale travel demand modeling
- Origin–destination simulation
- Policy impact studies

**Inspiration**
Future extension for realistic commuter behavior in Indian cities.

---

# Feature Mapping

| Capability | Reference Project | Planned Implementation |
|---|---|---|
| OSM Import | OSMnx | ✓ |
| Traffic Simulation | SUMO | ✓ |
| Live Visualization | SUMO / CARLA | ✓ |
| User Editing | NetEdit | ✓ |
| AI Signal Control | Flow / PressLight | ✓ |
| Infrastructure Recommendations | Aimsun / Vissim | ✓ |
| Scenario Comparison | Aimsun | ✓ |
| City-Scale Demand Modeling | MATSim | Future |
| Multi-Agent Optimization | CoLight / Flow | ✓ |

---

# What Makes This Project Unique

The planned platform combines:

```text
OpenStreetMap + SUMO + Live Web Visualization + Editable Sandbox + AI Planning Advisor