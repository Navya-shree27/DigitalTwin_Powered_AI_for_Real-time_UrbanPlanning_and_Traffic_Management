import React, { useState } from 'react'
import './BeforeAfterToggle.css'

/**
 * BeforeAfterToggle — lets the user switch between baseline and proposal views.
 * Shows a compact before/after delta comparison for the selected proposal.
 */
export default function BeforeAfterToggle({
  view,
  onToggle,
  metrics,
  proposals,
  validatedProposals,
}) {
  const [selectedPropIdx, setSelectedPropIdx] = useState(0)

  const validProp = validatedProposals?.[selectedPropIdx]
  const comparison = validProp?.validation?.metrics

  return (
    <div className="ba-panel glass-card">
      {/* Toggle */}
      <div className="ba-header">
        <div className="toggle-wrapper">
          <button
            className={`toggle-option ${view === 'before' ? 'active' : ''}`}
            onClick={() => onToggle('before')}
            id="toggle-before"
          >
            Baseline
          </button>
          <button
            className={`toggle-option ${view === 'after' ? 'active' : ''}`}
            onClick={() => onToggle('after')}
            disabled={validatedProposals.length === 0}
            title={validatedProposals.length === 0 ? 'Validate a proposal in the right panel first' : 'View proposal comparison'}
            id="toggle-after"
          >
            With Proposal
          </button>
        </div>

        {validatedProposals.length > 0 && (
          <select
            className="prop-select"
            value={selectedPropIdx}
            onChange={e => setSelectedPropIdx(Number(e.target.value))}
          >
            {validatedProposals.map((vp, i) => (
              <option key={i} value={i}>
                {vp.proposal?.type?.replace(/_/g, ' ')} #{i + 1}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Metrics comparison */}
      {comparison && view === 'after' ? (
        <div className="ba-metrics">
          {[
            { key: 'avg_speed_kph',      label: 'Avg Speed',    unit: 'km/h', higherBetter: true },
            { key: 'avg_travel_time_s',   label: 'Travel Time',  unit: 's',    higherBetter: false },
            { key: 'avg_wait_time_s',     label: 'Wait Time',    unit: 's',    higherBetter: false },
            { key: 'congestion_ratio',    label: 'Congestion',   unit: '%',    higherBetter: false, scale: 100 },
            { key: 'efficiency_score',    label: 'Efficiency',   unit: '/100', higherBetter: true },
          ].map(m => {
            const entry = comparison[m.key]
            if (!entry) return null
            const before  = entry.before * (m.scale || 1)
            const after   = entry.after  * (m.scale || 1)
            const delta   = entry.delta  * (m.scale || 1)
            const pct     = entry.delta_pct
            const improved = entry.improved
            return (
              <DeltaRow
                key={m.key}
                label={m.label}
                unit={m.unit}
                before={before}
                after={after}
                delta={delta}
                deltaPct={pct}
                improved={improved}
              />
            )
          })}

          {/* Verdict badge */}
          {validProp?.validation?.verdict && (
            <div className="ba-verdict">
              <span className={`badge ${
                validProp.validation.verdict === 'APPROVED'
                  ? 'badge-approved'
                  : validProp.validation.verdict === 'APPROVED_WITH_CONDITIONS'
                  ? 'badge-moderate'
                  : 'badge-rejected'
              }`}>
                {validProp.validation.verdict}
              </span>
              <span className="ba-score">
                Score: {validProp.validation.improvement_score}/100
              </span>
            </div>
          )}
        </div>
      ) : (
        <div className="ba-baseline">
          <BaselineMetric label="Speed"      value={metrics?.avg_speed_kph?.toFixed(1) || '--'}  unit="km/h" />
          <BaselineMetric label="Wait"       value={metrics?.avg_wait_time_s?.toFixed(0) || '--'} unit="sec" />
          <BaselineMetric label="Congestion" value={`${((metrics?.congestion_ratio || 0) * 100).toFixed(1)}`} unit="%" />
          {validatedProposals.length === 0 && proposals.length > 0 && (
            <p className="ba-hint">Click <strong>⚡ Validate Proposal</strong> in the right panel to unlock before/after comparison</p>
          )}
          {validatedProposals.length === 0 && proposals.length === 0 && (
            <p className="ba-hint">Run a simulation to generate AI proposals</p>
          )}
        </div>
      )}
    </div>
  )
}

function DeltaRow({ label, unit, before, after, delta, deltaPct, improved }) {
  const sign = delta >= 0 ? '+' : ''
  return (
    <div className="delta-row">
      <span className="delta-label">{label}</span>
      <div className="delta-values">
        <span className="delta-before">{before.toFixed(1)}{unit}</span>
        <span className="delta-arrow">→</span>
        <span className="delta-after">{after.toFixed(1)}{unit}</span>
        <span className={`delta-pct ${improved ? 'positive' : 'negative'}`}>
          {sign}{deltaPct?.toFixed(1)}%
        </span>
      </div>
    </div>
  )
}

function BaselineMetric({ label, value, unit }) {
  return (
    <div className="baseline-metric">
      <span className="baseline-value">{value}</span>
      <span className="baseline-unit">{unit}</span>
      <span className="baseline-label">{label}</span>
    </div>
  )
}
