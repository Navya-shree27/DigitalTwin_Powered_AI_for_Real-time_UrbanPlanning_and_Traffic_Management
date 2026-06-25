# Digital Twin Traffic AI — System Architecture

This document describes the high-level system architecture and data flow for the Digital Twin Powered AI for Real-Time Urban Planning and Traffic Management.

## System Overview

The system creates a digital model of an urban road network, runs traffic simulations, detects traffic bottlenecks and safety hazards using rules and AI, and proposes concrete remedies.

```
       +---------------------------------------------+
       |             OpenStreetMap Data              |
       +---------------------+-----------------------+
                             |
                             v
       +---------------------+-----------------------+
       |      Data Ingestion & Network Builder       |
       |       (OSMnx + netconvert/CityFlow)         |
       +---------------------+-----------------------+
                             |
                             v
       +---------------------+-----------------------+
       |             Simulation Engine               |
       |         (SUMO / Synthetic Telemetry)        |
       +---------------------+-----------------------+
                             |
                             v
       +---------------------+-----------------------+
       |             Telemetry Schema                |
       |  (Speed, Flow, Occupancy, Wait Time, etc.)  |
       +-------+-------------+-------------+---------+
               |             |             |
               v             v             v
       +-------+-----+ +-----+-----+ +-----+---------+
       |  Rule-Based | |   AI City | |  Proposal     |
       |  Detectors  | | Inspector | |  Generator    |
       |  (Issues)   | |  (LLM)    | | (Interven.)   |
       +-------+-----+ +-----------+ +-----+---------+
               |                           |
               |                           v
               |               +-----------+---------+
               |               | Re-Simulation &     |
               |               | Validation Engine   |
               |               +-----------+---------+
               |                           | (Before/After)
               v                           v
       +-------+---------------------------+---------+
       |                API Backend                  |
       |             (FastAPI + SQLite)              |
       +---------------------+-----------------------+
                             |
                             v
       +---------------------+-----------------------+
       |             Interactive Dashboard           |
       |           (React + Deck.gl + Charts)        |
       +---------------------------------------------+
```

## Module Directory Structure

- **`data/`**: Stores raw OpenStreetMap extracts, processed road networks, and traffic scenarios.
- **`simulation/`**: Manages importing map data and running simulations (either SUMO TraCI or synthetic telemetry generator).
- **`agents/`**:
  - `city_inspector_agent`: Uses LLMs to generate human-like summaries and reasoning.
  - `issue_detection`: Rule-based scripts analyzing speeds and occupancy to flag hotspots.
  - `proposal_generator`: Optimization algorithms suggesting traffic signal timing, route diversions, or lane changes.
- **`validation/`**: Reruns modified networks/scenarios to produce a before-and-after KPI diff.
- **`backend/`**: Serves simulation, agents, and validation APIs.
- **`frontend/`**: Renders the 2D/3D map dashboard and KPI comparison charts.
