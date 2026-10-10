# Digital Twin Powered AI for Real-Time Urban Planning and Traffic Management

> An AI-assisted urban traffic analysis platform that builds a digital representation of a road network, simulates traffic, detects congestion and safety issues, and evaluates possible interventions.

<p align="center">
  <b>OpenStreetMap · Python · FastAPI · React · Machine Learning · Multi-Agent AI</b>
</p>

## Project Information

- **Project:** Digital Twin Powered AI for Real-Time Urban Planning and Traffic Management
- **Course:** Major Project Phase 1 (BCS685)
- **Department:** Computer Science and Engineering, BIET Davanagere
- **Project Guide:** Dr. Usha G R
- **Team:** Afifa M Makandar, Ayush R, Mohammad Salman R, Navya Shree A R

## Overview

Urban traffic problems are interconnected: congestion, long queues, inefficient signal timing, route bottlenecks, and intersection-safety constraints can all affect travel time and road-network performance. This project combines a digital representation of a road network with simulation, machine learning, rule-based issue detection, and AI-assisted planning to help explore potential improvements.

The system follows an intervention loop:

1. **Create a road-network scenario** from OpenStreetMap data.
2. **Run a baseline simulation** and collect traffic telemetry.
3. **Detect issues** such as congestion hotspots, safety concerns, and lane-utilization problems.
4. **Analyze conditions** using the ML traffic classifier and specialized agents.
5. **Generate intervention proposals**, such as signal-timing adjustments, lane changes, or route diversions.
6. **Validate proposals** by re-simulating and comparing baseline and proposed outcomes.
7. **Review results** through the API and interactive dashboard.

> **Important:** This is a decision-support and simulation project. Results depend on the quality of the road-network data, simulation assumptions, model performance, and configuration. Proposed changes should not be treated as automatically validated real-world traffic-control instructions.

## Key Features

- **Road-network digital twin:** Uses OpenStreetMap road data and OSMnx-based network processing.
- **Traffic simulation:** Supports a synthetic telemetry workflow and integrations/configurations for SUMO/TraCI or CityFlow where the required tools are installed.
- **ML-based congestion classification:** A Random Forest classifier predicts Low, Moderate, or Severe congestion from traffic features.
- **Issue detection:** Modules analyze congestion, intersection safety, and lane utilization.
- **AI-assisted planning:** Specialized agents analyze traffic conditions, assess safety constraints, and help formulate interventions.
- **Intervention proposals:** Includes signal-timing optimization, lane-change recommendations, and route-diversion planning.
- **Before/after validation:** Calculates comparative traffic KPIs after a proposed intervention is simulated.
- **REST API:** FastAPI endpoints expose scenario, simulation, issue, proposal, and dashboard functionality.
- **Interactive dashboard:** React-based frontend with map and chart-related dependencies for viewing network and performance information.
- **Automated tests:** Pytest suites cover API routes, agents, ML behavior, simulation, and intervention workflow components.

## System Architecture

```text
 OpenStreetMap / OSMnx
          |
          v
 Road-Network Processing
          |
          v
 Baseline Traffic Simulation
 (Synthetic / configured simulator)
          |
          v
 Traffic Telemetry and KPIs
          |
          +----------------------------+
          |                            |
          v                            v
 ML Congestion Classifier       Issue Detection
 (Low / Moderate / Severe)      (Congestion / Safety / Lane Use)
          |                            |
          +-------------+--------------+
                        |
                        v
             AI Agent / Orchestrator
                        |
                        v
              Intervention Proposals
          (Signals / Lane Changes / Routes)
                        |
                        v
             Re-simulation and Validation
                        |
                        v
           Before/After KPI Comparison
                        |
                        v
               FastAPI + React UI
```

For more detail, see [System Architecture](docs/architecture.md).

## Technology Stack

