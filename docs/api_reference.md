# API Reference

## Scenarios

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/scenarios` | Create scenario + download OSM data |
| GET  | `/api/scenarios` | List all scenarios |
| GET  | `/api/scenarios/{id}` | Get scenario details |
| POST | `/api/scenarios/{id}/simulate` | Run baseline simulation |
| GET  | `/api/scenarios/{id}/runs` | List simulation runs |
| GET  | `/api/scenarios/{id}/metrics` | Get baseline KPIs |
| GET  | `/api/scenarios/{id}/issues` | Get detected issues |
| GET  | `/api/scenarios/{id}/proposals` | Get proposals |

## Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard/{id}` | Full aggregated dashboard payload |
| GET | `/api/dashboard/{id}/geojson/network` | Road network GeoJSON |
| GET | `/api/dashboard/{id}/geojson/nodes` | Intersection points GeoJSON |

## Proposals

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET  | `/api/proposals/{id}` | Get proposal + validation result |
| POST | `/api/proposals/{id}/validate` | Re-simulate and validate |

## System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/docs`   | Interactive Swagger UI |
