import React, { useState, useMemo } from 'react'

/**
 * SignalPlanModal
 * Displays detailed inspection breakdown for all signals recommended
 * to be removed, added, relocated, or retimed.
 */
export default function SignalPlanModal({
  proposals = [],
  initialFilter = 'all',
  onClose,
  onSelectNode,
  onSimulateIntersection,
  onRelocateSignal,
}) {
  const [activeFilter, setActiveFilter] = useState(initialFilter)
  const [searchQuery, setSearchQuery] = useState('')

  // Categorize proposals
  const removeProposals = useMemo(
    () => proposals.filter((p) => p.type === 'signal_remove'),
    [proposals]
  )
  const addProposals = useMemo(
    () => proposals.filter((p) => p.type === 'signal_add'),
    [proposals]
  )
  const relocateProposals = useMemo(
    () => proposals.filter((p) => p.type === 'signal_relocate'),
    [proposals]
  )
  const timingProposals = useMemo(
    () => proposals.filter((p) => p.type === 'signal_timing'),
    [proposals]
  )

  // Current list based on activeFilter
  const filteredList = useMemo(() => {
    let list = []
    if (activeFilter === 'signal_remove') list = removeProposals
    else if (activeFilter === 'signal_add') list = addProposals
    else if (activeFilter === 'signal_relocate') list = relocateProposals
    else if (activeFilter === 'signal_timing') list = timingProposals
    else list = proposals

    if (!searchQuery.trim()) return list
    const q = searchQuery.toLowerCase()
    return list.filter((p) => {
      const nid = String(p.parameters?.node_id || '')
      const desc = (p.description || '').toLowerCase()
      const rat = (p.ai_rationale || '').toLowerCase()
      return nid.includes(q) || desc.includes(q) || rat.includes(q)
    })
  }, [
    activeFilter,
    proposals,
    removeProposals,
    addProposals,
    relocateProposals,
    timingProposals,
    searchQuery,
  ])

  const getBadgeStyle = (type) => {
    switch (type) {
      case 'signal_remove':
        return {
          bg: 'rgba(239, 68, 68, 0.15)',
          color: '#fca5a5',
          border: '1px solid rgba(239, 68, 68, 0.35)',
          label: '🗑️ Decommission Signal (Convert to Yield/Stop)',
        }
      case 'signal_add':
        return {
          bg: 'rgba(34, 197, 94, 0.15)',
          color: '#86efac',
          border: '1px solid rgba(34, 197, 94, 0.35)',
          label: '➕ Install New Multi-Phase Signal',
        }
      case 'signal_relocate':
        return {
          bg: 'rgba(168, 85, 247, 0.15)',
          color: '#d8b4fe',
          border: '1px solid rgba(168, 85, 247, 0.35)',
          label: '📍 Relocate Stop Line / Approach',
        }
      case 'signal_timing':
      default:
        return {
          bg: 'rgba(56, 189, 248, 0.15)',
          color: '#7dd3fc',
          border: '1px solid rgba(56, 189, 248, 0.35)',
          label: '⏱️ Webster Optimal Retiming',
        }
    }
  }

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
          maxWidth: 820,
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          background: 'rgba(15, 23, 42, 0.95)',
          border: '1px solid rgba(255, 255, 255, 0.15)',
          borderRadius: 16,
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.6)',
          overflow: 'hidden',
        }}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            background: 'rgba(30, 41, 59, 0.5)',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 20 }}>🚦</span>
              <h2
                style={{
                  margin: 0,
                  fontSize: 16,
                  fontWeight: 700,
                  color: '#f8fafc',
                }}
              >
                Traffic Signal Infrastructure & Planning Action Plan
              </h2>
            </div>
            <p
              style={{
                margin: '2px 0 0 28px',
                fontSize: 12,
                color: 'var(--text-muted, #94a3b8)',
              }}
            >
              Detailed breakdown of intersections recommended for signal
              removal, addition, relocation, or phase optimization.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'rgba(255, 255, 255, 0.1)',
              border: 'none',
              borderRadius: 8,
              width: 32,
              height: 32,
              color: '#e2e8f0',
              cursor: 'pointer',
              fontSize: 16,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            ✕
          </button>
        </div>

        {/* Filter Navigation Tabs */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '12px 20px',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            background: 'rgba(15, 23, 42, 0.8)',
            flexWrap: 'wrap',
          }}
        >
          <button
            type="button"
            onClick={() => setActiveFilter('all')}
            style={{
              padding: '6px 14px',
              borderRadius: 20,
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
              background:
                activeFilter === 'all'
                  ? 'rgba(56, 189, 248, 0.2)'
                  : 'transparent',
              border:
                activeFilter === 'all'
                  ? '1px solid #38bdf8'
                  : '1px solid rgba(255, 255, 255, 0.1)',
              color: activeFilter === 'all' ? '#38bdf8' : 'var(--text-muted)',
            }}
          >
            All Action Items ({proposals.length})
          </button>

          {removeProposals.length > 0 && (
            <button
              type="button"
              onClick={() => setActiveFilter('signal_remove')}
              style={{
                padding: '6px 14px',
                borderRadius: 20,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                background:
                  activeFilter === 'signal_remove'
                    ? 'rgba(239, 68, 68, 0.25)'
                    : 'transparent',
                border:
                  activeFilter === 'signal_remove'
                    ? '1px solid #ef4444'
                    : '1px solid rgba(239, 68, 68, 0.2)',
                color:
                  activeFilter === 'signal_remove' ? '#fca5a5' : '#ef4444',
              }}
            >
              🗑️ Remove ({removeProposals.length})
            </button>
          )}

          {addProposals.length > 0 && (
            <button
              type="button"
              onClick={() => setActiveFilter('signal_add')}
              style={{
                padding: '6px 14px',
                borderRadius: 20,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                background:
                  activeFilter === 'signal_add'
                    ? 'rgba(34, 197, 94, 0.25)'
                    : 'transparent',
                border:
                  activeFilter === 'signal_add'
                    ? '1px solid #22c55e'
                    : '1px solid rgba(34, 197, 94, 0.2)',
                color: activeFilter === 'signal_add' ? '#86efac' : '#22c55e',
              }}
            >
              ➕ Add ({addProposals.length})
            </button>
          )}

          {relocateProposals.length > 0 && (
            <button
              type="button"
              onClick={() => setActiveFilter('signal_relocate')}
              style={{
                padding: '6px 14px',
                borderRadius: 20,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                background:
                  activeFilter === 'signal_relocate'
                    ? 'rgba(168, 85, 247, 0.25)'
                    : 'transparent',
                border:
                  activeFilter === 'signal_relocate'
                    ? '1px solid #a855f7'
                    : '1px solid rgba(168, 85, 247, 0.2)',
                color:
                  activeFilter === 'signal_relocate' ? '#d8b4fe' : '#a855f7',
              }}
            >
              📍 Relocate ({relocateProposals.length})
            </button>
          )}

          {timingProposals.length > 0 && (
            <button
              type="button"
              onClick={() => setActiveFilter('signal_timing')}
              style={{
                padding: '6px 14px',
                borderRadius: 20,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                background:
                  activeFilter === 'signal_timing'
                    ? 'rgba(56, 189, 248, 0.25)'
                    : 'transparent',
                border:
                  activeFilter === 'signal_timing'
                    ? '1px solid #38bdf8'
                    : '1px solid rgba(56, 189, 248, 0.2)',
                color:
                  activeFilter === 'signal_timing' ? '#7dd3fc' : '#38bdf8',
              }}
            >
              ⏱️ Retime Phases ({timingProposals.length})
            </button>
          )}

          {/* Quick Search */}
          <div style={{ marginLeft: 'auto', minWidth: 160 }}>
            <input
              type="text"
              placeholder="Search node or rationale…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: '100%',
                padding: '5px 10px',
                fontSize: 11,
                background: 'rgba(0, 0, 0, 0.3)',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                borderRadius: 6,
                color: '#f8fafc',
                outline: 'none',
              }}
            />
          </div>
        </div>

        {/* Content Body / Cards List */}
        <div
          style={{
            padding: 20,
            overflowY: 'auto',
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
          }}
        >
          {filteredList.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                padding: '40px 0',
                color: 'var(--text-muted, #94a3b8)',
              }}
            >
              <div style={{ fontSize: 32, marginBottom: 8 }}>🔍</div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>
                No signal proposals found for this filter.
              </div>
            </div>
          ) : (
            filteredList.map((proposal, idx) => {
              const p = proposal.parameters || {}
              const nodeId = p.node_id || proposal.proposal_id
              const badge = getBadgeStyle(proposal.type)
              const lat = p.lat || p.current_lat || 0
              const lon = p.lon || p.current_lon || 0

              return (
                <div
                  key={proposal.id || idx}
                  style={{
                    background: 'rgba(30, 41, 59, 0.45)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    borderRadius: 12,
                    padding: 16,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 10,
                    transition: 'all 0.15s ease',
                  }}
                >
                  {/* Card Header */}
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      flexWrap: 'wrap',
                      gap: 8,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span
                        style={{
                          fontSize: 14,
                          fontWeight: 700,
                          color: '#f8fafc',
                          background: 'rgba(255, 255, 255, 0.08)',
                          padding: '3px 10px',
                          borderRadius: 6,
                          border: '1px solid rgba(255, 255, 255, 0.15)',
                        }}
                      >
                        Node #{nodeId}
                      </span>
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 600,
                          padding: '3px 10px',
                          borderRadius: 20,
                          background: badge.bg,
                          color: badge.color,
                          border: badge.border,
                        }}
                      >
                        {badge.label}
                      </span>
                    </div>

                    {lat !== 0 && (
                      <span
                        style={{
                          fontSize: 11,
                          color: 'var(--text-muted, #94a3b8)',
                          fontFamily: 'monospace',
                        }}
                      >
                        📍 {lat.toFixed(5)}° N, {lon.toFixed(5)}° E
                      </span>
                    )}
                  </div>

                  {/* Description & AI Rationale */}
                  <div
                    style={{
                      fontSize: 12.5,
                      lineHeight: 1.55,
                      color: '#cbd5e1',
                    }}
                  >
                    <strong>Action: </strong>
                    {proposal.description}
                  </div>

                  {proposal.ai_rationale && (
                    <div
                      style={{
                        background: 'rgba(15, 23, 42, 0.6)',
                        borderLeft: '3px solid #38bdf8',
                        padding: '8px 12px',
                        borderRadius: '0 8px 8px 0',
                        fontSize: 11.5,
                        lineHeight: 1.5,
                        color: '#94a3b8',
                      }}
                    >
                      <strong style={{ color: '#38bdf8' }}>
                        City Planning Rationale:{' '}
                      </strong>
                      {proposal.ai_rationale}
                    </div>
                  )}

                  {/* Actions toolbar */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      marginTop: 4,
                      paddingTop: 10,
                      borderTop: '1px solid rgba(255, 255, 255, 0.06)',
                      flexWrap: 'wrap',
                    }}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        onClose()
                        onSimulateIntersection &&
                          onSimulateIntersection({
                            node_id: nodeId,
                            lat,
                            lon,
                            is_signal: proposal.type === 'signal_remove',
                            street_count: p.street_count || 4,
                          })
                      }}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 5,
                        background: 'rgba(239, 68, 68, 0.15)',
                        border: '1px solid rgba(239, 68, 68, 0.35)',
                        color: '#fca5a5',
                        borderRadius: 6,
                        padding: '5px 12px',
                        fontSize: 11.5,
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                      title="Run progressive vehicle ramp-up stress test to find the exact failing capacity"
                    >
                      ⚡ Failing Point Stress Test
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        onClose()
                        onSelectNode &&
                          onSelectNode({
                            node_id: nodeId,
                            lat,
                            lon,
                            is_signal: proposal.type === 'signal_remove',
                          })
                      }}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 5,
                        background: 'rgba(56, 189, 248, 0.15)',
                        border: '1px solid rgba(56, 189, 248, 0.35)',
                        color: '#7dd3fc',
                        borderRadius: 6,
                        padding: '5px 12px',
                        fontSize: 11.5,
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                      title="Open in Signal Sandbox to tweak green/red timings or yield rules"
                    >
                      🛠️ Configure in Sandbox
                    </button>

                    {proposal.type === 'signal_relocate' && (
                      <button
                        type="button"
                        onClick={() => {
                          onClose()
                          onRelocateSignal &&
                            onRelocateSignal({
                              node_id: nodeId,
                              lat,
                              lon,
                            })
                        }}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 5,
                          background: 'rgba(168, 85, 247, 0.15)',
                          border: '1px solid rgba(168, 85, 247, 0.35)',
                          color: '#d8b4fe',
                          borderRadius: 6,
                          padding: '5px 12px',
                          fontSize: 11.5,
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        📍 Relocate Stop Line
                      </button>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