| Area | Technologies |
|---|---|
| Language | Python |
| API backend | FastAPI, Uvicorn, Pydantic |
| Frontend | React, Vite, JavaScript |
| Interactive maps and visualization | Deck.gl, MapLibre GL, Chart.js |
| Geospatial processing | OSMnx, GeoPandas, Shapely, NetworkX, PyProj |
| Machine learning | scikit-learn, NumPy, pandas, SciPy |
| Simulation integration | Synthetic telemetry; SUMO/TraCI and CityFlow configurations |
| AI agents / LLM integration | Agent modules; optional Ollama or Anthropic configuration |
| Database | SQLite by default via SQLAlchemy |
| Testing | pytest, pytest-asyncio, HTTPX |

## Repository Structure

The outline below highlights the main modules currently present in the repository. Some generated data, trained model artifacts, and local simulation outputs may need to be created separately.

```text
.
├── agents/
│   ├── city_inspector_agent/       # LLM-based inspection and agent memory
│   ├── issue_detection/            # Congestion, safety, and lane-use detectors
│   ├── proposal_generator/         # Signal, lane, and route interventions
│   ├── multi_agent_framework.py    # Agent framework and LLM integration
│   ├── orchestrator.py             # Coordinates traffic-analysis workflow
│   ├── traffic_analysis_agent.py   # Traffic analysis
│   ├── safety_agent.py             # Safety assessments
│   └── planner_agent.py            # Intervention planning
├── backend/
│   ├── api/                        # Simulation, agent, and dashboard routes
│   ├── database/                   # Database connection and initialization
│   ├── models/                     # API/data schemas
│   └── app.py                      # FastAPI application entry point
├── data/
│   └── scenarios/                  # Scenario data and guidance
├── docs/
│   ├── architecture.md             # System architecture
│   └── api_reference.md            # API reference
├── frontend/
│   ├── src/                        # React application and UI components
│   ├── package.json
│   └── index.html
├── ml/                             # Dataset generation, preprocessing, training, evaluation, inference
├── models/                         # Persisted model/preprocessor artifacts and feature schema
├── results/
│   ├── model_metrics.json          # Recorded evaluation metrics
│   ├── confusion_matrix.png        # Confusion matrix visualization
│   └── feature_importance.png      # Feature-importance visualization
├── simulation/
│   ├── osm_to_network.py           # OSM road-network processing
│   ├── simulation_runner.py        # Simulation execution
│   ├── traci_interface.py          # SUMO/TraCI interface
│   ├── cityflow_config/
│   └── sumo_config/
├── tests/                          # Pytest test suite
├── validation/
│   ├── before_after_comparator.py   # Baseline/proposal comparison
│   ├── metrics_calculator.py       # KPI calculation
│   └── report_generator.py         # Validation report generation
├── .env.example                    # Example environment settings
├── requirements.txt                # Python dependencies
└── README.md
```

The `ml/` and `models/` directories are present in the repository. Trained model binaries and generated datasets may still need to be created locally, depending on which artifacts are tracked in your checkout.

## Prerequisites

- Git
- Python 3.10 or newer (Python 3.13 has been used during project development; dependency compatibility can vary)
- Node.js and npm compatible with the installed Vite version
- Optional: a supported local LLM runtime and downloaded model for local LLM features
- Optional: SUMO installed and configured when using the SUMO/TraCI engine; CityFlow for a CityFlow setup

## Installation and Setup

### 1. Clone the repository

```bash
git clone https://github.com/Navya-shree27/DigitalTwin_Powered_AI_for_Real-time_UrbanPlanning_and_Traffic_Management.git
cd DigitalTwin_Powered_AI_for_Real-time_UrbanPlanning_and_Traffic_Management
```

### 2. Create and activate a Python virtual environment

**macOS / Linux**
```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
```

