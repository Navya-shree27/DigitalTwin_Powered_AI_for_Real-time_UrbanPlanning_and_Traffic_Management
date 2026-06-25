# Digital Twin Powered AI for Real-Time Urban Planning and Traffic Management

> **Course:** Major Project Phase 1 (BCS685) — Department of CSE, BIET Davanagere  
> **Team:** Afifa M Makandar, Ayush R, Mohammad Salman R, Navya Shree A R  
> **Guide:** Dr. Usha G R

## Overview

This system builds a real-time **Digital Twin** of a city's road network using OpenStreetMap data, runs it through a traffic micro-simulator, and layers an **AI City Inspector Agent** on top. The agent studies simulated traffic, finds problems (congestion, unsafe intersections, poor lane usage), proposes fixes (signal retiming, lane changes, route diversions), re-simulates those fixes, and presents everything on an interactive dashboard.

```
OSM Data → Simulation Engine → Issue Detection + LLM Agent → Proposals → Validation → Dashboard
```

---

## Architecture

```
digital-twin-traffic-ai/
├── data/               # Raw OSM extracts and processed network files
├── simulation/         # Network conversion and traffic simulation runner
├── agents/
│   ├── city_inspector_agent/   # LLM-based reasoning agent
│   ├── issue_detection/        # Rule-based congestion/safety/lane detectors
│   └── proposal_generator/     # Signal timing, lane change, route diversion
├── validation/         # Before/after KPI comparison
├── backend/            # FastAPI REST API
├── frontend/           # React + Deck.gl interactive dashboard
├── notebooks/          # Exploratory analysis
├── tests/              # Pytest test suite
└── docs/               # Architecture and API reference
```

---

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- Git

### 1. Clone & set up Python environment

```bash
git clone <repo-url>
cd digital-twin-traffic-ai
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env — add your LLM API key and adjust city bounding box if needed
```

### 3. Start the backend

```bash
cd backend
uvicorn app:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard available at: http://localhost:5173

---

## Running the Pipeline

1. **Create a scenario** (downloads OSM data for Davanagere):
   ```
   POST http://localhost:8000/api/scenarios
   {"name": "Davanagere Peak Hour", "city": "Davanagere, Karnataka, India"}
   ```

2. **Run baseline simulation**:
   ```
   POST http://localhost:8000/api/scenarios/1/simulate
   ```

3. **View detected issues**:
   ```
   GET http://localhost:8000/api/scenarios/1/issues
   ```

4. **View proposals**:
   ```
   GET http://localhost:8000/api/scenarios/1/proposals
   ```

5. **Validate a proposal**:
   ```
   POST http://localhost:8000/api/proposals/1/validate
   ```

6. **Full dashboard payload**:
   ```
   GET http://localhost:8000/api/dashboard/1
   ```

---

## Development Phases

| Phase | Status | Description |
|-------|--------|-------------|
| A — Foundation | ✅ | Repo structure, environment, OSM ingestion |
| B — Baseline Simulation | 🔄 | Full SUMO integration, realistic telemetry |
| C — Detection Layer | ✅ | Rule-based issue detectors |
| D — Agent + Proposal Layer | ✅ | LLM agent + proposal generators |
| E — Validation Layer | ✅ | Before/after KPI comparison |
| F — Backend + Dashboard | ✅ | FastAPI + React dashboard |
| G — Integration & Testing | ⏳ | End-to-end testing, tuning |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.10 |
| Map data | OpenStreetMap via OSMnx |
| Simulation | SUMO / CityFlow (synthetic fallback) |
| AI/ML | PyTorch, Scikit-learn, NumPy, Pandas |
| LLM Agent | Claude (Anthropic API) |
| Geospatial | GeoPandas, Shapely |
| Backend | FastAPI + SQLite (→ PostGIS) |
| Frontend | React + Vite + Deck.gl + Chart.js |

---

## Notes

- The simulator is decoupled from the AI layer — agents only consume structured telemetry, never simulator internals. SUMO can be swapped for CityFlow without rewriting agents.
- In Phase A, synthetic telemetry is generated from OSMnx graph topology (realistic Gaussian noise on edge attributes). Full SUMO wiring comes in Phase B.
- Every baseline and validated run is persisted so the dashboard can show historical before/after comparisons.
