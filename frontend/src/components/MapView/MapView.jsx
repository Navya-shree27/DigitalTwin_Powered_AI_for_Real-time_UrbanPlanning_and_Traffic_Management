import React, { useEffect, useRef, useState } from 'react'
import './MapView.css'

const DAVANAGERE_CENTER = { lat: 14.4644, lon: 75.9218, zoom: 13 }

/**
 * MapView component — renders the road network map with issue markers.
 *
 * Uses MapLibre GL JS with free OSM tiles (no API key required).
 * Falls back to a styled placeholder if MapLibre is not yet installed.
 */
export default function MapView({ scenarioId, selectedIssue, isReady, selectedNode, onSelectNode, editMode }) {
  const mapContainer = useRef(null)
  const mapRef       = useRef(null)
  const [mapReady, setMapReady]   = useState(false)
  const [mapError, setMapError]   = useState(false)

  // ── Initialize MapLibre GL ────────────────────────────────────────────────
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return

    const init = async () => {
      try {
        const maplibregl = await import('maplibre-gl')
        await import('maplibre-gl/dist/maplibre-gl.css')

        const map = new maplibregl.default.Map({
          container: mapContainer.current,
          style: {
            version: 8,
            sources: {
              'osm-tiles': {
                type: 'raster',
                tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
                tileSize: 256,
                attribution: '© OpenStreetMap contributors',
              },
            },
            layers: [{
              id: 'osm-background',
              type: 'raster',
              source: 'osm-tiles',
              paint: {
                'raster-brightness-min': 0,
                'raster-brightness-max': 0.8,
                'raster-saturation': -0.1,
                'raster-contrast': 0.1,
              },
            }],
            glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
          },
          center: [DAVANAGERE_CENTER.lon, DAVANAGERE_CENTER.lat],
          zoom:   DAVANAGERE_CENTER.zoom,
        })

        map.on('load', () => {
          mapRef.current = map
          setMapReady(true)
        })

      } catch (err) {
        console.warn('MapLibre not available:', err)
        setMapError(true)
      }
    }

    init()

    return () => {
      if (mapRef.current) {
        mapRef.current.remove()
        mapRef.current = null
      }
    }
  }, [])

  // ── Load Network & Nodes GeoJSON ──────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !mapRef.current || !scenarioId || !isReady) return

    const map = mapRef.current

    const loadGeoJson = async () => {
      try {
        const { dashboardApi } = await import('../../services/apiClient.js')
        const networkData = await dashboardApi.getNetworkGeoJson(scenarioId)
        const nodesData = await dashboardApi.getNodesGeoJson(scenarioId)

        // Clean existing sources and layers if they already exist
        if (map.getLayer('nodes-layer')) map.removeLayer('nodes-layer')
        if (map.getLayer('network-layer')) map.removeLayer('network-layer')
        if (map.getSource('nodes-source')) map.removeSource('nodes-source')
        if (map.getSource('network-source')) map.removeSource('network-source')

        map.addSource('network-source', {
          type: 'geojson',
          data: networkData
        })

        map.addLayer({
          id: 'network-layer',
          type: 'line',
          source: 'network-source',
          paint: {
            'line-width': [
              'case',
              ['==', ['get', 'widenable'], false], 1.5,
              3
            ],
            'line-color': [
              'case',
              ['==', ['get', 'widenable'], false], '#ef4444', // Red for building constraint / unwidenable
              '#00d4aa' // Cyan for widenable
            ],
            'line-opacity': 0.8
          }
        })

        map.addSource('nodes-source', {
          type: 'geojson',
          data: nodesData
        })

        map.addLayer({
          id: 'nodes-layer',
          type: 'circle',
          source: 'nodes-source',
          paint: {
            'circle-radius': 8,
            'circle-color': '#3b82f6',
            'circle-stroke-width': 2,
            'circle-stroke-color': '#ffffff'
          }
        })

        // Click handler for nodes-layer
        map.on('click', 'nodes-layer', (e) => {
          if (e.features && e.features.length > 0) {
            const properties = e.features[0].properties
            const geometry = e.features[0].geometry
            if (onSelectNode) {
              onSelectNode({
                osmid: properties.osmid,
                street_count: properties.street_count,
                lat: geometry.coordinates[1],
                lon: geometry.coordinates[0]
              })
            }
          }
        })

        // Change cursor on hover over nodes
        map.on('mouseenter', 'nodes-layer', () => {
          map.getCanvas().style.cursor = 'pointer'
        })
        map.on('mouseleave', 'nodes-layer', () => {
          map.getCanvas().style.cursor = ''
        })

        // Zoom map to fit the network bounds
        if (networkData.features && networkData.features.length > 0) {
          const coordinates = networkData.features.flatMap(f => {
            if (f.geometry && f.geometry.type === 'LineString') return f.geometry.coordinates
            return []
          })
          if (coordinates.length > 0) {
            const lons = coordinates.map(c => c[0])
            const lats = coordinates.map(c => c[1])
            const minLon = Math.min(...lons)
            const maxLon = Math.max(...lons)
            const minLat = Math.min(...lats)
            const maxLat = Math.max(...lats)
            map.fitBounds([minLon, minLat, maxLon, maxLat], { padding: 40, maxZoom: 15 })
          }
        }

      } catch (err) {
        console.error('Failed to load GeoJSON onto MapLibre:', err)
      }
    }

    loadGeoJson()
  }, [mapReady, scenarioId, isReady])

  // ── Highlight selected node ────────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !mapRef.current) return
    const map = mapRef.current
    if (map.getLayer('selected-node-layer')) {
      map.removeLayer('selected-node-layer')
    }
    if (map.getSource('selected-node-source')) {
      map.removeSource('selected-node-source')
    }

    if (!selectedNode) return

    map.addSource('selected-node-source', {
      type: 'geojson',
      data: {
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [selectedNode.lon, selectedNode.lat]
        },
        properties: {}
      }
    })

    map.addLayer({
      id: 'selected-node-layer',
      type: 'circle',
      source: 'selected-node-source',
      paint: {
        'circle-radius': 12,
        'circle-color': '#f97316',
        'circle-stroke-width': 3,
        'circle-stroke-color': '#ffffff',
        'circle-opacity': 0.9
      }
    })
  }, [selectedNode, mapReady])

  // ── Fly to selected issue location ────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !mapRef.current || !selectedIssue) return
    const loc = selectedIssue.location || {}
    const lat = loc.lat
    const lon = loc.lon
    if (lat && lon) {
      mapRef.current.flyTo({ center: [lon, lat], zoom: 15, speed: 1.4, curve: 1 })
    }
  }, [selectedIssue, mapReady])

  // ── Fly to selected node location ─────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !mapRef.current || !selectedNode) return
    const { lat, lon } = selectedNode
    if (lat && lon) {
      mapRef.current.flyTo({ center: [lon, lat], zoom: 16, speed: 1.2 })
    }
  }, [selectedNode, mapReady])

  // ── Fallback UI ───────────────────────────────────────────────────────────
  if (mapError) {
    return (
      <MapFallback
        scenarioId={scenarioId}
        isReady={isReady}
        selectedIssue={selectedIssue}
        selectedNode={selectedNode}
        onSelectNode={onSelectNode}
      />
    )
  }

  return (
    <div className="map-view-root">
      {/* MapLibre container */}
      <div ref={mapContainer} className="map-container" />

      {/* Overlay info */}
      {isReady && (
        <div className="map-overlay-tl">
          <div className="map-chip">🗺 Davanagere Road Network</div>
          {selectedIssue && (
            <div className="map-chip map-chip-issue">
              📍 {selectedIssue.type?.replace(/_/g, ' ')} — {selectedIssue.severity}
            </div>
          )}
          {selectedNode && (
            <div className="map-chip map-chip-node">
              🚦 Sandbox Node: {selectedNode.osmid}
            </div>
          )}
        </div>
      )}

      {/* Loading shimmer */}
      {!mapReady && !mapError && (
        <div className="map-loading-overlay">
          <div className="spinner" style={{ width: 32, height: 32, borderWidth: 3 }} />
          <p>Loading map…</p>
        </div>
      )}
    </div>
  )
}

