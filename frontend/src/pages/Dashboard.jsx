import React, { useState, useEffect, useCallback } from 'react'
import MapView from '../components/MapView/MapView.jsx'
import MetricsPanel from '../components/MetricsPanel/MetricsPanel.jsx'
import IssueList from '../components/IssueList/IssueList.jsx'
import BeforeAfterToggle from '../components/BeforeAfterToggle/BeforeAfterToggle.jsx'
import { scenariosApi, dashboardApi, proposalsApi } from '../services/apiClient.js'
import './Dashboard.css'

const POLL_INTERVAL = 4000   // ms — poll while simulation is running

export default function Dashboard() {
  const [scenarios, setScenarios]         = useState([])
  const [activeScenarioId, setActiveScenarioId] = useState(null)
  const [dashboardData, setDashboardData] = useState(null)
  const [selectedIssue, setSelectedIssue] = useState(null)
  const [view, setView]                   = useState('before')   // 'before' | 'after'
  const [loading, setLoading]             = useState(false)
  const [simRunning, setSimRunning]       = useState(false)
  const [error, setError]                 = useState(null)
  const [showNewScenario, setShowNewScenario] = useState(false)

  // Panel Toggles
  const [leftSidebarOpen, setLeftSidebarOpen] = useState(true)
  const [rightSidebarOpen, setRightSidebarOpen] = useState(true)

  // Sandbox State
  const [editMode, setEditMode]           = useState(false)
  const [selectedNode, setSelectedNode]   = useState(null)
  const [signalOverrides, setSignalOverrides] = useState({})
  const [customSimResult, setCustomSimResult] = useState(null)
  const [customSimLoading, setCustomSimLoading] = useState(false)

  // ── Load scenarios list ───────────────────────────────────────────────────
  const loadScenarios = useCallback(async () => {
    try {
      const data = await scenariosApi.list()
      setScenarios(data.scenarios || [])
      if (!activeScenarioId && data.scenarios?.length > 0) {
        setActiveScenarioId(data.scenarios[0].id)
      }
    } catch (e) {
      setError('Could not reach backend. Is the API running?')
    }
  }, [activeScenarioId])

  // ── Load dashboard data ───────────────────────────────────────────────────
  const loadDashboard = useCallback(async (scenarioId) => {
    if (!scenarioId) return
    setLoading(true)
    setError(null)
    try {
      const data = await dashboardApi.get(scenarioId)
      setDashboardData(data)
      setSimRunning(data.run?.status === 'running' || data.run?.status === 'pending')
      if (data.run?.status === 'failed') {
        setError('Simulation run failed. Please check the backend console logs.')
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  // ── Initial load ──────────────────────────────────────────────────────────
  useEffect(() => { loadScenarios() }, [])

  useEffect(() => {
    if (activeScenarioId) loadDashboard(activeScenarioId)
  }, [activeScenarioId])

  // ── Poll while simulation is running ─────────────────────────────────────
  useEffect(() => {
    if (!simRunning || !activeScenarioId) return
    const timer = setInterval(() => loadDashboard(activeScenarioId), POLL_INTERVAL)
    return () => clearInterval(timer)
  }, [simRunning, activeScenarioId])

  // ── Create scenario ───────────────────────────────────────────────────────
  const handleCreateScenario = async (payload) => {
    setLoading(true)
    setError(null)
    try {
      const data = await scenariosApi.create(payload)
      const newId = data.scenario.id
      await loadScenarios()
      setActiveScenarioId(newId)
      setShowNewScenario(false)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  // ── Run simulation ────────────────────────────────────────────────────────
  const handleRunSimulation = async () => {
    if (!activeScenarioId) return
    setError(null)
    try {
      await scenariosApi.simulate(activeScenarioId)
      setSimRunning(true)
      setDashboardData(prev => ({
        ...prev,
        run: { ...prev?.run, status: 'running' },
        status: 'running',
      }))
    } catch (e) {
      setError(e.message)
    }
  }

  // ── Run Custom Sandbox Simulation ──────────────────────────────────────────
  const handleRunCustomTest = async () => {
    if (!activeScenarioId) return
    setCustomSimLoading(true)
    setError(null)
    try {
      const overridesList = Object.entries(signalOverrides).map(([id, val]) => ({
        node_id: Number(id),
        green_s: val.green_s,
        amber_s: val.amber_s,
        red_s: val.red_s
      }))
      const result = await scenariosApi.testCustomConfig(activeScenarioId, overridesList)
      setCustomSimResult(result)
    } catch (e) {
      setError(e.message)
    } finally {
      setCustomSimLoading(false)
    }
  }

  // ── UI ────────────────────────────────────────────────────────────────────
  const isReady     = dashboardData?.status === 'ready'
  const hasRun      = !!dashboardData?.run
  const metrics     = dashboardData?.metrics
  const issues      = dashboardData?.top_issues || []
  const proposals   = dashboardData?.top_proposals || []
  const scenario    = dashboardData?.scenario

  return (
    <div className="dashboard-root">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="dashboard-header">
        <div className="header-left">
          <div className="header-logo">
            <div className="logo-icon">🏙️</div>
            <div>
              <h1 className="gradient-text">Digital Twin Traffic AI</h1>
              <p className="header-subtitle">Urban Planning & Traffic Management</p>
            </div>
          </div>
        </div>

        <div className="header-center">
          <select
            className="scenario-select"
            value={activeScenarioId || ''}
            onChange={e => setActiveScenarioId(Number(e.target.value))}
          >
            <option value="" disabled>Select scenario…</option>
            {scenarios.map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          <button
            className="btn btn-ghost"
            onClick={() => setShowNewScenario(true)}
            id="btn-new-scenario"
          >+ New Scenario</button>
        </div>

        <div className="header-right">
          {simRunning && (
            <div className="sim-status">
              <div className="spinner" />
              <span>Simulation running…</span>
            </div>
          )}
          {!simRunning && activeScenarioId && (
            <div className="flex gap-2" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <button
                className={`btn btn-ghost panel-toggle-btn ${leftSidebarOpen ? 'active' : ''}`}
                onClick={() => setLeftSidebarOpen(!leftSidebarOpen)}
                title="Toggle Left Metrics Panel"
                style={{ fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'center', width: 34, height: 34, padding: 0 }}
              >
                📊
              </button>
              <button
                className={`btn btn-ghost panel-toggle-btn ${rightSidebarOpen ? 'active' : ''}`}
                onClick={() => setRightSidebarOpen(!rightSidebarOpen)}
                title="Toggle Right Sandbox Panel"
                style={{ fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'center', width: 34, height: 34, padding: 0 }}
              >
                🛠️
              </button>
              <button
                className="btn btn-primary"
                onClick={handleRunSimulation}
                id="btn-run-simulation"
                disabled={loading}
              >
                {hasRun ? '▶ Re-simulate' : '▶ Run Simulation'}
              </button>
              {hasRun && (
                <button
                  className={`btn ${editMode ? 'btn-primary' : 'btn-ghost'}`}
                  onClick={() => {
                    setEditMode(!editMode)
                    setSelectedNode(null)
                    setCustomSimResult(null)
                  }}
                  id="btn-toggle-edit-mode"
                >
                  {editMode ? '⚙️ Exit Sandbox' : '🛠️ Signal Sandbox'}
                </button>
              )}
            </div>
          )}
          <div className="flex items-center gap-2">
            <div className={`status-dot ${error ? 'offline' : simRunning ? 'pending' : 'online'}`} />
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {error ? 'Error' : simRunning ? 'Running' : 'Ready'}
            </span>
          </div>
        </div>
      </header>

      {/* ── Error banner ───────────────────────────────────────────────── */}
      {error && (
        <div className="error-banner">
          ⚠ {error}
          <button onClick={() => setError(null)} className="error-close">✕</button>
        </div>
      )}

      {/* ── Main layout ────────────────────────────────────────────────── */}
      <div className="dashboard-body">
        {/* Left sidebar */}
        <aside className={`sidebar-left ${leftSidebarOpen ? 'open' : 'collapsed'}`}>
          <div className="sidebar-section">
            <div className="sidebar-section-header">
              <span className="sidebar-section-title">Network Overview</span>
              {scenario && (
                <span className="sidebar-section-badge">
                  {scenario.n_nodes?.toLocaleString()} nodes
                </span>
              )}
            </div>
            <MetricsPanel
              metrics={metrics}
              isLoading={loading && !metrics}
              isReady={isReady}
            />
          </div>

          {isReady && (
            <div className="sidebar-section sidebar-section-grow">
              <div className="sidebar-section-header">
                <span className="sidebar-section-title">Detected Issues</span>
                <span className="sidebar-section-badge">
                  {dashboardData?.issue_summary?.total || 0}
                </span>
              </div>
              <IssueList
                issues={issues}
                selectedIssue={selectedIssue}
                onSelectIssue={setSelectedIssue}
              />
            </div>
          )}

          {!isReady && !simRunning && activeScenarioId && (
            <div className="empty-state">
              <div className="empty-state-icon">🚦</div>
              <div className="empty-state-title">No simulation data yet</div>
              <div className="empty-state-desc">
                Click "Run Simulation" to download map data and generate traffic telemetry.
              </div>
            </div>
          )}

          {simRunning && (
            <div className="sim-progress-card">
              <div className="spinner" style={{ width: 24, height: 24, borderWidth: 3 }} />
              <div>
                <div style={{ fontWeight: 600, fontSize: 14 }}>Simulation in progress</div>
                <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
                  Downloading OSM data, running traffic model, detecting issues…
                </div>
              </div>
            </div>
          )}
        </aside>

        {/* Map — main content */}
        <main className="map-area">
          <MapView
            scenarioId={activeScenarioId}
            selectedIssue={selectedIssue}
            isReady={isReady}
            selectedNode={selectedNode}
            onSelectNode={setSelectedNode}
            editMode={editMode}
            customTelemetry={customSimResult?.telemetry}
            leftSidebarOpen={leftSidebarOpen}
            rightSidebarOpen={rightSidebarOpen}
          />

          {/* Before/after overlay */}
          {isReady && proposals.length > 0 && selectedIssue && !editMode && (
            <div className="ba-overlay">
              <BeforeAfterToggle
                view={view}
                onToggle={setView}
                metrics={metrics}
                proposals={proposals.filter(
                  p => p.issue_id === selectedIssue?.issue_id ||
                       p.run_id === dashboardData?.run?.id
                )}
                validatedProposals={dashboardData?.validated_proposals || []}
                scenarioId={activeScenarioId}
              />
            </div>
          )}
        </main>

        {/* Right sidebar */}
        {isReady && (
          <aside className={`sidebar-right ${rightSidebarOpen ? 'open' : 'collapsed'}`}>
            {!editMode ? (
              <div className="sidebar-section">
                <div className="sidebar-section-header">
                  <span className="sidebar-section-title">AI Proposals</span>
                  <span className="sidebar-section-badge">{proposals.length}</span>
                </div>
                <div className="proposal-list">
                  {proposals.length === 0 && (
                    <div className="empty-state" style={{ padding: 24 }}>
                      <div className="empty-state-desc">No proposals generated yet.</div>
                    </div>
                  )}
                  {proposals.map(p => (
                    <ProposalCard
                      key={p.id}
                      proposal={p}
                      scenarioId={activeScenarioId}
                      onValidated={() => loadDashboard(activeScenarioId)}
                    />
                  ))}
                </div>
              </div>
            ) : (
              <SignalSandboxPanel
                selectedNode={selectedNode}
                overrides={signalOverrides}
                setOverrides={setSignalOverrides}
                onRunCustomTest={handleRunCustomTest}
                customSimLoading={customSimLoading}
                customSimResult={customSimResult}
                onClose={() => {
                  setEditMode(false)
                  setSelectedNode(null)
                  setCustomSimResult(null)
                }}
              />
            )}
          </aside>
        )}
      </div>

      {/* ── New Scenario modal ─────────────────────────────────────────── */}
      {showNewScenario && (
        <NewScenarioModal
          onClose={() => setShowNewScenario(false)}
          onCreate={handleCreateScenario}
          loading={loading}
        />
      )}
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ProposalCard({ proposal, scenarioId, onValidated }) {
  const [validating, setValidating] = useState(false)
  const [result, setResult] = useState(null)

  const typeColors = {
    signal_timing:    'var(--accent-primary)',
    lane_change:      'var(--accent-secondary)',
    route_diversion:  'var(--accent-warning)',
  }
  const typeIcons = {
    signal_timing:   '🚦',
    lane_change:     '🛣️',
    route_diversion: '↩️',
  }

  const handleValidate = async () => {
    setValidating(true)
    try {
      const { proposalsApi: pApi } = await import('../services/apiClient.js')
      await pApi.validate(proposal.id)
      // Poll for result
      setTimeout(async () => {
        const data = await pApi.get(proposal.id)
        setResult(data.validation)
        onValidated()
        setValidating(false)
      }, 3000)
    } catch {
      setValidating(false)
    }
  }

  return (
    <div className="proposal-card glass-card">
      <div className="proposal-card-header">
        <span className="proposal-type-icon">{typeIcons[proposal.type] || '💡'}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="proposal-type-label" style={{ color: typeColors[proposal.type] || 'var(--accent-primary)' }}>
            {proposal.type?.replace(/_/g, ' ')}
          </div>
        </div>
        {proposal.validated && (
          <span className={`badge badge-${result?.verdict === 'APPROVED' ? 'approved' : 'rejected'}`}>
            {result?.verdict || 'Validated'}
          </span>
        )}
      </div>

      <p className="proposal-desc">{proposal.description}</p>

      {result && (
        <div className="proposal-result">
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>IMPROVEMENT SCORE</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: result.verdict === 'APPROVED' ? 'var(--accent-success)' : 'var(--accent-warning)' }}>
            {result.improvement_score}/100
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>{result.summary?.slice(0, 80)}…</div>
        </div>
      )}

      {!proposal.validated && (
        <button
          className="btn btn-ghost"
          style={{ width: '100%', marginTop: 8, justifyContent: 'center' }}
          onClick={handleValidate}
          disabled={validating}
          id={`btn-validate-${proposal.id}`}
        >
          {validating ? <><div className="spinner" style={{width:14,height:14}} /> Validating…</> : '⚡ Validate Proposal'}
        </button>
      )}
    </div>
  )
}

function NewScenarioModal({ onClose, onCreate, loading }) {
  const [name, setName]     = useState('Davanagere Peak Hour')
  const [city, setCity]     = useState('Davanagere, Karnataka, India')
  const [desc, setDesc]     = useState('')
  const [force, setForce]   = useState(false)

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card glass-card" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>New Simulation Scenario</h2>
          <button className="btn btn-ghost" style={{ padding: '4px 8px' }} onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          <div className="form-group">
            <label className="form-label">Scenario Name</label>
            <input
              className="form-input"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Davanagere Peak Hour"
              id="input-scenario-name"
            />
          </div>

          <div className="form-group">
            <label className="form-label">City / Place Name</label>
            <input
              className="form-input"
              value={city}
              onChange={e => setCity(e.target.value)}
              placeholder="e.g. Davanagere, Karnataka, India"
              id="input-scenario-city"
            />
            <small className="form-hint">Used by OpenStreetMap to download the road network.</small>
          </div>

          <div className="form-group">
            <label className="form-label">Description (optional)</label>
            <textarea
              className="form-input"
              value={desc}
              onChange={e => setDesc(e.target.value)}
              rows={2}
              placeholder="Notes about this scenario…"
            />
          </div>

          <label className="form-checkbox">
            <input type="checkbox" checked={force} onChange={e => setForce(e.target.checked)} />
            Force re-download OSM data
          </label>
        </div>

        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button
            className="btn btn-primary"
            onClick={() => onCreate({ name, city, description: desc, forceRebuild: force })}
            disabled={loading || !name || !city}
            id="btn-create-scenario"
          >
            {loading ? <><div className="spinner" style={{width:14,height:14}} /> Creating…</> : '🚀 Create & Download Map'}
          </button>
        </div>
      </div>
    </div>
  )
}

function SignalSandboxPanel({
  selectedNode,
  overrides,
  setOverrides,
  onRunCustomTest,
  customSimLoading,
  customSimResult,
  onClose
}) {
  const nodeId = selectedNode?.osmid
  
  // Local state for the sliders of the currently selected node
  const [green, setGreen] = useState(35)
  const [amber, setAmber] = useState(3)
  const [red, setRed] = useState(35)

  // Synchronize slider state when selected node or overrides change
  useEffect(() => {
    if (!nodeId) return
    const currentOverride = overrides[nodeId] || { green_s: 35, amber_s: 3, red_s: 35 }
    setGreen(currentOverride.green_s)
    setAmber(currentOverride.amber_s)
    setRed(currentOverride.red_s)
  }, [nodeId, overrides])

  const handleSliderChange = (type, val) => {
    if (!nodeId) return
    const updated = {
      green_s: type === 'green' ? val : green,
      amber_s: type === 'amber' ? val : amber,
      red_s: type === 'red' ? val : red,
    }
    if (type === 'green') setGreen(val)
    if (type === 'amber') setAmber(val)
    if (type === 'red') setRed(val)

    setOverrides(prev => ({
      ...prev,
      [nodeId]: updated
    }))
  }

  const handleResetNode = () => {
    if (!nodeId) return
    setGreen(35)
    setAmber(3)
    setRed(35)
    setOverrides(prev => {
      const copy = { ...prev }
      delete copy[nodeId]
      return copy
    })
  }

  return (
    <div className="sandbox-panel-root sidebar-section" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="sidebar-section-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="sidebar-section-title">🚦 Signal Timing Sandbox</span>
        <button className="btn btn-ghost" style={{ padding: '2px 6px', fontSize: 12 }} onClick={onClose}>✕ Exit</button>
      </div>

      <div className="sandbox-content" style={{ display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto', flex: 1, paddingRight: '4px' }}>
        {!selectedNode ? (
          <div className="empty-state" style={{ padding: '32px 16px', textAlign: 'center' }}>
            <div className="empty-state-icon" style={{ fontSize: 36, marginBottom: 12 }}>🧭</div>
            <div className="empty-state-title" style={{ fontWeight: 600, fontSize: 14 }}>Select an Intersection</div>
            <div className="empty-state-desc" style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
              Click any junction node (blue circles) on the map or SVG fallback to adjust signal timings.
            </div>
          </div>
        ) : (
          <div className="sandbox-controls glass-card" style={{ padding: 16, marginTop: 12 }}>
            <div className="sandbox-node-info" style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 700, fontSize: 15 }}>Junction ID: {nodeId}</span>
                <span className="badge badge-info" style={{ fontSize: 11 }}>{selectedNode.street_count || 3} branches</span>
              </div>
              {selectedNode.name && (
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                  {selectedNode.name}
                </div>
              )}
            </div>

            {/* Slider controls */}
            <div className="form-group" style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <label className="form-label" style={{ fontSize: 12, fontWeight: 600 }}>🟢 Green Phase Split</label>
                <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--accent-primary)' }}>{green}s</span>
              </div>
              <input
                type="range" min="10" max="120" step="5"
                value={green}
                onChange={e => handleSliderChange('green', Number(e.target.value))}
                style={{ width: '100%' }}
              />
            </div>

            <div className="form-group" style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <label className="form-label" style={{ fontSize: 12, fontWeight: 600 }}>🟡 Amber Transition</label>
                <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--accent-warning)' }}>{amber}s</span>
              </div>
              <input
                type="range" min="2" max="5" step="1"
                value={amber}
                onChange={e => handleSliderChange('amber', Number(e.target.value))}
                style={{ width: '100%' }}
              />
            </div>

            <div className="form-group" style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <label className="form-label" style={{ fontSize: 12, fontWeight: 600 }}>🔴 Red Phase Split</label>
                <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: '#ff4444' }}>{red}s</span>
              </div>
              <input
                type="range" min="10" max="120" step="5"
                value={red}
                onChange={e => handleSliderChange('red', Number(e.target.value))}
                style={{ width: '100%' }}
              />
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <button
                className="btn btn-ghost"
                onClick={handleResetNode}
                style={{ flex: 1, fontSize: 12, justifyContent: 'center' }}
              >
                Reset Timing
              </button>
              <button
                className="btn btn-primary"
                onClick={onRunCustomTest}
                disabled={customSimLoading}
                style={{ flex: 2, fontSize: 12, justifyContent: 'center' }}
              >
                {customSimLoading ? <div className="spinner" style={{ width:12, height:12 }} /> : '⚡ Test Timing'}
              </button>
            </div>
          </div>
        )}

        {/* Results section */}
        {customSimLoading && (
          <div className="sim-progress-card" style={{ marginTop: 16, display: 'flex', gap: '8px', alignItems: 'center' }}>
            <div className="spinner" style={{ width: 18, height: 18, borderWidth: 2 }} />
            <div style={{ fontSize: 12 }}>Running custom validation simulation...</div>
          </div>
        )}

        {customSimResult && !customSimLoading && (
          <div className="sandbox-results" style={{ marginTop: 16 }}>
            <h4 style={{ fontSize: 13, fontWeight: 700, marginBottom: 8, color: 'var(--text-secondary)' }}>
              📊 Sandbox Simulation Outcomes
            </h4>
            <div className="results-grid" style={{ display: 'grid', gap: 8 }}>
              {Object.entries(customSimResult.deltas).map(([key, item]) => {
                const labels = {
                  avg_wait_time_s: { label: 'Avg Wait Time', unit: 's', lowerIsBetter: true },
                  avg_travel_time_s: { label: 'Avg Travel Time', unit: 's', lowerIsBetter: true },
                  avg_speed_kph: { label: 'Avg Speed', unit: 'km/h', lowerIsBetter: false },
                  noise_pollution_db: { label: 'Noise Pollution', unit: 'dBA', lowerIsBetter: true },
                  emissions_proxy: { label: 'CO2 Emissions', unit: 'g/km', lowerIsBetter: true },
                  congestion_ratio: { label: 'Congestion Index', unit: '%', lowerIsBetter: true },
                  efficiency_score: { label: 'Efficiency Score', unit: '', lowerIsBetter: false },
                }
                const conf = labels[key]
                if (!conf) return null

                let beforeStr = item.before
                let afterStr = item.after
                if (key === 'congestion_ratio') {
                  beforeStr = `${round(item.before * 100, 1)}%`
                  afterStr = `${round(item.after * 100, 1)}%`
                } else {
                  beforeStr = `${item.before}${conf.unit}`
                  afterStr = `${item.after}${conf.unit}`
                }

                const isImprovement = conf.lowerIsBetter ? (item.diff < 0) : (item.diff > 0)
                const isNeutral = item.diff === 0
                const colorStyle = isNeutral ? {} : { color: isImprovement ? 'var(--accent-success)' : '#ef4444' }
                const arrow = isNeutral ? '' : isImprovement ? '↓' : '↑'

                return (
                  <div key={key} className="result-row glass-card" style={{ padding: '8px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12 }}>
                    <div>
                      <div style={{ fontWeight: 600 }}>{conf.label}</div>
                      <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                        {beforeStr} → <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{afterStr}</span>
                      </div>
                    </div>
                    <div style={{ ...colorStyle, fontWeight: 700 }}>
                      {arrow} {Math.abs(item.pct)}%
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function round(val, dec) {
  return Number(val).toFixed(dec)
}
