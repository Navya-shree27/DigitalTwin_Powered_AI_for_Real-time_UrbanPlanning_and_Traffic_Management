import React, { useEffect, useRef, useState } from 'react'
import './MapView.css'

const DAVANAGERE_CENTER = { lat: 14.4644, lon: 75.9218, zoom: 13 }

/**
 * MapView component — renders the road network map with issue markers.
 *
 * Uses MapLibre GL JS with free OSM tiles (no API key required).
 * Falls back to a styled placeholder if MapLibre is not yet installed.
 */
export default function MapView({
  scenarioId,
  selectedIssue,
  isReady,
  selectedNode,
  onSelectNode,
  editMode,
  customTelemetry,
  leftSidebarOpen = true,
  rightSidebarOpen = true
}) {
  const mapContainer = useRef(null)
  const mapRef       = useRef(null)
  const [mapReady, setMapReady]   = useState(false)
  const [mapError, setMapError]   = useState(false)

  const [baselineTelemetry, setBaselineTelemetry] = useState(null)
  const [animating, setAnimating] = useState(false)
  const [speedMultiplier, setSpeedMultiplier] = useState(3)
  const [densityMultiplier, setDensityMultiplier] = useState(1.5)

  const networkGeoJsonRef = useRef(null)
  const particlesRef = useRef([])
  const animationFrameIdRef = useRef(null)
  const lastTimeRef = useRef(performance.now())

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
        networkGeoJsonRef.current = networkData // Save ref for telemetry particle calculations!

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
            'circle-radius': [
              'case',
              ['==', ['get', 'highway'], 'traffic_signals'], 10,
              ['>=', ['get', 'street_count'], 4], 9,
              7
            ],
            'circle-color': [
              'case',
              ['==', ['get', 'highway'], 'traffic_signals'], '#ef4444', // Red for traffic signals
              ['>=', ['get', 'street_count'], 4], '#f59e0b', // Amber for major crossroads
              '#3b82f6' // Blue for other standard nodes
            ],
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

  // ── Fetch Baseline Telemetry ──────────────────────────────────────────────
  useEffect(() => {
    if (!scenarioId || !isReady) {
      setBaselineTelemetry(null)
      return
    }

    let active = true
    const fetchTelemetry = async () => {
      try {
        const { dashboardApi } = await import('../../services/apiClient.js')
        const tel = await dashboardApi.getTelemetry(scenarioId)
        if (active) {
          setBaselineTelemetry(tel)
        }
      } catch (err) {
        console.warn('Failed to load telemetry:', err)
      }
    }
    fetchTelemetry()
    return () => { active = false }
  }, [scenarioId, isReady])
  // ── Linear interpolation along LineString with Left-Hand Driving offset ──────
  const interpolateLineString = (coordinates, progress, offsetDistance = 0.00003) => {
    if (!coordinates || coordinates.length === 0) return null
    if (coordinates.length === 1) return coordinates[0]

    const segments = []
    let totalLength = 0
    for (let i = 0; i < coordinates.length - 1; i++) {
      const p1 = coordinates[i]
      const p2 = coordinates[i + 1]
      const dx = p2[0] - p1[0]
      const dy = p2[1] - p1[1]
      const dist = Math.sqrt(dx * dx + dy * dy)
      segments.push({ p1, p2, dx, dy, dist })
      totalLength += dist
    }

    if (totalLength === 0) return coordinates[0]

    let targetDist = progress * totalLength
    let accumulatedDist = 0

    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i]
      if (accumulatedDist + seg.dist >= targetDist) {
        const segProgress = seg.dist === 0 ? 0 : (targetDist - accumulatedDist) / seg.dist
        
        // Center line point
        const lon = seg.p1[0] + (seg.p2[0] - seg.p1[0]) * segProgress
        const lat = seg.p1[1] + (seg.p2[1] - seg.p1[1]) * segProgress

        // Left-hand drive offset perpendicular to segment direction
        if (seg.dist > 0 && offsetDistance !== 0) {
          const leftX = -seg.dy / seg.dist
          const leftY = seg.dx / seg.dist
          return [
            lon + leftX * offsetDistance,
            lat + leftY * offsetDistance
          ]
        }
        return [lon, lat]
      }
      accumulatedDist += seg.dist
    }

    return coordinates[coordinates.length - 1]
  }

  const activeTelemetry = customTelemetry || baselineTelemetry

  // ── Local Signal State for Close-up Animation ──────────────────────────────
  const [activeGreenEdgeId, setActiveGreenEdgeId] = useState(null)
  const [incomingEdgeIdsList, setIncomingEdgeIdsList] = useState([])

  // ── Particle Simulation and Rendering Effect (Selected Node Focus) ────────
  useEffect(() => {
    if (!mapReady || !mapRef.current) return
    const map = mapRef.current

    const setupLayer = () => {
      if (!map.getSource('traffic-particles')) {
        map.addSource('traffic-particles', {
          type: 'geojson',
          data: {
            type: 'FeatureCollection',
            features: []
          }
        })
      }

      if (!map.getLayer('traffic-particles-layer')) {
        map.addLayer({
          id: 'traffic-particles-layer',
          type: 'circle',
          source: 'traffic-particles',
          paint: {
            'circle-radius': ['get', 'size'],
            'circle-color': ['get', 'color'],
            'circle-stroke-width': 1,
            'circle-stroke-color': '#ffffff',
            'circle-opacity': 0.95
          }
        })
      }
    }

    const removeLayer = () => {
      try {
        if (map.getLayer('traffic-particles-layer')) {
          map.removeLayer('traffic-particles-layer')
        }
        if (map.getSource('traffic-particles')) {
          map.removeSource('traffic-particles')
        }
      } catch (err) {
        // Safe check for style cleanups during hot-reloads
      }
    }

    // CRITICAL STRATEGY: Only simulate traffic when a specific signal node is selected!
    // This stops whole-city canvas crashes and centers the detail on the closeup.
    if (!animating || !activeTelemetry || !networkGeoJsonRef.current || !selectedNode) {
      removeLayer()
      if (animationFrameIdRef.current) {
        cancelAnimationFrame(animationFrameIdRef.current)
        animationFrameIdRef.current = null
      }
      setActiveGreenEdgeId(null)
      setIncomingEdgeIdsList([])
      return
    }

    setupLayer()

    // 1. Identify roads connected directly to the selected signal node
    const selectedId = Number(selectedNode.osmid)
    const connectedFeatures = networkGeoJsonRef.current.features.filter(feature => {
      if (!feature.geometry || feature.geometry.type !== 'LineString') return false
      const u = Number(feature.properties.u)
      const v = Number(feature.properties.v)
      return u === selectedId || v === selectedId
    })

    const incomingEdgeFeatures = connectedFeatures.filter(
      f => Number(f.properties.v) === selectedId
    )
    const incomingEdgeIds = incomingEdgeFeatures.map(
      f => `${f.properties.u}_${f.properties.v}_${f.properties.key}`
    )
    setIncomingEdgeIdsList(incomingEdgeIds)

    // Build lookup for edge telemetries
    const edgeTelemetryMap = new Map()
    if (activeTelemetry.edges) {
      activeTelemetry.edges.forEach(e => {
        edgeTelemetryMap.set(e.edge_id, e)
      })
    }

    // 2. Generate detailed mixed vehicle particles for each connected road
    const newParticles = []
    connectedFeatures.forEach(feature => {
      const edgeId = `${feature.properties.u}_${feature.properties.v}_${feature.properties.key}`
      const edgeTel = edgeTelemetryMap.get(edgeId)

      const isIncoming = Number(feature.properties.v) === selectedId
      const speedKph = edgeTel ? edgeTel.speed_sim : (feature.properties.speed_kph || 40)
      const flow = edgeTel ? edgeTel.flow : 0
      const occupancy = edgeTel ? edgeTel.occupancy : 0
      const lengthM = feature.properties.length || 100

      const densityVal = edgeTel ? edgeTel.density : (flow / Math.max(speedKph, 1))
      
      // Scale particle counts so closeup signal view looks alive
      const baseCount = Math.max(4, Math.round(densityVal * (lengthM / 1000) * densityMultiplier * 4.5))
      const particleCount = Math.min(8, baseCount)

      let progressSpeed = (speedKph * 0.2777) / lengthM
      if (isNaN(progressSpeed) || !isFinite(progressSpeed) || progressSpeed <= 0) {
        progressSpeed = 0.01
      }

      // Base road congestion color code
      let baseColor = '#10b981' // Green
      const speedRatio = speedKph / (feature.properties.speed_kph || 40)
      if (occupancy > 0.8 || speedRatio < 0.35) {
        baseColor = '#ef4444' // Red
      } else if (occupancy > 0.5 || speedRatio < 0.65) {
        baseColor = '#f59e0b' // Orange
      }

      // Distribute particles with dynamic mixed traffic sizes/staggering
      for (let i = 0; i < particleCount; i++) {
        // Vehicle types in Indian mixed traffic:
        // 35% two-wheelers/auto-rickshaws, 45% cars, 20% heavy buses/trucks
        const rand = Math.random()
        let size = 4.5
        let offsetVal = 0.00003 // Left hand drive offset
        let color = baseColor

        if (rand < 0.35) {
          // Two wheeler / auto-rickshaw (filtering traffic, riding more to left)
          size = 3.0
          offsetVal = 0.000045 + (Math.random() - 0.5) * 0.00001
          color = '#38bdf8' // Blue/Cyan tint
        } else if (rand < 0.80) {
          // Passenger car
          size = 4.5
          offsetVal = 0.00003 + (Math.random() - 0.5) * 0.000005
          color = baseColor
        } else {
          // Bus / heavy truck
          size = 6.0
          offsetVal = 0.00002
          color = '#a855f7' // Purple tint for heavy visual distinction
        }

        newParticles.push({
          edgeId,
          isIncoming,
          coordinates: feature.geometry.coordinates,
          progress: Math.random(), // Stagger positions
          speed: progressSpeed,
          baseColor,
          color,
          size,
          offset: offsetVal
        })
      }
    })

    particlesRef.current = newParticles
    lastTimeRef.current = performance.now()

    // 3. Animation loop: update positions & handle signal light phasing
    const animate = (time) => {
      try {
        if (!mapRef.current || !mapRef.current.getStyle()) return

        let dt = (time - lastTimeRef.current) / 1000
        if (isNaN(dt) || dt < 0 || dt > 1) {
          dt = 0
        }
        lastTimeRef.current = time

        // Calculate dynamic signal phase cycle (e.g. 10s green per approach)
        const elapsed = time / 1000
        const phaseDuration = 10
        const activeGreenIndex = Math.floor((elapsed / phaseDuration) % Math.max(1, incomingEdgeIds.length))
        const greenEdgeId = incomingEdgeIds[activeGreenIndex] || null
        
        // Notify React of green approach changes
        setActiveGreenEdgeId(greenEdgeId)

        // Group particles by edge to handle queues (so cars don't overlap on red)
        const particlesByEdge = {}
        particlesRef.current.forEach(p => {
          particlesByEdge[p.edgeId] = particlesByEdge[p.edgeId] || []
          particlesByEdge[p.edgeId].push(p)
        })

        // Sort particles: closest to junction first (progress desc)
        Object.keys(particlesByEdge).forEach(eId => {
          particlesByEdge[eId].sort((a, b) => b.progress - a.progress)
        })

        const pointFeatures = []
        particlesRef.current.forEach(p => {
          const edgeGroup = particlesByEdge[p.edgeId] || []
          const queueIndex = edgeGroup.indexOf(p)

          // Physics: Check signal timing stops for incoming edges
          if (p.isIncoming && p.edgeId !== greenEdgeId) {
            // RED Signal is active for this street
            // Spaced queue positions: stop 1st car at 0.94, 2nd at 0.88, etc.
            const targetStopProgress = 0.94 - queueIndex * 0.06

            if (p.progress < targetStopProgress) {
              // Move towards queue and decelerate smoothly
              const distToStop = targetStopProgress - p.progress
              const speedFactor = distToStop < 0.12 ? distToStop / 0.12 : 1
              p.progress += p.speed * dt * speedMultiplier * speedFactor
              if (p.progress > targetStopProgress) p.progress = targetStopProgress
            } else {
              p.progress = targetStopProgress // Hold stopped
            }
          } else {
            // GREEN Signal / Outgoing edge: normal movement
            p.progress += p.speed * dt * speedMultiplier
            if (p.progress >= 1) {
              p.progress = 0
            }
          }

          const coords = interpolateLineString(p.coordinates, p.progress, p.offset)
          if (coords) {
            // Animate local lights: if p is at front of queue on red, color it red!
            let particleColor = p.color
            if (p.isIncoming && p.progress >= (0.94 - queueIndex * 0.06) - 0.01) {
              particleColor = p.edgeId === greenEdgeId ? '#22c55e' : '#ef4444'
            }

            pointFeatures.push({
              type: 'Feature',
              geometry: {
                type: 'Point',
                coordinates: coords
              },
              properties: {
                color: particleColor,
                size: p.size
              }
            })
          }
        })

        const source = map.getSource('traffic-particles')
        if (source) {
          source.setData({
            type: 'FeatureCollection',
            features: pointFeatures
          })
        }

        animationFrameIdRef.current = requestAnimationFrame(animate)
      } catch (err) {
        console.warn('Map animation tick warning:', err)
      }
    }

    animationFrameIdRef.current = requestAnimationFrame(animate)

    return () => {
      if (animationFrameIdRef.current) {
        cancelAnimationFrame(animationFrameIdRef.current)
      }
      removeLayer()
    }
  }, [animating, activeTelemetry, speedMultiplier, densityMultiplier, mapReady, selectedNode])

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
        'circle-radius': 13,
        'circle-color': '#f97316',
        'circle-stroke-width': 3,
        'circle-stroke-color': '#ffffff',
        'circle-opacity': 0.95
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

  return (
    <div className="map-view-root">
      {mapError ? (
        <MapFallback
          scenarioId={scenarioId}
          isReady={isReady}
          selectedIssue={selectedIssue}
          selectedNode={selectedNode}
          onSelectNode={onSelectNode}
          animating={animating}
          speedMultiplier={speedMultiplier}
          densityMultiplier={densityMultiplier}
        />
      ) : (
        <div ref={mapContainer} className="map-container" />
      )}

      {/* Overlay info */}
      {isReady && (
        <div className={`map-overlay-tl ${leftSidebarOpen ? 'sidebar-open' : ''}`}>
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

      {/* Traffic Control Panel Overlay */}
      {isReady && (
        <div 
          className={`map-overlay-tr ${rightSidebarOpen ? 'sidebar-open' : ''}`}
          onClick={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <div className="traffic-control-panel glass-card">
            <div className="panel-title">
              <span className="icon">🚗</span>
              <h3>Traffic Visualizer</h3>
            </div>
            
            {!selectedNode ? (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', textAlign: 'center', padding: '10px 0', lineHeight: 1.6 }}>
                🔍 Click any intersection node on the map to start local traffic animation.
              </div>
            ) : (
              <>
                <div style={{ fontSize: 11, background: 'rgba(255,255,255,0.06)', borderRadius: 4, padding: '4px 8px', marginBottom: 12, color: 'var(--accent-primary)', fontWeight: 600 }}>
                  🚦 Junction: Node {selectedNode.osmid}
                </div>

                <label className="toggle-container">
                  <input
                    type="checkbox"
                    checked={animating}
                    onChange={(e) => setAnimating(e.target.checked)}
                  />
                  <span className="toggle-label">Animate Selected Signal</span>
                </label>

                {animating && (
                  <div className="panel-controls">
                    <div className="control-group">
                      <div className="control-header">
                        <span>Traffic Density</span>
                        <span>{densityMultiplier.toFixed(1)}x</span>
                      </div>
                      <input
                        type="range"
                        min="0.5"
                        max="3.0"
                        step="0.1"
                        value={densityMultiplier}
                        onChange={(e) => setDensityMultiplier(parseFloat(e.target.value))}
                      />
                    </div>

                    <div className="control-group">
                      <div className="control-header">
                        <span>Speed Factor</span>
                        <span>{speedMultiplier.toFixed(0)}x</span>
                      </div>
                      <input
                        type="range"
                        min="1"
                        max="10"
                        step="1"
                        value={speedMultiplier}
                        onChange={(e) => setSpeedMultiplier(parseFloat(e.target.value))}
                      />
                    </div>

                    {activeGreenEdgeId && (
                      <div style={{ fontSize: 11, color: 'var(--accent-success)', display: 'flex', alignItems: 'center', gap: 6, fontWeight: 500 }}>
                        <span className="spinner" style={{ width: 10, height: 10, borderWidth: 1.5, borderColor: 'var(--accent-success) transparent var(--accent-success) transparent' }} />
                        <span>Green Phase rotating...</span>
                      </div>
                    )}

                    <div className="legend-container">
                      <div className="legend-title">Congestion Index</div>
                      <div className="legend-items">
                        <div className="legend-item">
                          <span className="dot dot-free" />
                          <span>Free-flow (Left-hand Drive)</span>
                        </div>
                        <div className="legend-item">
                          <span className="dot dot-moderate" />
                          <span>Moderate queue</span>
                        </div>
                        <div className="legend-item">
                          <span className="dot dot-heavy" />
                          <span>Gridlock red</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
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
function MapFallback({ scenarioId, isReady, selectedIssue, selectedNode, onSelectNode, animating, speedMultiplier, densityMultiplier }) {
  const [offset, setOffset] = useState(0)

  useEffect(() => {
    if (!animating) return

    let frameId
    const tick = () => {
      setOffset(prev => (prev + 0.15 * speedMultiplier) % 100)
      frameId = requestAnimationFrame(tick)
    }
    frameId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frameId)
  }, [animating, speedMultiplier])

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

          {/* Animated fallback traffic (Only close up selected junction streets) */}
          {animating && selectedNode && (() => {
            const mapping = {
              1001: { hIdx: 3, vIdx: 3, hPct: 35, vPct: 45 },
              1002: { hIdx: 5, vIdx: 5, hPct: 55, vPct: 65 },
              1003: { hIdx: 2, vIdx: 7, hPct: 70, vPct: 35 }
            }[selectedNode.osmid]

            if (!mapping) return null

            const isHorizontalGreen = Math.floor(offset / 15) % 2 === 0
            const carsCount = Math.round(3 * densityMultiplier)

            // Render Horizontal flow
            const hFlow = Array.from({ length: carsCount }).map((_, j) => {
              const y = 12 + mapping.hIdx * 11
              const startX = j * (100 / carsCount)
              let curX = (startX + offset) % 100
              
              // If RED, hold before intersection (mapping.hPct)
              if (!isHorizontalGreen) {
                // Queue positions: stop before mapping.hPct (e.g. from mapping.hPct - 15 to mapping.hPct)
                const targetStopX = mapping.hPct - 4 - j * 4
                // Calculate position with stopping logic
                let tempX = (startX + offset) % 100
                if (tempX < targetStopX) {
                  // normal flow
                } else {
                  tempX = targetStopX
                }
                curX = tempX
              }

              return (
                <circle
                  key={`h-car-${j}`}
                  cx={`${curX}%`}
                  cy={`${y}%`}
                  r={j % 2 === 0 ? 3.5 : 2.5}
                  fill={isHorizontalGreen ? '#10b981' : '#ef4444'}
                  opacity="0.85"
                />
              )
            })

            // Render Vertical flow
            const vFlow = Array.from({ length: carsCount }).map((_, j) => {
              const x = 10 + mapping.vIdx * 9
              const startY = j * (100 / carsCount)
              let curY = (startY + offset) % 100

              // If RED, hold before intersection (mapping.vPct)
              if (isHorizontalGreen) {
                const targetStopY = mapping.vPct - 4 - j * 4
                let tempY = (startY + offset) % 100
                if (tempY < targetStopY) {
                  // normal flow
                } else {
                  tempY = targetStopY
                }
                curY = tempY
              }

              return (
                <circle
                  key={`v-car-${j}`}
                  cx={`${x}%`}
                  cy={`${curY}%`}
                  r={j % 2 === 0 ? 3.5 : 2.5}
                  fill={!isHorizontalGreen ? '#10b981' : '#ef4444'}
                  opacity="0.85"
                />
              )
            })

            return (
              <g key="fallback-flow">
                {hFlow}
                {vFlow}
              </g>
            )
          })()}

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
