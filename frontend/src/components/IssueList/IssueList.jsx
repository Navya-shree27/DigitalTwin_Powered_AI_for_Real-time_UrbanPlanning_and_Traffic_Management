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

function IssueItem({ issue, isSelected, onSelect }) {
  const severityClass = {
    severe:   'badge-severe',
    moderate: 'badge-moderate',
    low:      'badge-low',
  }[issue.severity] || 'badge-low'

  const m = issue.metrics || {}

  return (
    <div
      className={`issue-item ${isSelected ? 'selected' : ''}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && onSelect()}
    >
      <div className="flex items-center justify-between gap-2" style={{ marginBottom: 4 }}>
        <span className="issue-item-type">
          {TYPE_ICONS[issue.type] || '📍'} {TYPE_LABELS[issue.type] || issue.type}
          {issue.subtype && <span style={{ opacity: 0.6 }}> · {issue.subtype}</span>}
        </span>
        <span className={`badge ${severityClass}`}>{issue.severity}</span>
      </div>
      <div className="issue-item-desc">{issue.description}</div>

      {/* Metric pills */}
      {(m.occupancy !== undefined || m.conflict_rate !== undefined || m.speed_ratio !== undefined) && (
        <div className="issue-metrics-row">
          {m.speed_ratio !== undefined && (
            <MetricPill label="Speed ratio" value={`${(m.speed_ratio * 100).toFixed(0)}%`} />
          )}
          {m.occupancy !== undefined && (
            <MetricPill label="Occupancy" value={`${(m.occupancy * 100).toFixed(0)}%`} />
          )}
          {m.conflict_rate !== undefined && (
            <MetricPill label="Conflicts/h" value={m.conflict_rate.toFixed(1)} />
          )}
          {m.wait_time_s !== undefined && (
            <MetricPill label="Wait" value={`${m.wait_time_s.toFixed(0)}s`} />
          )}
        </div>
      )}
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
