# Digital Twin Powered AI for Real-Time Urban Planning and Traffic Management

> **Course:** Major Project Phase 1 (BCS685) — Department of CSE, BIET Davanagere  
> **Team:** Afifa M Makandar, Ayush R, Mohammad Salman R, Navya Shree A R  
> **Guide:** Dr. Usha G R

---

## 1. Executive Summary & Architecture

The system builds a real-time **Digital Twin** of a city's road network using OpenStreetMap (OSM) data and runs it through a high-fidelity traffic micro-simulation. It features a **Two-Tier AI Architecture**:

1. **Tier A — Trained Machine Learning Model (`ml/`)**:
   - Supervised Scikit-learn Random Forest model trained on reproducible simulation telemetry across diverse traffic demand profiles (45,000 records).
   - Accurately predicts edge-level congestion severity classes (Low, Moderate, Severe) and computes numerical probability distributions and risk scores.
2. **Tier B — Ollama-Powered Multi-Agent AI Framework (`agents/`)**:
   - Specialized local LLM agents (**Traffic Analysis Agent**, **Safety Assessment Agent**, **Urban Planning Agent**, and **Multi-Agent Orchestrator**) that reason over structured ML predictions, intersection geometries, and spatial building constraints.
   - Proposes targeted interventions (Webster-method signal timing, dynamic lane reconfigurations, and k-shortest path route diversions).
3. **Before/After Digital Twin Validation (`validation/`)**:
   - Automatically re-simulates proposed interventions and computes comparative KPIs (travel time, wait time, speed, emissions proxy, noise level, throughput, and efficiency scores).

```
+-------------------------------------------------------------------------------+
|                           OpenStreetMap Digital Twin                          |
|                       (16,343 Nodes / 45,841 Edges)                           |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+---------------------------------------+---------------------------------------+
|                    Traffic Simulation Engine (BPR / SUMO)                     |
|            (Flow, Speed, Density, Queue Length, Wait Time, Occupancy)         |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+---------------------------------------+---------------------------------------+
|             Layer A: Trained ML Traffic Congestion Model (RF)                 |
|               (Predicts: Congestion Class, Probabilities, Risk)               |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+---------------------------------------+---------------------------------------+
|             Layer B: Ollama Multi-Agent AI Intelligence Layer                 |
|       * Traffic Analysis Agent   * Safety Assessment Agent                    |
|       * Urban Planning Agent     * Multi-Agent Orchestrator                   |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+---------------------------------------+---------------------------------------+
|           Proposals: Signal Timing | Lane Change | Route Diversion            |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+---------------------------------------+---------------------------------------+
|           Digital Twin Re-Simulation & Before/After Validation Engine         |
|               (KPI Deltas, Improvement Score, Validation Report)              |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+---------------------------------------+---------------------------------------+
|           Interactive Dashboard (FastAPI + React + Deck.gl / Maps)            |
+-------------------------------------------------------------------------------+
```

---

## 2. Directory Structure

