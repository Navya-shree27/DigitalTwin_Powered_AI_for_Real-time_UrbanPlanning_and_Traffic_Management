import React, { useEffect, useRef, useState } from 'react'
import { formatElapsed, formatETA } from '../../utils/timeFormat.js'
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
  scenario = null,
  editMode,
  customTelemetry,
  leftSidebarOpen = true,
  rightSidebarOpen = true,
  signalOverrides = {},
  simRunning = false,
  simProgress = null,
  elapsedSeconds = 0
}) {
  const mapContainer = useRef(null)
  const mapRef = useRef(null)
  const [mapReady, setMapReady] = useState(false)
  const [mapError, setMapError] = useState(false)

  const [baselineTelemetry, setBaselineTelemetry] = useState(null)
  const [animating, setAnimating] = useState(false)
  const [speedMultiplier, setSpeedMultiplier] = useState(3)
  const [densityMultiplier, setDensityMultiplier] = useState(1.5)
  const geoJsonCacheRef = useRef({ scenarioId: null, network: null, nodes: null, signals: null })

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
          zoom: DAVANAGERE_CENTER.zoom,
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

  // ── Load Network, Nodes & Signals GeoJSON ──────────────────────────────────
  useEffect(() => {
    if (!mapReady || !mapRef.current || !scenarioId) return

    const map = mapRef.current
    let active = true

    const loadGeoJson = async () => {
      try {
        const { dashboardApi } = await import('../../services/apiClient.js')

        let cache = geoJsonCacheRef.current
        if (cache.scenarioId !== scenarioId) {
          cache = { scenarioId, network: null, nodes: null, signals: null }
          geoJsonCacheRef.current = cache
        }

        // Fetch network, nodes, and signals concurrently if not cached
        if (!cache.network || !cache.nodes || !cache.signals || !(cache.signals.features && cache.signals.features.length > 0)) {
          const [net, nds, sigs] = await Promise.all([
            cache.network || dashboardApi.getNetworkGeoJson(scenarioId).catch(e => ({ type: 'FeatureCollection', features: [] })),
            cache.nodes || dashboardApi.getNodesGeoJson(scenarioId).catch(e => ({ type: 'FeatureCollection', features: [] })),
            (!cache.signals || !(cache.signals.features && cache.signals.features.length > 0))
              ? dashboardApi.getSignalsGeoJson(scenarioId).catch(e => ({ type: 'FeatureCollection', features: [] }))
              : cache.signals
          ])
          if (!active) return
          cache.network = net
          cache.nodes = nds
          cache.signals = sigs
        }

        const networkData = cache.network
        const nodesData = cache.nodes
        const rawSignals = cache.signals

        // Deep/shallow copy features so we don't mutate the cached originals
        const networkCopy = {
          ...networkData,
          features: (networkData.features || []).map(f => ({
            ...f,
            properties: { ...f.properties }
          }))
        }

        const nodesCopy = {
          ...nodesData,
          features: (nodesData.features || []).map(f => ({
            ...f,
            properties: { ...f.properties }
          }))
        }

        // Apply signal overrides on top of backend-provided highway attribute
        if (nodesCopy && nodesCopy.features) {
          nodesCopy.features.forEach(feat => {
            if (feat && feat.properties) {
              const featOsmid = feat.properties.osmid
              if (featOsmid) {
                const override = signalOverrides[featOsmid]
                if (override) {
                  if (override.is_signal !== undefined) {
                    feat.properties.highway = override.is_signal ? 'traffic_signals' : 'priority'
                  }
                  if (override.has_dustbin !== undefined) {
                    feat.properties.has_dustbin = override.has_dustbin
                  }
                }
              }
            }
          })
        }

        // Apply edge overrides
        if (networkCopy && networkCopy.features) {
          networkCopy.features.forEach(feat => {
            if (feat && feat.properties) {
              const u = feat.properties.u
              const v = feat.properties.v
              const overrideU = signalOverrides[u]
              const overrideV = signalOverrides[v]

              if (overrideU && overrideU.lanes !== undefined && overrideU.lanes !== null) {
                feat.properties.lanes = overrideU.lanes
              } else if (overrideV && overrideV.lanes !== undefined && overrideV.lanes !== null) {
                feat.properties.lanes = overrideV.lanes
              }

              if (overrideU && overrideU.has_sidewalk !== undefined && overrideU.has_sidewalk !== null) {
                feat.properties.has_sidewalk = overrideU.has_sidewalk
              } else if (overrideV && overrideV.has_sidewalk !== undefined && overrideV.has_sidewalk !== null) {
                feat.properties.has_sidewalk = overrideV.has_sidewalk
              }
            }
          })
        }

        // Safely set or add network-source
        if (map.getSource('network-source')) {
          map.getSource('network-source').setData(networkCopy)
        } else {
          map.addSource('network-source', {
            type: 'geojson',
            data: networkCopy
          })
        }
        networkGeoJsonRef.current = networkCopy

        // Safely add network-layer
        if (!map.getLayer('network-layer')) {
          map.addLayer({
            id: 'network-layer',
            type: 'line',
            source: 'network-source',
            paint: {
              'line-width': [
                'match',
                ['get', 'lanes'],
                1, 2.0,
                2, 3.5,
                3, 5.0,
                4, 6.5,
                3.0
              ],
              'line-color': [
                'case',
                ['==', ['get', 'widenable'], false], '#ef4444',
                '#00d4aa'
              ],
              'line-opacity': 0.8
            }
          })
        }

        // Add sidewalk / footpath layer
        if (!map.getLayer('sidewalk-layer')) {
          map.addLayer({
            id: 'sidewalk-layer',
            type: 'line',
            source: 'network-source',
            filter: ['==', ['get', 'has_sidewalk'], true],
            paint: {
              'line-color': '#e2e8f0',
              'line-width': 2.0,
              'line-dasharray': [2, 2],
              'line-offset': 6
            }
          })
        }

        // Safely set or add nodes-source
        if (map.getSource('nodes-source')) {
          map.getSource('nodes-source').setData(nodesCopy)
        } else {
          map.addSource('nodes-source', {
            type: 'geojson',
            data: nodesCopy
          })
        }

        // Safely add nodes-layer
        if (!map.getLayer('nodes-layer')) {
          map.addLayer({
            id: 'nodes-layer',
            type: 'circle',
            source: 'nodes-source',
            minzoom: 14.5,
            filter: ['>=', ['get', 'street_count'], 3],
            paint: {
              'circle-radius': ['case', ['>=', ['get', 'street_count'], 4], 3.5, 2.5],
              'circle-color': '#64748b',
              'circle-opacity': 0.45,
              'circle-stroke-width': 0
            }
          })
        }

        // Add dustbins POI symbol layer
        if (!map.getLayer('dustbins-layer')) {
          map.addLayer({
            id: 'dustbins-layer',
            type: 'symbol',
            source: 'nodes-source',
            minzoom: 14.0,
            filter: ['==', ['get', 'has_dustbin'], true],
            layout: {
              'text-field': '🗑️',
              'text-size': 13,
              'text-allow-overlap': true,
              'text-offset': [0, -1.2]
            }
          })
        }

        // ── Traffic Signals Layer ───────────────────────────────────────────
        const signalFeatures = (rawSignals?.features || []).map(feat => {
          if (!feat?.properties?.osmid) return feat
          const override = signalOverrides[feat.properties.osmid]
          if (override) {
            return {
              ...feat,
              properties: {
                ...feat.properties,
                highway: override.is_signal !== undefined
                  ? (override.is_signal ? 'traffic_signals' : 'priority')
                  : feat.properties.highway,
                has_dustbin: override.has_dustbin !== undefined
                  ? override.has_dustbin
                  : feat.properties.has_dustbin,
              }
            }
          }
          return feat
        }).filter(f => f?.properties?.highway === 'traffic_signals')

        const signalsGeoJson = { type: 'FeatureCollection', features: signalFeatures }

        if (map.getSource('signals-source')) {
          map.getSource('signals-source').setData(signalsGeoJson)
        } else {
          map.addSource('signals-source', {
            type: 'geojson',
            data: signalsGeoJson
          })
        }

        // Glow halo (visual affordance) — only add layer once
        if (!map.getLayer('signals-halo-layer')) {
          map.addLayer({
            id: 'signals-halo-layer',
            type: 'circle',
            source: 'signals-source',
            paint: {
              'circle-radius': 20,
              'circle-color': '#ef4444',
              'circle-opacity': 0.25,
              'circle-stroke-width': 0
            }
          })
        }

        // Solid signal dot — only add layer once
        if (!map.getLayer('signals-layer')) {
          map.addLayer({
            id: 'signals-layer',
            type: 'circle',
            source: 'signals-source',
            paint: {
              'circle-radius': 9,
              'circle-color': '#ef4444',
              'circle-stroke-width': 2.5,
              'circle-stroke-color': '#ffffff',
              'circle-opacity': 1.0
            }
          })
        }

        // Ensure signal layers stay rendered on top of network and nodes
        if (map.getLayer('signals-halo-layer')) map.moveLayer('signals-halo-layer')
        if (map.getLayer('signals-layer')) map.moveLayer('signals-layer')

        // ── Auto-center & fit camera to current scenario's coordinates ────────
        if (nodesCopy && nodesCopy.features && nodesCopy.features.length > 0) {
          let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity
          for (const f of nodesCopy.features) {
            const coords = f.geometry?.coordinates
            if (coords && coords.length >= 2) {
              const lon = coords[0]
              const lat = coords[1]
              if (lon < minLon) minLon = lon
              if (lon > maxLon) maxLon = lon
              if (lat < minLat) minLat = lat
              if (lat > maxLat) maxLat = lat
            }
          }
          if (minLon !== Infinity && maxLon !== -Infinity && (maxLon - minLon > 0.0005 || maxLat - minLat > 0.0005)) {
            map.fitBounds(
              [[minLon, minLat], [maxLon, maxLat]],
              { padding: 60, maxZoom: 15.5, duration: 1000 }
            )
          }
        }

        // ── Click handlers ───────────────────────────────────────────────────
        map.off('click', 'signals-layer', map._signalClickHandler)
        map.off('mouseenter', 'signals-layer', map._signalMouseEnterHandler)
        map.off('mouseleave', 'signals-layer', map._signalMouseLeaveHandler)

        map._signalClickHandler = (e) => {
          if (e.features && e.features.length > 0) {
            const p = e.features[0].properties
            const g = e.features[0].geometry
            if (onSelectNode) {
              onSelectNode({
                osmid: p.osmid,
                street_count: p.street_count || 3,
                lat: g.coordinates[1],
                lon: g.coordinates[0],
                name: p.designation || p.name || `Signal · Node ${p.osmid}`,
                highway: 'traffic_signals'
              })
            }
          }
        }
        map._signalMouseEnterHandler = () => { map.getCanvas().style.cursor = 'pointer' }
        map._signalMouseLeaveHandler = () => { map.getCanvas().style.cursor = '' }

        map.on('click', 'signals-layer', map._signalClickHandler)
        map.on('mouseenter', 'signals-layer', map._signalMouseEnterHandler)
        map.on('mouseleave', 'signals-layer', map._signalMouseLeaveHandler)

        // Zoom map to fit signals bounds
        if (signalFeatures && signalFeatures.length > 0) {
          const lons = signalFeatures.map(f => f.geometry.coordinates[0])
          const lats = signalFeatures.map(f => f.geometry.coordinates[1])
          const minLon = Math.min(...lons)
          const maxLon = Math.max(...lons)
          const minLat = Math.min(...lats)
          const maxLat = Math.max(...lats)
          map.fitBounds([minLon, minLat, maxLon, maxLat], { padding: 80, maxZoom: 14.5 })
        } else if (networkData.features && networkData.features.length > 0) {
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
        if (active) {
          console.error('Failed to load GeoJSON onto MapLibre:', err)
        }
      }
    }

    loadGeoJson()
    return () => {
      active = false
    }
  }, [mapReady, scenarioId, isReady, signalOverrides])

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

  const nodeOverride = selectedNode ? signalOverrides?.[selectedNode.osmid] : null
  const isNodeOriginallySignal = selectedNode?.highway === 'traffic_signals'
  const nodeIsSignal = nodeOverride ? (nodeOverride.is_signal !== false) : isNodeOriginallySignal

  // ── Local Signal State for Close-up Animation ──────────────────────────────
  const [activeGreenEdgeId, setActiveGreenEdgeId] = useState(null)
  const [incomingEdgeIdsList, setIncomingEdgeIdsList] = useState([])
  const [phaseCountdown, setPhaseCountdown] = useState(null)   // seconds remaining in current green phase
  const [phaseLabel, setPhaseLabel] = useState('')      // e.g. "N/S Green"

  // ── Indian traffic physics constants ─────────────────────────────────────
  // Based on HCM-India (IRC:106) and Davanagere field study averages
  const PHASE_DURATION_S = 25   // green per approach (realistic for Tier-2 city)
  const QUEUE_GAP_DEG = 0.000038  // ~4.2 m (tighter Indian stop gap)
  const VEHICLE_MIX = [
    // [cumulativeProbability, type, sizeRadius, lhOffset, colorLight, colorDark]
    [0.45, 'two-wheeler', 2.5, 0.000032, '#38bdf8', '#0ea5e9'],   // 45% — two-wheelers weave near lane edge
    [0.60, 'auto', 3.2, 0.000026, '#a78bfa', '#7c3aed'],   // 15% — auto-rickshaws
    [0.85, 'car', 4.5, 0.000020, '#10b981', '#059669'],   // 25% — cars center in lane
    [0.95, 'lcv', 5.0, 0.000014, '#f59e0b', '#d97706'],   // 10% — LCV/minivans
    [1.00, 'bus', 6.5, 0.000009, '#f97316', '#ea580c'],   //  5% — buses run close to centerline
  ]

  // ── Particle Simulation and Rendering Effect (Selected Node Focus) ────────
  useEffect(() => {
    if (!mapReady || !mapRef.current) return
    const map = mapRef.current

    const setupLayer = () => {
      // 1. Add road surface source & layers (casing border first, then fill)
      if (!map.getSource('road-surface-source')) {
        map.addSource('road-surface-source', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] }
        })
      }
      if (!map.getLayer('road-surface-casing-layer')) {
        map.addLayer({
          id: 'road-surface-casing-layer',
          type: 'line',
          source: 'road-surface-source',
          paint: {
            'line-width': 26,
            'line-color': '#374151', // Sleek dark-slate curb boundary casing
            'line-opacity': 0.85,
            'line-blur': 0.5
          },
          layout: {
            'line-cap': 'round',
            'line-join': 'round'
          }
        })
      }
      if (!map.getLayer('road-surface-fill-layer')) {
        map.addLayer({
          id: 'road-surface-fill-layer',
          type: 'line',
          source: 'road-surface-source',
          paint: {
            'line-width': 22,
            'line-color': '#1f2937', // Dark asphalt road surface
            'line-opacity': 0.95
          },
          layout: {
            'line-cap': 'round',
            'line-join': 'round'
          }
        })
      }

      // 2. Add particles source & layer (drawn on top)
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
        if (map.getLayer('traffic-particles-layer')) map.removeLayer('traffic-particles-layer')
        if (map.getLayer('road-surface-fill-layer')) map.removeLayer('road-surface-fill-layer')
        if (map.getLayer('road-surface-casing-layer')) map.removeLayer('road-surface-casing-layer')
        if (map.getSource('traffic-particles')) map.removeSource('traffic-particles')
        if (map.getSource('road-surface-source')) map.removeSource('road-surface-source')
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

    // 1. Identify roads connected to the selected signal node
    // Both OSM traffic_signals and major junction nodes have real integer osmids
    // that directly match the u/v fields in the network GeoJSON edges.
    const selectedId = Number(selectedNode.osmid)
    if (isNaN(selectedId)) {
      // Safety guard: if somehow a non-numeric id slips through, bail out cleanly
      console.warn('MapView: selectedNode.osmid is not a valid number — aborting simulation')
      removeLayer()
      return
    }

    let connectedFeatures = networkGeoJsonRef.current.features.filter(feature => {
      if (!feature.geometry || feature.geometry.type !== 'LineString') return false
      const u = Number(feature.properties.u)
      const v = Number(feature.properties.v)
      return u === selectedId || v === selectedId
    })

    // Spatial nearest lookup fallback if selectedId didn't match u/v directly
    if (connectedFeatures.length === 0 && selectedNode.lat && selectedNode.lon) {
      const targetLat = Number(selectedNode.lat)
      const targetLon = Number(selectedNode.lon)
      let bestDist = Infinity
      let bestNodeId = null

      networkGeoJsonRef.current.features.forEach(feat => {
        if (!feat.geometry || feat.geometry.type !== 'LineString' || !feat.geometry.coordinates?.length) return
        const coords = feat.geometry.coordinates
        const startPt = coords[0]
        const endPt = coords[coords.length - 1]
        
        const dStart = Math.hypot(startPt[0] - targetLon, startPt[1] - targetLat)
        const dEnd = Math.hypot(endPt[0] - targetLon, endPt[1] - targetLat)
        
        if (dStart < bestDist) {
          bestDist = dStart
          bestNodeId = Number(feat.properties.u)
        }
        if (dEnd < bestDist) {
          bestDist = dEnd
          bestNodeId = Number(feat.properties.v)
        }
      })

      if (bestNodeId !== null) {
        connectedFeatures = networkGeoJsonRef.current.features.filter(feature => {
          if (!feature.geometry || feature.geometry.type !== 'LineString') return false
          const u = Number(feature.properties.u)
          const v = Number(feature.properties.v)
          return u === bestNodeId || v === bestNodeId
        })
      }
    }

    // Update road surface boundary representation
    const roadSurfaceSource = map.getSource('road-surface-source')
    if (roadSurfaceSource) {
      roadSurfaceSource.setData({
        type: 'FeatureCollection',
        features: connectedFeatures
      })
    }

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

    // 2. Generate Indian mixed-traffic particles for each connected road
    const newParticles = []
    const numApproaches = Number(selectedNode.street_count) || Math.max(2, incomingEdgeIds.length)

    connectedFeatures.forEach(feature => {
      const edgeId = `${feature.properties.u}_${feature.properties.v}_${feature.properties.key}`
      const edgeTel = edgeTelemetryMap.get(edgeId)

      const isIncoming = Number(feature.properties.v) === selectedId
      const freeFlowKph = edgeTel ? edgeTel.speed_sim : (feature.properties.speed_kph || 35)
      const flow = edgeTel ? edgeTel.flow : 300
      const occupancy = edgeTel ? edgeTel.occupancy : 0.3
      const lengthM = feature.properties.length || 120

      // IRC:106 density — vehicles/km (Indian road standard)
      const densityVal = edgeTel ? edgeTel.density : (flow / Math.max(freeFlowKph, 1))

      // Realistic particle count: Davanagere peak ~600 PCU/hr on secondary roads
      const baseCount = Math.max(5, Math.round(densityVal * (lengthM / 1000) * densityMultiplier * 5.5))
      const particleCount = Math.min(12, baseCount)

      // Speed in progress/sec units along the edge
      let progressSpeed = (freeFlowKph * 0.2777) / Math.max(lengthM, 1)
      if (isNaN(progressSpeed) || !isFinite(progressSpeed) || progressSpeed <= 0) progressSpeed = 0.008

      // Congestion colour based on speed ratio (BPR curve)
      const speedRatio = freeFlowKph / (feature.properties.speed_kph || 35)
      let baseColor = speedRatio >= 0.70 ? '#10b981' : speedRatio >= 0.45 ? '#f59e0b' : '#ef4444'

      for (let i = 0; i < particleCount; i++) {
        const rand = Math.random()
        // Find vehicle type from cumulative probability table
        const vt = VEHICLE_MIX.find(v => rand <= v[0]) || VEHICLE_MIX[VEHICLE_MIX.length - 1]
        const [, vType, vSize, vOffset, vColorFree] = vt

        // Two-wheelers weave laterally — add small random lateral jitter
        const lateralJitter = vType === 'two-wheeler' ? (Math.random() - 0.5) * 0.000015 : 0

        newParticles.push({
          edgeId,
          isIncoming,
          coordinates: feature.geometry.coordinates,
          progress: Math.random(),  // stagger starting positions
          speed: progressSpeed,
          baseColor,
          color: vColorFree,
          size: vSize,
          offset: vOffset + lateralJitter,
          vType,
          isLeftTurner: isIncoming && Math.random() < 0.28  // ~28% of vehicles turn left
        })
      }
    })

    particlesRef.current = newParticles
    lastTimeRef.current = performance.now()

    // 3. Animation loop with realistic Indian signal phasing (IRC:106)
    const animate = (time) => {
      try {
        if (!mapRef.current || !mapRef.current.getStyle()) return

        let dt = (time - lastTimeRef.current) / 1000
        if (isNaN(dt) || dt < 0 || dt > 0.5) dt = 0.016  // cap at 0.5s (handles tab-switch pause)
        lastTimeRef.current = time

        // Dynamic sandbox signal timings split calculations
        const nodeOverride = selectedNode ? signalOverrides?.[selectedNode.osmid] : null
        const greenTime = nodeOverride ? Number(nodeOverride.green_s || 25) : 25
        const yellowTime = nodeOverride ? Number(nodeOverride.amber_s || nodeOverride.yellow_s || 4) : 4
        const slotTime = greenTime + yellowTime
        const cycleDuration = numApproaches * slotTime
        const elapsed = time / 1000
        const phasePos = elapsed % cycleDuration

        const activeGreenIndex = Math.floor(phasePos / slotTime) % Math.max(1, incomingEdgeIds.length)
        const greenEdgeId = incomingEdgeIds[activeGreenIndex] || null

        const isYellow = (phasePos % slotTime) >= greenTime
        const secondsRemaining = Math.ceil(
          isYellow ? (slotTime - (phasePos % slotTime)) : (greenTime - (phasePos % slotTime))
        )
        const labels = ['N/S Green', 'E/W Green', 'Left Arrow', 'Aux Phase']

        // Update React state only when values change (avoids 60fps re-renders)
        setActiveGreenEdgeId(prev => prev !== greenEdgeId ? greenEdgeId : prev)
        setPhaseCountdown(prev => prev !== secondsRemaining ? secondsRemaining : prev)
        setPhaseLabel(prev => { const next = labels[activeGreenIndex % labels.length]; return prev !== next ? next : prev })

        // Group & sort particles by edge (closest to junction = highest progress)
        const particlesByEdge = {}
        particlesRef.current.forEach(p => {
          particlesByEdge[p.edgeId] = particlesByEdge[p.edgeId] || []
          particlesByEdge[p.edgeId].push(p)
        })
        Object.keys(particlesByEdge).forEach(eId => {
          particlesByEdge[eId].sort((a, b) => b.progress - a.progress)
        })

        const pointFeatures = []
        particlesRef.current.forEach(p => {
          const edgeGroup = particlesByEdge[p.edgeId] || []
          const queueIndex = edgeGroup.indexOf(p)

          // ── Signal physics ────────────────────────────────────────────────
          const isGreen = !nodeIsSignal || (p.edgeId === greenEdgeId)
          // Left-turners in India may proceed slowly even on red (no oncoming conflict)
          const canCreepon = p.isLeftTurner && !isGreen && p.progress < 0.88

          if (p.isIncoming && !isGreen && !canCreepon) {
            // RED — vehicles queue behind stop line
            // Tighter Indian gap: QUEUE_GAP_DEG per vehicle position
            const stopProgress = 0.96 - queueIndex * (QUEUE_GAP_DEG * 22000)  // normalised to edge length
            const clampedStop = Math.max(0.02, stopProgress)

            if (p.progress < clampedStop) {
              // Deceleration zone: slow smoothly within last 15% of edge
              const distToStop = clampedStop - p.progress
              const brakeFactor = distToStop < 0.15 ? (distToStop / 0.15) ** 0.6 : 1.0
              p.progress += p.speed * dt * speedMultiplier * brakeFactor
              if (p.progress > clampedStop) p.progress = clampedStop
            }
            // else: hold at stop position
          } else if (p.isIncoming && canCreepon) {
            // Left-turner creep on red at ~8 kph relative speed
            const creepSpeed = p.speed * 0.22
            p.progress += creepSpeed * dt * speedMultiplier
            if (p.progress >= 1) p.progress = 0
          } else {
            // GREEN — move at free-flow speed; outgoing edges always flow
            p.progress += p.speed * dt * speedMultiplier
            if (p.progress >= 1) p.progress = 0
          }

          const coords = interpolateLineString(p.coordinates, p.progress, p.offset)
          if (coords) {
            // Colour stopped vehicles at head-of-queue in signal colour
            let particleColor = p.color
            const atStop = p.isIncoming && !isGreen && p.progress >= (0.96 - queueIndex * (QUEUE_GAP_DEG * 22000)) - 0.005
            if (atStop) particleColor = '#ef4444'          // stopped on red
            else if (p.isIncoming && isGreen && p.progress > 0.88) particleColor = '#22c55e'  // clearing on green

            pointFeatures.push({
              type: 'Feature',
              geometry: { type: 'Point', coordinates: coords },
              properties: { color: particleColor, size: p.size }
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
  }, [animating, activeTelemetry, speedMultiplier, densityMultiplier, mapReady, selectedNode, signalOverrides])

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

    // Resolve exact node coordinates from network LineStrings if available
    let nodeLon = Number(selectedNode.lon)
    let nodeLat = Number(selectedNode.lat)
    if (networkGeoJsonRef.current && selectedNode.osmid) {
      const selectedId = Number(selectedNode.osmid)
      const matchingEdge = networkGeoJsonRef.current.features.find(f => {
        if (!f.geometry || f.geometry.type !== 'LineString') return false
        return Number(f.properties.u) === selectedId || Number(f.properties.v) === selectedId
      })
      if (matchingEdge && matchingEdge.geometry.coordinates?.length) {
        const coords = matchingEdge.geometry.coordinates
        if (Number(matchingEdge.properties.u) === selectedId) {
          nodeLon = coords[0][0]
          nodeLat = coords[0][1]
        } else {
          nodeLon = coords[coords.length - 1][0]
          nodeLat = coords[coords.length - 1][1]
        }
      }
    }

    // Color selected node based on its is_signal override
    const nodeColor = nodeIsSignal ? '#ef4444' : '#10b981'  // red = signal, green = priority

    map.addSource('selected-node-source', {
      type: 'geojson',
      data: {
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [nodeLon, nodeLat]
        },
        properties: {}
      }
    })

    map.addLayer({
      id: 'selected-node-layer',
      type: 'circle',
      source: 'selected-node-source',
      paint: {
        'circle-radius': 14,
        'circle-color': nodeColor,
        'circle-stroke-width': 3,
        'circle-stroke-color': '#ffffff',
        'circle-opacity': 0.95
      }
    })
  }, [selectedNode, mapReady, signalOverrides])

  // ── Live override visual feedback — update signal dots for installed/removed signals ─
  useEffect(() => {
    if (!mapReady || !mapRef.current) return
    const map = mapRef.current

    const overrideEntries = Object.entries(signalOverrides || {})

    // Build a set of removed node IDs (is_signal === false) and installed node IDs (is_signal === true)
    const removedIds = new Set(
      overrideEntries.filter(([, v]) => v.is_signal === false).map(([k]) => Number(k))
    )
    const installedIds = new Set(
      overrideEntries.filter(([, v]) => v.is_signal === true).map(([k]) => Number(k))
    )

    // Update the signals-layer opacity if source is loaded
    try {
      if (map.getLayer('signals-halo-layer')) {
        map.setPaintProperty('signals-halo-layer', 'circle-opacity', [
          'case',
          ['in', ['get', 'osmid'], ['literal', [...removedIds]]],
          0.05, // dimmed halo for removed signals
          0.18  // normal opacity
        ])
      }
      if (map.getLayer('signals-layer')) {
        map.setPaintProperty('signals-layer', 'circle-color', [
          'case',
          ['in', ['get', 'osmid'], ['literal', [...removedIds]]],
          '#6b7280', // gray for removed signal
          '#ef4444'  // red for active signal
        ])
        map.setPaintProperty('signals-layer', 'circle-opacity', [
          'case',
          ['in', ['get', 'osmid'], ['literal', [...removedIds]]],
          0.35,
          1.0
        ])
      }
    } catch (err) {
      // Safe for rapid override changes
    }
  }, [signalOverrides, mapReady])

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
          <div className="map-chip">🗺 {scenario?.city || scenario?.name || 'Road Network'}</div>
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
              <span className="icon">🚦</span>
              <h3>Signal Sandbox</h3>
            </div>

            {!selectedNode ? (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', textAlign: 'center', padding: '10px 0', lineHeight: 1.6 }}>
                Click a <span style={{ color: '#ef4444', fontWeight: 700 }}>red signal marker</span> on the map to begin intersection simulation.
              </div>
            ) : (
              <>
                {/* Junction identity card */}
                <div style={{
                  background: nodeIsSignal ? 'rgba(239,68,68,0.10)' : 'rgba(34,197,94,0.10)',
                  border: `1px solid ${nodeIsSignal ? 'rgba(239,68,68,0.25)' : 'rgba(34,197,94,0.25)'}`,
                  borderRadius: 8,
                  padding: '8px 10px',
                  marginBottom: 12
                }}>
                  <div style={{
                    fontSize: 11,
                    color: nodeIsSignal ? '#ef4444' : '#22c55e',
                    fontWeight: 700,
                    marginBottom: 2
                  }}>
                    {nodeIsSignal ? '🚦' : '🟢'} {selectedNode.name || `Junction ${selectedNode.osmid}`}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                    {selectedNode.street_count}-approach {nodeIsSignal ? 'signal · IRC:106 phasing' : 'priority intersection'}
                  </div>
                </div>

                <label className="toggle-container">
                  <input type="checkbox" checked={animating} onChange={(e) => setAnimating(e.target.checked)} />
                  <span className="toggle-label">Run Simulation</span>
                </label>

                {animating && (
                  <div className="panel-controls">
                    {/* Live phase countdown */}
                    {phaseCountdown !== null && nodeIsSignal && (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'rgba(34,197,94,0.12)', border: '1px solid rgba(34,197,94,0.30)', borderRadius: 8, padding: '6px 10px', marginBottom: 10 }}>
                        <div>
                          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2 }}>Current Phase</div>
                          <div style={{ fontSize: 11, color: '#22c55e', fontWeight: 600 }}>{phaseLabel}</div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontSize: 22, fontWeight: 800, color: '#22c55e', fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>{phaseCountdown}s</div>
                          <div style={{ fontSize: 9, color: 'var(--text-muted)' }}>remaining</div>
                        </div>
                      </div>
                    )}

                    <div className="control-group">
                      <div className="control-header">
                        <span>Traffic Density</span>
                        <span>{densityMultiplier.toFixed(1)}x</span>
                      </div>
                      <input type="range" min="0.5" max="3.0" step="0.1" value={densityMultiplier}
                        onChange={(e) => setDensityMultiplier(parseFloat(e.target.value))} />
                    </div>

                    <div className="control-group">
                      <div className="control-header">
                        <span>Simulation Speed</span>
                        <span>{speedMultiplier.toFixed(0)}x</span>
                      </div>
                      <input type="range" min="1" max="10" step="1" value={speedMultiplier}
                        onChange={(e) => setSpeedMultiplier(parseFloat(e.target.value))} />
                    </div>

                    <div className="legend-container">
                      <div className="legend-title">Vehicle Mix (IRC:106)</div>
                      <div className="legend-items">
                        <div className="legend-item"><span className="dot" style={{ background: '#38bdf8' }} /><span>Two-wheelers (45%)</span></div>
                        <div className="legend-item"><span className="dot" style={{ background: '#a78bfa' }} /><span>Auto-rickshaws (15%)</span></div>
                        <div className="legend-item"><span className="dot" style={{ background: '#10b981' }} /><span>Cars (25%)</span></div>
                        <div className="legend-item"><span className="dot" style={{ background: '#f59e0b' }} /><span>LCV (10%)</span></div>
                        <div className="legend-item"><span className="dot" style={{ background: '#f97316' }} /><span>Buses (5%)</span></div>
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

      {/* Live Simulation Sweeper Overlay */}
      {simRunning && (
        <div className="radar-overlay-root">
          <div className="radar-scanner">
            <div className="radar-sweep" />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', pointerEvents: 'none' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, fontSize: 13, color: '#10b981' }}>
              <span className="live-dot" />
              <span>SUMO ENGINE SIMULATING</span>
              <span className="radar-timer-badge">
                ⏱️ {formatElapsed(elapsedSeconds)}
              </span>
              <span className="radar-eta-badge">
                ⏳ {formatETA(simProgress?.eta_s)}
              </span>
            </div>
            <div style={{ fontSize: 11, color: '#94a3b8', display: 'flex', gap: 8, alignItems: 'center' }}>
              <span>{simProgress?.stage_label || 'Executing TraCI loops & vehicle flow simulations...'}</span>
              {simProgress?.step > 0 && (
                <span style={{ color: '#cbd5e1', fontFamily: 'var(--font-mono, monospace)' }}>
                  ({simProgress.step}/{simProgress.total_steps || 300} • {simProgress.progress ? Math.round(simProgress.progress) : 0}%)
                </span>
              )}
            </div>
          </div>
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
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(0,212,170,0.06)" strokeWidth="1" />
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
              1003: { hIdx: 2, vIdx: 7, hPct: 70, vPct: 35 },
              // Map real OSM node IDs to fallback grid positions
              571395243: { hIdx: 3, vIdx: 3, hPct: 35, vPct: 45 },
              571407773: { hIdx: 5, vIdx: 5, hPct: 55, vPct: 65 },
              1470841066: { hIdx: 2, vIdx: 7, hPct: 70, vPct: 35 },
              1465243476: { hIdx: 4, vIdx: 4, hPct: 45, vPct: 55 },
              1822610272: { hIdx: 6, vIdx: 2, hPct: 28, vPct: 75 },
              1782305061: { hIdx: 1, vIdx: 6, hPct: 62, vPct: 23 },
              2702258541: { hIdx: 3, vIdx: 5, hPct: 53, vPct: 45 },
              1782236061: { hIdx: 5, vIdx: 1, hPct: 19, vPct: 65 },
              1464736528: { hIdx: 2, vIdx: 4, hPct: 46, vPct: 34 },
              1782269831: { hIdx: 4, vIdx: 8, hPct: 82, vPct: 56 }
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
            { osmid: 571395243, cx: '37%', cy: '45%', street_count: 4, name: 'Aruna Theatre Junction', lat: 14.4678, lon: 75.9146 },
            { osmid: 571407773, cx: '55%', cy: '67%', street_count: 3, name: 'Vidyarthi Bhavan Junction', lat: 14.4592, lon: 75.9198 },
            { osmid: 1470841066, cx: '73%', cy: '34%', street_count: 3, name: 'Mothi Circle (PB Road)', lat: 14.4643, lon: 75.9176 },
            { osmid: 1465243476, cx: '46%', cy: '56%', street_count: 3, name: 'Gandhi Circle', lat: 14.4654, lon: 75.9227 },
            { osmid: 1822610272, cx: '28%', cy: '78%', street_count: 3, name: 'District Court Junction', lat: 14.4623, lon: 75.9203 },
            { osmid: 1782305061, cx: '64%', cy: '23%', street_count: 3, name: '8th Main / PB Road Signal', lat: 14.4639, lon: 75.9156 },
            { osmid: 2702258541, cx: '55%', cy: '45%', street_count: 3, name: 'KSRTC Bus Stand Junction', lat: 14.4676, lon: 75.9158 },
            { osmid: 1782236061, cx: '19%', cy: '67%', street_count: 3, name: 'Vinobanagar Circle', lat: 14.4556, lon: 75.9149 },
            { osmid: 1464736528, cx: '46%', cy: '34%', street_count: 3, name: 'SBI / Collector Office', lat: 14.4640, lon: 75.9199 },
            { osmid: 1782269831, cx: '82%', cy: '56%', street_count: 3, name: 'Anjaneya Temple Road', lat: 14.4606, lon: 75.9220 }
          ].map((n, i) => {
            const isSelected = selectedNode?.osmid === n.osmid
            return (
              <g key={i} style={{ cursor: 'pointer' }} onClick={() => onSelectNode && onSelectNode(n)}>
                <circle cx={n.cx} cy={n.cy} r={isSelected ? "16" : "12"} fill={isSelected ? "#f97316" : "#3b82f6"} fillOpacity="0.25" />
                <circle cx={n.cx} cy={n.cy} r={isSelected ? "8" : "6"} fill={isSelected ? "#f97316" : "#3b82f6"} stroke="#ffffff" strokeWidth="2" />
                <text x={n.cx} y={n.cy} dy="-16" fill="#ffffff" fontSize="10" textAnchor="middle" fontWeight="bold">
                  {isSelected ? `Selected Node` : n.name.split(' ')[0]}
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
              <circle cx={m.cx} cy={m.cy} r="5" fill={m.color} />
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
