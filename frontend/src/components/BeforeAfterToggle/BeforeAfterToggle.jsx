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
            { key: 'avg_speed_kph',               label: 'Avg Speed',          unit: 'km/h', higherBetter: true },
            { key: 'avg_travel_time_s',            label: 'Travel Time',         unit: 's',    higherBetter: false },
            { key: 'avg_wait_time_s',              label: 'Wait Time',           unit: 's',    higherBetter: false },
            { key: 'congestion_ratio',             label: 'Congestion',          unit: '%',    higherBetter: false, scale: 100 },
            { key: 'efficiency_score',             label: 'Efficiency',          unit: '/100', higherBetter: true },
            { key: 'weighted_intersection_delay',  label: 'Intersection Delay',  unit: 's',    higherBetter: false, eq: '§1' },
            { key: 'delay_entropy',                label: 'Delay Entropy',       unit: 'H',    higherBetter: true,  eq: '§2' },
            { key: 'total_delay_s',                label: 'Total Delay',         unit: 's',    higherBetter: false },
          ].map(m => {
            const entry = comparison[m.key]
            if (!entry) return null
            const before   = entry.before * (m.scale || 1)
            const after    = entry.after  * (m.scale || 1)
            const delta    = entry.delta  * (m.scale || 1)
            const pct      = entry.delta_pct
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
                eqRef={m.eq}
              />
            )
          })}

          {/* Queue-reduction reward (§3) */}
          {validProp?.validation?.queue_reduction_reward != null && (
            <div className="delta-row" style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 6, marginTop: 2 }}>
              <span className="delta-label" title="equ.md §3 — Queue-Reduction Reward (α_abs=0.4, α_red=0.6)">
                Queue-Reduction r <span style={{ fontSize: 9, opacity: 0.6 }}>§3</span>
              </span>
              <div className="delta-values">
                <span className={`delta-pct ${validProp.validation.queue_reduction_reward >= 0 ? 'positive' : 'negative'}`}>
                  {validProp.validation.queue_reduction_reward >= 0 ? '+' : ''}{validProp.validation.queue_reduction_reward?.toFixed(4)}
                </span>
              </div>
            </div>
          )}

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

          {/* Equation legend */}
          <EquationLegend />
        </div>
      ) : (
        <div className="ba-baseline">
          <BaselineMetric label="Speed"      value={metrics?.avg_speed_kph?.toFixed(1) || '--'}  unit="km/h" />
          <BaselineMetric label="Wait"       value={metrics?.avg_wait_time_s?.toFixed(0) || '--'} unit="sec" />
          <BaselineMetric label="Congestion" value={`${((metrics?.congestion_ratio || 0) * 100).toFixed(1)}`} unit="%" />
          {metrics?.weighted_intersection_delay != null && (
            <BaselineMetric label="Int. Delay" value={metrics.weighted_intersection_delay?.toFixed(3)} unit="s §1" />
          )}
          {metrics?.delay_entropy != null && (
            <BaselineMetric label="Entropy H" value={metrics.delay_entropy?.toFixed(3)} unit="§2" />
          )}
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


function DeltaRow({ label, unit, before, after, delta, deltaPct, improved, eqRef }) {
  const sign = delta >= 0 ? '+' : ''
  return (
    <div className="delta-row">
      <span className="delta-label">
        {label}
        {eqRef && (
          <span
            title={`Computed using equ.md ${eqRef}`}
            style={{ marginLeft: 4, fontSize: 9, opacity: 0.55, cursor: 'help' }}
          >
            {eqRef}
          </span>
        )}
      </span>
      <div className="delta-values">
        <span className="delta-before">{before.toFixed(2)}{unit}</span>
        <span className="delta-arrow">→</span>
        <span className="delta-after">{after.toFixed(2)}{unit}</span>
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

function EquationLegend() {
  const [open, setOpen] = React.useState(false)
  return (
    <div style={{ marginTop: 10, borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 8 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'rgba(255,255,255,0.45)', fontSize: 10, padding: 0,
          display: 'flex', alignItems: 'center', gap: 4,
        }}
      >
        {open ? '▾' : '▸'} Equation sources (equ.md)
      </button>
      {open && (
        <div style={{ marginTop: 6, fontSize: 10, color: 'rgba(255,255,255,0.45)', lineHeight: 1.6 }}>
          <div>§1 — Weighted Intersection Delay: d′_I = Σtd_i / Σ(v_i·n_i)</div>
          <div>§2 — Delay Entropy: H_t = −Σ p_i ln(p_i)</div>
          <div>§3 — Queue-Reduction Reward: r_t = α_abs·(−Q/NQ_norm) + α_red·(ΔQ/NQ_norm)</div>
          <div>§7 — Before/After ΔM: (M_base − M_prop) / M_base × 100</div>
          <div>§9 — Acceptance: delay↓≥5%, queue↑≤5%, throughput↓≤2%</div>
        </div>
      )}
    </div>
  )
}