```
digital-twin-traffic-ai/
├── data/
│   ├── raw/osm/                         # Raw OSM extracts cached locally
│   └── processed/
│       ├── network/                     # GraphML & GeoJSON road networks
│       ├── simulation_traffic_dataset.csv # 45,000-sample reproducible simulation dataset
│       ├── dataset_metadata.json        # Labeled dataset provenance metadata
│       └── reports/                     # Persisted before/after validation reports
│
├── ml/                                  # Machine Learning Subsystem
│   ├── dataset_generator.py             # Reproducible multi-scenario data generator
│   ├── preprocess.py                    # Feature scaling, encoding, leakage-free splitting
│   ├── train_model.py                   # RandomForest training pipeline with hyperparameter tuning
│   ├── evaluate.py                      # Unseen test evaluation, metrics calculation & plotting
│   └── predict.py                       # Real-time batched inference engine
│
├── models/                              # Persisted Trained ML Artifacts
│   ├── traffic_model.joblib             # Trained Random Forest model
│   ├── preprocessor.joblib              # Fitted StandardScaler & OneHotEncoder
│   └── feature_names.json               # Input feature schema definition
│
├── results/                             # Evaluation Artifacts
│   ├── model_metrics.json               # Genuine evaluation metrics (Accuracy, F1, Precision, Recall)
│   ├── confusion_matrix.png             # Test set confusion matrix plot
│   └── feature_importance.png           # Gini feature importances plot
│
├── agents/                              # Multi-Agent AI Framework
│   ├── multi_agent_framework.py         # Base agent class & configurable Ollama client
│   ├── traffic_analysis_agent.py        # Diagnoses congestion & ML probability risk
│   ├── safety_agent.py                  # Evaluates conflict rates & building widening limits
│   ├── planner_agent.py                 # Formulates signal, lane, and diversion interventions
│   ├── orchestrator.py                  # Multi-agent coordinator & executive synthesizer
│   ├── city_inspector_agent/            # Reasoning agent & memory store
│   ├── issue_detection/                 # Algorithmic congestion/safety/lane detectors
│   └── proposal_generator/              # Optimization algorithms (Webster, Yen's K-Paths)
│
├── simulation/
│   ├── osm_to_network.py                # Downloads & enriches OSM road graph
│   ├── simulation_runner.py             # End-to-end simulation runner with ML inference
│   └── traci_interface.py               # TraCI live SUMO interface
│
├── validation/
│   ├── metrics_calculator.py            # Computes standard traffic & environmental KPIs
│   ├── before_after_comparator.py       # Diffs baseline vs proposal-applied simulation runs
│   └── report_generator.py              # Generates structured audit reports
│
├── backend/                             # FastAPI Application & REST APIs
├── frontend/                            # React + Deck.gl + Vite interactive dashboard
└── tests/                               # Comprehensive Pytest test suites
```

---

## 3. Step-by-Step Reproduction Guide

### Prerequisites
- Python 3.10+ (tested on Python 3.13)
- Node.js 18+ & npm
- (Optional) Local Ollama daemon running on `http://localhost:11434` with model `llama3`

### Step 1: Environment Setup
```bash
# Clone the repository and enter directory
cd digital-twin-traffic-ai

# Activate Python virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install required dependencies
pip install -r requirements.txt
```

### Step 2: Generate Traffic Simulation Dataset
```bash
# Generates 45,000 labeled simulation records across 30 demand profiles
python -m ml.dataset_generator --scenarios 30 --output data/processed/simulation_traffic_dataset.csv
```

### Step 3: Train the Machine Learning Model
```bash
# Trains Random Forest classifier with 150 estimators and balanced class weights
python -m ml.train_model --data data/processed/simulation_traffic_dataset.csv
```

### Step 4: Evaluate Model on Unseen Test Data
```bash
# Evaluates model on held-out test partition and exports metrics/plots
python -m ml.evaluate
```

### Step 5: Test Real-Time Model Inference
```bash
# Tests the standalone inference engine on sample traffic inputs
python -m ml.predict
```

### Step 6: Run Full Automated Test Suite
```bash
# Executes all 38 unit & integration tests
pytest -v
```

---

## 4. Starting the Application

### 1. Launch FastAPI Backend
```bash
# Start backend on port 8000
uvicorn backend.app:app --reload --port 8000
```
- Interactive API Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Launch React Dashboard
```bash
cd frontend
npm install
npm run dev
```
- Dashboard Interface: [http://localhost:5173](http://localhost:5173)

---

## 5. Ollama Multi-Agent Configuration

Configure local Ollama settings in `.env`:
```env
LLM_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3
```

> **Note on Fallback**: If Ollama is offline or unreachable, all agents automatically execute structured deterministic reasoning, guaranteeing that data generation, model training, simulation runs, and validation comparisons never fail.