/**
 * Fallback when MapLibre is unavailable — shows a beautiful SVG canvas
 * with a stylized city grid and issue markers.
 */
function MapFallback({ scenarioId, isReady, selectedIssue, selectedNode, onSelectNode }) {
  return (
    <div className="map-fallback">
      <div className="map-fallback-bg">
        {/* Animated city grid SVG */}
        <svg width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(0,212,170,0.06)" strokeWidth="1"/>
            </pattern>
            <radialGradient id="glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="rgba(0,212,170,0.15)" />
              <stop offset="100%" stopColor="rgba(0,0,0,0)" />
            </radialGradient>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
          <rect width="100%" height="100%" fill="url(#glow)" />

          {/* Stylized road lines */}
          {Array.from({ length: 8 }).map((_, i) => (
            <line
              key={`h${i}`}
              x1="0" y1={`${12 + i * 11}%`}
              x2="100%" y2={`${12 + i * 11}%`}
              stroke="rgba(0,212,170,0.12)" strokeWidth={i % 3 === 0 ? 2 : 1}
            />
          ))}
          {Array.from({ length: 10 }).map((_, i) => (
            <line
              key={`v${i}`}
              x1={`${10 + i * 9}%`} y1="0"
              x2={`${10 + i * 9}%`} y2="100%"
              stroke="rgba(59,130,246,0.10)" strokeWidth={i % 4 === 0 ? 2 : 1}
            />
          ))}

          {/* Fallback Intersections */}
          {isReady && [
            { osmid: 1001, cx: '35%', cy: '45%', street_count: 4, name: 'Main St & Broadway (ID: 1001)', lat: 14.4644, lon: 75.9218 },
            { osmid: 1002, cx: '55%', cy: '65%', street_count: 3, name: 'MG Road & Court Rd (ID: 1002)', lat: 14.4680, lon: 75.9250 },
            { osmid: 1003, cx: '70%', cy: '35%', street_count: 4, name: 'PB Road Junction (ID: 1003)', lat: 14.4600, lon: 75.9180 },
          ].map((n, i) => {
            const isSelected = selectedNode?.osmid === n.osmid
            return (
              <g key={i} style={{ cursor: 'pointer' }} onClick={() => onSelectNode && onSelectNode(n)}>
                <circle cx={n.cx} cy={n.cy} r={isSelected ? "16" : "12"} fill={isSelected ? "#f97316" : "#3b82f6"} fillOpacity="0.25" />
                <circle cx={n.cx} cy={n.cy} r={isSelected ? "8" : "6"}  fill={isSelected ? "#f97316" : "#3b82f6"} stroke="#ffffff" strokeWidth="2" />
                <text x={n.cx} y={`calc(${n.cy} - 16px)`} fill="#ffffff" fontSize="10" textAnchor="middle" fontWeight="bold">
                  {isSelected ? `Selected Node: ${n.osmid}` : `Node: ${n.osmid}`}
                </text>
              </g>
            )
          })}

          {/* Issue markers */}
          {isReady && [
            { cx: '35%', cy: '40%', color: '#ef4444', label: 'Congestion' },
            { cx: '55%', cy: '60%', color: '#f59e0b', label: 'Intersection' },
            { cx: '70%', cy: '35%', color: '#3b82f6', label: 'Lane issue' },
          ].map((m, i) => (
            <g key={i}>
              <circle cx={m.cx} cy={m.cy} r="10" fill={m.color} fillOpacity="0.2" className="pulse-circle" />
              <circle cx={m.cx} cy={m.cy} r="5"  fill={m.color} />
            </g>
          ))}
        </svg>
      </div>

      <div className="map-fallback-center">
        {!isReady ? (
          <>
            <div style={{ fontSize: 48, marginBottom: 12 }}>🏙️</div>
            <h2 style={{ fontWeight: 700, fontSize: 20, marginBottom: 8 }}>
              Digital Twin Map
            </h2>
            <p style={{ color: 'var(--text-muted)', maxWidth: 320, textAlign: 'center' }}>
              {scenarioId
                ? 'Run a simulation to populate the map with real OSM road data.'
                : 'Select or create a scenario to get started.'}
            </p>
          </>
        ) : (
          <>
            <div style={{ fontSize: 36, marginBottom: 8 }}>🗺️</div>
            <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
              Map rendering — Click highlighted junctions to open Sandbox controls
            </p>
            <code style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8, fontFamily: 'var(--font-mono)' }}>
              Interactive Sandbox Active (SVG fallback mode)
            </code>
          </>
        )}
      </div>
    </div>
  )
}