**Windows PowerShell**
```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### 3. Install Python dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example configuration file:

**macOS / Linux**
```bash
cp .env.example .env
```

**Windows PowerShell**
```powershell
Copy-Item .env.example .env
```

Review the values in `.env` before running the application.

Common settings include:

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | Agent LLM provider setting |
| `OLLAMA_HOST` | Local Ollama server URL, when using Ollama |
| `OLLAMA_MODEL` | Locally available model name |
| `DATABASE_URL` | Database connection; SQLite is the default |
| `CITY_PLACE_NAME` | Target area used for OpenStreetMap data |
| `SIMULATION_ENGINE` | Simulation mode, such as `synthetic` |
| `SIMULATION_DURATION` | Configured simulation duration in seconds |
| `SIMULATION_SEED` | Seed for repeatable simulation runs |
| `CORS_ORIGINS` | Frontend origins allowed by the API |
| `LOG_LEVEL` | Backend logging level |

Do not commit API keys, secrets, or a personal `.env` file to the repository.

## Run the Application

Open separate terminal windows for the backend and frontend.

### 1. Start the FastAPI backend

From the repository root, with the virtual environment activated:

```bash
python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

Useful URLs:

- API root: http://localhost:8000/
- Health check: http://localhost:8000/health
- Interactive Swagger documentation: http://localhost:8000/docs
- ReDoc documentation: http://localhost:8000/redoc

The backend initializes its configured database during startup. The default example configuration uses SQLite.

### 2. Start the React frontend

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, typically http://localhost:5173.

If the frontend cannot reach the API, verify that the backend is running and that `CORS_ORIGINS` in `.env` includes the frontend origin.

## API Overview

