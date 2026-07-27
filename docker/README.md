# Production Docker Environment

This folder houses multi-stage Dockerfiles and composition definitions for deployment.

## Deployment Setup
- `Dockerfile.backend`: Bundles FastAPI, SUMO binaries, and TraCI.
- `Dockerfile.frontend`: Multi-stage build for the Vite production build.
- `docker-compose.yml`: Orchestrates frontend, backend, database, queue, and AI worker services.
