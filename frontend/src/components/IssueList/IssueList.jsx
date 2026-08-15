import React, { useState } from 'react'
import './IssueList.css'

const TYPE_LABELS = {
  congestion:           'Congestion',
  intersection_safety:  'Intersection',
  lane_utilization:     'Lane Usage',
}
const TYPE_ICONS = {
  congestion:          '🚗',
  intersection_safety: '⚠️',
  lane_utilization:    '🛣️',
}

export default function IssueList({ issues, selectedIssue, onSelectIssue }) {
  const [filter, setFilter] = useState('all')   // 'all' | 'severe' | 'moderate' | 'low'
  const [typeFilter, setTypeFilter] = useState('all')

  const filtered = issues.filter(i => {
    const sev = filter === 'all' || i.severity === filter
    const typ = typeFilter === 'all' || i.type === typeFilter
    return sev && typ
  })

  const severeCnt   = issues.filter(i => i.severity === 'severe').length
  const moderateCnt = issues.filter(i => i.severity === 'moderate').length
  const lowCnt      = issues.filter(i => i.severity === 'low').length

  return (
    <div className="issue-list-root">
      {/* Severity filter chips */}
      <div className="filter-chips">
        <FilterChip active={filter === 'all'}      onClick={() => setFilter('all')}      label="All" count={issues.length} />
        <FilterChip active={filter === 'severe'}   onClick={() => setFilter('severe')}   label="Severe"   count={severeCnt}   variant="severe" />
        <FilterChip active={filter === 'moderate'} onClick={() => setFilter('moderate')} label="Mod"      count={moderateCnt} variant="moderate" />
        <FilterChip active={filter === 'low'}      onClick={() => setFilter('low')}      label="Low"      count={lowCnt}      variant="low" />
      </div>

      {/* Type filter */}
      <div className="type-filter-row">
        {['all', 'congestion', 'intersection_safety', 'lane_utilization'].map(t => (
          <button
            key={t}
            className={`type-filter-btn ${typeFilter === t ? 'active' : ''}`}
            onClick={() => setTypeFilter(t)}
          >
            {t === 'all' ? 'All types' : TYPE_ICONS[t] + ' ' + (TYPE_LABELS[t] || t)}
          </button>
        ))}
      </div>

      {/* Issue items */}
      <div className="issue-scroll">
        {filtered.length === 0 && (
          <div className="empty-state" style={{ padding: '20px 0' }}>
            <div className="empty-state-desc">No issues match this filter.</div>
          </div>
        )}
        {filtered.map(issue => (
          <IssueItem
            key={issue.issue_id || issue.id}
            issue={issue}
            isSelected={selectedIssue?.issue_id === issue.issue_id}
            onSelect={() => onSelectIssue(issue)}
          />
        ))}
      </div>
    </div>
  )
}

/**
 * Builds a readable location string from the issue location object.
 * Falls back to edge_id if no lat/lon available.
 */
function formatLocation(issue) {
  const loc = issue.location || {}
  if (loc.lat && loc.lon) {
    return `${Number(loc.lat).toFixed(4)}, ${Number(loc.lon).toFixed(4)}`
  }
  if (loc.edge_id) {
    // edge_id format is "{u}_{v}_{k}" — shorten to first+last node
    const parts = loc.edge_id.split('_')
    if (parts.length >= 2) return `Node ${parts[0]} → ${parts[1]}`
    return loc.edge_id
  }
  if (loc.node_id) return `Node #${loc.node_id}`
  return null
}

/**
 * Build a unique, data-driven summary line from the issue's metrics.
 * This replaces the raw long description with a compact insight.
 */
function buildSummary(issue) {
  const m = issue.metrics || {}
  const loc = issue.location || {}

  if (issue.type === 'congestion') {
    const speedKph = m.speed_kph != null ? `${Number(m.speed_kph).toFixed(1)} km/h` : null
    const ffKph    = m.free_flow_kph != null ? `${Number(m.free_flow_kph).toFixed(1)} km/h` : null
    const ratio    = m.speed_ratio != null ? `${(Number(m.speed_ratio) * 100).toFixed(0)}%` : null
    const road     = loc.road_type || m.road_type || null
    if (speedKph && ffKph) {
      return `${speedKph} actual vs ${ffKph} free-flow (${ratio || '?'} efficiency)${road ? ` · ${road}` : ''}`
    }
    if (ratio) return `Speed efficiency: ${ratio}${road ? ` · ${road}` : ''}`
  }

  if (issue.type === 'intersection_safety') {
    const cr  = m.conflict_rate != null ? `${Number(m.conflict_rate).toFixed(1)} conflicts/h` : null
    const wt  = m.avg_wait_time != null ? `${Number(m.avg_wait_time).toFixed(0)}s avg wait` : null
    const sc  = m.street_count  != null ? `${m.street_count}-way junction` : null
    return [cr, wt, sc].filter(Boolean).join(' · ') || issue.description?.slice(0, 90)
  }

  if (issue.type === 'lane_utilization') {
    const util = m.utilization_ratio != null ? `${(Number(m.utilization_ratio)*100).toFixed(0)}% utilization` : null
    const lanes = m.lanes != null ? `${m.lanes} lane${m.lanes > 1 ? 's' : ''}` : null
    return [util, lanes].filter(Boolean).join(' · ') || issue.description?.slice(0, 90)
  }

  // Fallback: first 90 chars of description
  return issue.description?.slice(0, 90) || 'No details available'
}