The interactive Swagger UI at [http://localhost:8000/docs](http://localhost:8000/docs) is the recommended way to inspect request parameters and response schemas.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Check backend health |
| GET | `/` | API welcome/status response |
| POST | `/api/scenarios` | Create a scenario and obtain road-network data |
| GET | `/api/scenarios` | List scenarios |
| GET | `/api/scenarios/{id}` | Retrieve scenario details |
| POST | `/api/scenarios/{id}/simulate` | Run a baseline simulation |
| GET | `/api/scenarios/{id}/runs` | List simulation runs |
| GET | `/api/scenarios/{id}/metrics` | Retrieve baseline KPIs |
| GET | `/api/scenarios/{id}/issues` | Retrieve detected issues |
| GET | `/api/scenarios/{id}/proposals` | Retrieve intervention proposals |
| GET | `/api/dashboard/{id}` | Retrieve aggregated dashboard data |
| GET | `/api/dashboard/{id}/geojson/network` | Road-network GeoJSON |
| GET | `/api/dashboard/{id}/geojson/nodes` | Intersection-point GeoJSON |
| GET | `/api/proposals/{id}` | Retrieve a proposal and validation result |
| POST | `/api/proposals/{id}/validate` | Re-simulate and validate a proposal |

Refer to [docs/api_reference.md](docs/api_reference.md) for the maintained endpoint reference. Use the schemas exposed by the running API as the source of truth if routes change.

## Machine Learning Evaluation

The repository includes a recorded evaluation file at `results/model_metrics.json`, along with a confusion matrix and feature-importance image. The recorded evaluation is for a Random Forest classifier on a synthetic simulation dataset, with Low, Moderate, and Severe classes.

### Recorded overall metrics

| Metric | Recorded value |
|---|---:|
| Accuracy | 79.52% |
| Macro precision | 55.21% |
| Weighted precision | 91.94% |
| Macro recall | 66.27% |
| Weighted recall | 79.52% |
| Macro F1-score | 55.73% |
| Weighted F1-score | 83.62% |

### Recorded per-class results

| Class | Precision | Recall | F1-score | Test samples |
|---|---:|---:|---:|---:|
| Low | 98.65% | 79.69% | 88.16% | 74,604 |
| Moderate | 27.23% | 82.54% | 40.95% | 7,092 |
| Severe | 39.73% | 36.57% | 38.08% | 804 |

These numbers are the metrics stored in the repository and should be interpreted as the recorded experiment, not as a guarantee of real-world traffic prediction performance. The evaluation set is imbalanced, and severe congestion recall is an important area for improvement. Macro metrics and per-class performance are therefore useful alongside accuracy.

Available artifacts:

- [Model metrics JSON](results/model_metrics.json)
- [Confusion matrix](results/confusion_matrix.png)
- [Feature importance](results/feature_importance.png)

The results folder contains evaluation artifacts. Reproduce a training/evaluation run only using the training scripts and dataset generator present in your current checkout; generated datasets and model files may need to be created first.

## Machine Learning Workflow

The ML pipeline can generate a synthetic future-congestion dataset, train a Random Forest classifier, evaluate it on a held-out test split, and run sample inference. Dataset generation may need a processed OSM road network; if it is missing, the generator attempts to build one using the configured OpenStreetMap workflow.

Run these commands from the repository root:

```bash
# Generate a synthetic traffic dataset (optional; training can generate it if absent)
python -m ml.dataset_generator --scenarios 30 --timesteps 12 --output data/processed/simulation_traffic_dataset.csv

# Train and save the model and preprocessing artifacts
python -m ml.train_model

# Evaluate the saved model and refresh metrics/plots in results/
python -m ml.evaluate

# Run sample predictions
python -m ml.predict
```

The default training pipeline looks for `data/processed/simulation_traffic_dataset.csv` and writes model artifacts under `models/`. Evaluation requires a trained model and preprocessor. The dataset is simulation-generated, so evaluation metrics measure performance against the generated labels and are not a substitute for validation using real-world traffic observations.

## Testing

From the repository root, activate the virtual environment and run:

```bash
python -m pytest -v
```

To run a particular test module:

```bash
python -m pytest tests/test_api.py -v
python -m pytest tests/test_simulation.py -v
python -m pytest tests/test_agents.py -v
python -m pytest tests/test_intervention_loop.py -v
python -m pytest tests/test_ml.py -v
```

A previous development run reported **40 tests passed**. Re-run the suite on your current checkout to confirm the current status; test counts and results can change as the project evolves.

## Configuration Notes

### Local LLM / AI agents

The repository's example environment configuration supports an Ollama-based setup and documents an Anthropic provider option. For Ollama, install and start Ollama separately, download a model available on your machine, and ensure `OLLAMA_HOST` and `OLLAMA_MODEL` match that installation.

Example values from `.env.example`:

```env
LLM_PROVIDER=ollama
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:3b
```

For a hosted provider, configure the relevant provider and API key using your local `.env`. Keep credentials private. LLM-dependent features may require a reachable provider and a compatible model; deterministic/rule-based behavior depends on the relevant module's implementation and configuration.

### Simulation engine

The example configuration uses `SIMULATION_ENGINE=synthetic`. This is the simplest starting point because it does not require a separate SUMO installation. SUMO/TraCI or CityFlow workflows need their external tools and matching configuration to be installed and set up independently.

### OpenStreetMap data

Scenario creation may request data from external OpenStreetMap services. An internet connection is required when the relevant road network is not already available locally. Network size and data availability depend on the configured location and request.

## Project Documentation

- [Architecture](docs/architecture.md)
- [API Reference](docs/api_reference.md)
- [Scenario data notes](data/scenarios/README.md)
- [Data directory notes](data/README.md)

## Current Development Focus

Potential areas for continued development include:

- Improve classification performance for the underrepresented Severe congestion class.
- Evaluate models using macro F1, per-class recall, confusion matrices, and scenario-level tests.
- Compare interventions using repeatable baseline-versus-proposal simulations.
- Expand realistic scenario coverage and validate simulator assumptions.
- Improve API/UI handling of long-running scenarios and error states.
- Add repeatable setup and evaluation instructions as the pipeline evolves.

## Contributors

- Afifa M Makandar
- Ayush R
- Mohammad Salman R
- Navya Shree A R

**Project Guide:** Dr. Usha G R

## License

No license was identified in the repository metadata inspected for this README update. Unless a license is added to the repository, reuse and redistribution are subject to the applicable copyright rules. Add a `LICENSE` file if you intend to publish this project under an open-source license.
