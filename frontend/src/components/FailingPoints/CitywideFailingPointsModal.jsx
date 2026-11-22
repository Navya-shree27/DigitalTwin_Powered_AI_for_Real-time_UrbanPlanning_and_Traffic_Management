import React, { useState, useEffect, useMemo } from 'react'
import { scenariosApi } from '../../services/apiClient.js'

/**
 * CitywideFailingPointsModal
 * Analyzes and displays the progressive ramp-up capacity breakdown point (failing point)
 * for all traffic signals and unsignalized crossings across the city network.
 */
export default function CitywideFailingPointsModal({
  scenarioId,
  onClose,
  onSimulateIntersection,
  onSelectNode,
}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState('all') // 'all' | 'signals' | 'unsignalized' | 'critical'
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    let isMounted = true
    setLoading(true)
    setError(null)

    scenariosApi
      .getFailingPoints(scenarioId, 150)
      .then((res) => {
        if (isMounted) {
          setData(res.data || res)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err?.response?.data?.detail || err.message || 'Failed to fetch failing points')
          setLoading(false)
        }
      })

    return () => {
      isMounted = false
    }
  }, [scenarioId])

  const allIntersections = useMemo(() => {
    return data?.most_vulnerable_intersections || []
  }, [data])

  const filteredList = useMemo(() => {
    let list = allIntersections

    if (activeTab === 'signals') {
      list = list.filter((item) => item.is_signal)
    } else if (activeTab === 'unsignalized') {
      list = list.filter((item) => !item.is_signal)
    } else if (activeTab === 'critical') {
      list = list.filter((item) => (item.current_load_pct || 0) >= 70)
    }

    if (!searchQuery.trim()) return list
    const q = searchQuery.toLowerCase().trim()
    return list.filter((item) => {
      const nid = String(item.node_id || '').toLowerCase()
      const des = String(item.designation || '').toLowerCase()
      const fm = String(item.failure_mode || '').toLowerCase()
      return nid.includes(q) || des.includes(q) || fm.includes(q)
    })
  }, [allIntersections, activeTab, searchQuery])

  const signalCount = data?.signals_analyzed ?? allIntersections.filter((i) => i.is_signal).length
  const unsignalCount = data?.unsignalized_analyzed ?? allIntersections.filter((i) => !i.is_signal).length
  const criticalCount = allIntersections.filter((i) => (i.current_load_pct || 0) >= 70).length

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className="glass-card"
        style={{
          width: '100%',
          maxWidth: 960,
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          borderRadius: 16,
          border: '1px solid rgba(255, 255, 255, 0.12)',
          background: 'var(--bg-secondary, #111827)',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '18px 24px',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'rgba(255, 255, 255, 0.02)',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 22 }}>⚡</span>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: 'var(--text-primary, #fff)' }}>
                Citywide Junction Failing Points &amp; Capacity Stress Test
              </h2>
            </div>
            <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--text-muted, #9ca3af)' }}>
              Progressive vehicle ramp-up scan across all signals &amp; unsignalized crossings to determine exact breakdown thresholds.
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted, #9ca3af)',
              fontSize: 22,
              cursor: 'pointer',
              padding: '4px 8px',
              borderRadius: 6,
            }}
          >
            ✕
          </button>
        </div>

        {/* Metrics Banner */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: 12,
            padding: '14px 24px',
            background: 'rgba(255, 255, 255, 0.015)',
            borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
          }}
        >
          <div style={{ background: 'rgba(255, 255, 255, 0.04)', padding: '10px 14px', borderRadius: 8 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Total Analyzed</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#fff' }}>
              {data?.total_analyzed ?? allIntersections.length}
            </div>
          </div>
          <div style={{ background: 'rgba(239, 68, 68, 0.08)', padding: '10px 14px', borderRadius: 8 }}>
            <div style={{ fontSize: 11, color: '#fca5a5' }}>🚦 Signals Analyzed</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#ef4444' }}>
              {signalCount}
            </div>
          </div>
          <div style={{ background: 'rgba(34, 197, 94, 0.08)', padding: '10px 14px', borderRadius: 8 }}>
            <div style={{ fontSize: 11, color: '#86efac' }}>🟢 Unsignalized Crossings</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#22c55e' }}>
              {unsignalCount}
            </div>
          </div>
          <div style={{ background: 'rgba(245, 158, 11, 0.08)', padding: '10px 14px', borderRadius: 8 }}>
            <div style={{ fontSize: 11, color: '#fde68a' }}>🚨 Near Failure (≥70% Saturation)</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#f59e0b' }}>
              {criticalCount}
            </div>
          </div>
        </div>

        {/* Filter Toolbar & Search */}
        <div
          style={{
            padding: '12px 24px',
            display: 'flex',
            flexWrap: 'wrap',
            gap: 12,
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
          }}
        >
          {/* Tabs */}
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              onClick={() => setActiveTab('all')}
              style={{
                padding: '6px 12px',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                background: activeTab === 'all' ? 'var(--accent-primary, #3b82f6)' : 'rgba(255,255,255,0.05)',
                color: activeTab === 'all' ? '#fff' : 'var(--text-muted)',
                border: 'none',
              }}
            >
              All ({allIntersections.length})
            </button>
            <button
              onClick={() => setActiveTab('signals')}
              style={{
                padding: '6px 12px',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                background: activeTab === 'signals' ? '#ef4444' : 'rgba(255,255,255,0.05)',
                color: activeTab === 'signals' ? '#fff' : 'var(--text-muted)',
                border: 'none',
              }}
            >
              🚦 Signals Only ({signalCount})
            </button>
            <button
              onClick={() => setActiveTab('unsignalized')}
              style={{
                padding: '6px 12px',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                background: activeTab === 'unsignalized' ? '#22c55e' : 'rgba(255,255,255,0.05)',
                color: activeTab === 'unsignalized' ? '#fff' : 'var(--text-muted)',
                border: 'none',
              }}
            >
              🟢 Unsignalized ({unsignalCount})
            </button>
            <button
              onClick={() => setActiveTab('critical')}
              style={{
                padding: '6px 12px',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                background: activeTab === 'critical' ? '#f59e0b' : 'rgba(255,255,255,0.05)',
                color: activeTab === 'critical' ? '#fff' : 'var(--text-muted)',
                border: 'none',
              }}
            >
              🚨 Vulnerable (≥70%)
            </button>
          </div>

          {/* Search Box */}
          <div style={{ position: 'relative', minWidth: 260 }}>
            <input
              type="text"
              placeholder="Search Node ID, designation, mode..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: '100%',
                padding: '6px 12px',
                fontSize: 12,
                borderRadius: 6,
                border: '1px solid rgba(255, 255, 255, 0.12)',
                background: 'rgba(255, 255, 255, 0.05)',
                color: '#fff',
                outline: 'none',
              }}
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                style={{
                  position: 'absolute',
                  right: 8,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  fontSize: 12,
                }}
              >
                ✕
              </button>
            )}
          </div>
        </div>

        {/* Content Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 24px' }}>
          {loading && (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-muted)' }}>
              <div className="spinner" style={{ width: 28, height: 28, borderWidth: 3, margin: '0 auto 12px' }} />
              Scanning city network and computing progressive ramp-up breakdown points…
            </div>
          )}

          {error && (
            <div
              style={{
                background: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid rgba(239, 68, 68, 0.35)',
                color: '#fca5a5',
                padding: '12px 16px',
                borderRadius: 8,
                fontSize: 13,
              }}
            >
              ⚠ {error}
            </div>
          )}

          {!loading && !error && filteredList.length === 0 && (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-muted)', fontSize: 13 }}>
              No junctions match the current filter or search criteria.
            </div>
          )}

          {!loading && !error && filteredList.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {filteredList.map((item, idx) => {
                const isSig = item.is_signal
                const load = item.current_load_pct || 0
                const loadColor = load >= 85 ? '#ef4444' : load >= 65 ? '#f59e0b' : '#22c55e'
                const badgeBg = isSig ? 'rgba(239, 68, 68, 0.12)' : 'rgba(34, 197, 94, 0.12)'
                const badgeColor = isSig ? '#fca5a5' : '#86efac'
                const badgeBorder = isSig ? '1px solid rgba(239, 68, 68, 0.25)' : '1px solid rgba(34, 197, 94, 0.25)'

                return (
                  <div
                    key={item.node_id || idx}
                    style={{
                      background: 'rgba(255, 255, 255, 0.03)',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      borderRadius: 10,
                      padding: 14,
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 10,
                    }}
                  >
                    {/* Top Row: Node identification & Breakdown volume */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span
                            style={{
                              fontSize: 11,
                              fontWeight: 700,
                              padding: '2px 8px',
                              borderRadius: 4,
                              background: badgeBg,
                              color: badgeColor,
                              border: badgeBorder,
                            }}
                          >
                            {isSig ? '🚦 Signalized' : '🟢 Unsignalized Priority'}
                          </span>
                          <span style={{ fontSize: 14, fontWeight: 700, color: '#fff' }}>
                            Node {item.node_id}
                          </span>
                          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                            · {item.street_count || 4}-approach ({item.lanes_per_approach || 1} lane/appr)
                          </span>
                        </div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                          {item.designation || 'Urban Road Intersection'}
                        </div>
                      </div>

                      {/* Failing Point Metric */}
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: 10, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                          Failing Point (Capacity Breakdown)
                        </div>
                        <div style={{ fontSize: 18, fontWeight: 800, color: '#fff' }}>
                          {item.failing_point_veh_h?.toLocaleString()} <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)' }}>veh/h</span>
                          <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 6 }}>
                            ({item.failing_point_veh_min} v/min)
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Middle Row: Progress bar & Saturation stats */}
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
                        <span style={{ color: 'var(--text-muted)' }}>
                          Current Saturation: <strong style={{ color: loadColor }}>{load}%</strong>
                        </span>
                        <span style={{ color: 'var(--text-muted)' }}>
                          Reserve Headroom: <strong style={{ color: '#86efac' }}>+{item.reserve_capacity_veh_h} veh/h</strong>
                        </span>
                      </div>
                      <div
                        style={{
                          width: '100%',
                          height: 6,
                          background: 'rgba(255, 255, 255, 0.08)',
                          borderRadius: 3,
                          overflow: 'hidden',
                        }}
                      >
                        <div
                          style={{
                            width: `${Math.min(load, 100)}%`,
                            height: '100%',
                            background: loadColor,
                            borderRadius: 3,
                          }}
                        />
                      </div>
                    </div>

                    {/* Bottom Row: Failure Mode, Recommendation, and Action Buttons */}
                    <div
                      style={{
                        display: 'flex',
                        flexWrap: 'wrap',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        gap: 10,
                        borderTop: '1px solid rgba(255, 255, 255, 0.05)',
                        paddingTop: 8,
                      }}
                    >
                      <div style={{ flex: 1, minWidth: 280, fontSize: 11 }}>
                        <div>
                          <span style={{ color: 'var(--text-muted)' }}>Failure Mode: </span>
                          <strong style={{ color: '#f87171' }}>{item.failure_mode}</strong>
                          <span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>LOS: </span>
                          <strong style={{ color: '#f87171' }}>{item.failure_los || 'F'}</strong>
                        </div>
                        {item.recommendation && (
                          <div style={{ color: 'var(--text-secondary)', marginTop: 2 }}>
                            💡 {item.recommendation}
                          </div>
                        )}
                      </div>

                      <div style={{ display: 'flex', gap: 8 }}>
                        {onSelectNode && (
                          <button
                            type="button"
                            onClick={() => {
                              onSelectNode({
                                id: item.node_id,
                                lat: item.lat,
                                lon: item.lon,
                                properties: {
                                  osmid: item.node_id,
                                  street_count: item.street_count,
                                  designation: item.designation,
                                  highway: isSig ? 'traffic_signals' : undefined,
                                },
                              })
                              onClose()
                            }}
                            style={{
                              background: 'rgba(255, 255, 255, 0.06)',
                              border: '1px solid rgba(255, 255, 255, 0.12)',
                              color: 'var(--text-secondary)',
                              padding: '5px 10px',
                              borderRadius: 6,
                              fontSize: 11,
                              fontWeight: 600,
                              cursor: 'pointer',
                            }}
                          >
                            📍 Locate on Map
                          </button>
                        )}

                        {onSimulateIntersection && (
                          <button
                            type="button"
                            onClick={() => {
                              onSimulateIntersection({
                                id: item.node_id,
                                lat: item.lat,
                                lon: item.lon,
                                street_count: item.street_count,
                                properties: {
                                  osmid: item.node_id,
                                  street_count: item.street_count,
                                  designation: item.designation,
                                  highway: isSig ? 'traffic_signals' : undefined,
                                },
                              })
                              onClose()
                            }}
                            style={{
                              background: 'rgba(239, 68, 68, 0.2)',
                              border: '1px solid #ef4444',
                              color: '#fca5a5',
                              padding: '5px 12px',
                              borderRadius: 6,
                              fontSize: 11,
                              fontWeight: 700,
                              cursor: 'pointer',
                            }}
                          >
                            ⚡ Ramp-Up Stress Test
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