function IssueItem({ issue, isSelected, onSelect }) {
  const severityClass = {
    severe:   'badge-severe',
    moderate: 'badge-moderate',
    low:      'badge-low',
  }[issue.severity] || 'badge-low'

  const m    = issue.metrics || {}
  const loc  = issue.location || {}
  const locStr = formatLocation(issue)
  const summary = buildSummary(issue)

  // Occupancy bar — only for congestion issues
  const occupancy = m.occupancy != null ? Number(m.occupancy) : null
  const occupancyColor = occupancy > 0.8 ? '#ef4444' : occupancy > 0.65 ? '#f59e0b' : '#10b981'

  return (
    <div
      className={`issue-item ${isSelected ? 'selected' : ''}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && onSelect()}
    >
      {/* Header row: type + severity badge */}
      <div className="flex items-center justify-between gap-2" style={{ marginBottom: 4 }}>
        <span className="issue-item-type">
          {TYPE_ICONS[issue.type] || '📍'} {TYPE_LABELS[issue.type] || issue.type}
          {issue.subtype && <span style={{ opacity: 0.6 }}> · {issue.subtype}</span>}
        </span>
        <span className={`badge ${severityClass}`}>{issue.severity}</span>
      </div>

      {/* Location badge */}
      {locStr && (
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4, fontFamily: 'var(--font-mono)' }}>
          📍 {locStr}
        </div>
      )}

      {/* Smart unique summary */}
      <div className="issue-item-desc" style={{ marginBottom: occupancy != null ? 6 : 0 }}>
        {summary}
      </div>

      {/* Occupancy progress bar for congestion */}
      {occupancy != null && (
        <div style={{ marginBottom: 6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-muted)', marginBottom: 2 }}>
            <span>Road occupancy</span>
            <span style={{ color: occupancyColor, fontWeight: 600 }}>{(occupancy * 100).toFixed(0)}%</span>
          </div>
          <div style={{ height: 4, background: 'rgba(255,255,255,0.08)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{
              width: `${Math.min(occupancy * 100, 100)}%`,
              height: '100%',
              background: occupancyColor,
              borderRadius: 2,
              transition: 'width 0.3s ease'
            }} />
          </div>
        </div>
      )}

      {/* Metric pills */}
      <div className="issue-metrics-row">
        {m.speed_kph !== undefined && (
          <MetricPill label="Speed" value={`${Number(m.speed_kph).toFixed(1)} km/h`} />
        )}
        {m.queue_length !== undefined && m.queue_length > 0 && (
          <MetricPill label="Queue" value={`${Number(m.queue_length).toFixed(0)} veh`} />
        )}
        {m.wait_time_s !== undefined && (
          <MetricPill label="Wait" value={`${Number(m.wait_time_s).toFixed(0)}s`} />
        )}
        {m.conflict_rate !== undefined && (
          <MetricPill label="Conflicts/h" value={Number(m.conflict_rate).toFixed(1)} />
        )}
        {m.avg_wait_time !== undefined && m.conflict_rate === undefined && (
          <MetricPill label="Avg Wait" value={`${Number(m.avg_wait_time).toFixed(0)}s`} />
        )}
      </div>
    </div>
  )
}

function FilterChip({ active, onClick, label, count, variant }) {
  const variantClass = variant ? `filter-chip-${variant}` : ''
  return (
    <button className={`filter-chip ${variantClass} ${active ? 'active' : ''}`} onClick={onClick}>
      {label} <span className="filter-chip-count">{count}</span>
    </button>
  )
}

function MetricPill({ label, value }) {
  return (
    <div className="metric-pill">
      <span className="metric-pill-label">{label}</span>
      <span className="metric-pill-value">{value}</span>
    </div>
  )
}
