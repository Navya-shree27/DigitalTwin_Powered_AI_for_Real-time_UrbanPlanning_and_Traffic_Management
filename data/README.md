Data directory for the Digital Twin Traffic AI system.

Structure:
  raw/osm/         — Raw OpenStreetMap extracts (.osm, .pbf) downloaded by osm_to_network.py
  processed/
    network/       — Processed SUMO/CityFlow-ready network files (network.graphml, network.geojson)
    reports/       — Per-proposal validation reports (JSON)
    agent_memory.json — City Inspector Agent memory store
  scenarios/       — Saved traffic demand scenario configs
  cache/           — OSMnx HTTP cache (speeds up repeated downloads)
