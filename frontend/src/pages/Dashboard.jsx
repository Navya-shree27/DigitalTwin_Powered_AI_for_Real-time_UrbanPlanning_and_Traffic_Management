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
  const [simProgress, setSimProgress]     = useState(null)

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

  // ── Poll progress while simulation is running ────────────────────────────
  useEffect(() => {
    if ((!simRunning && !customSimLoading) || !activeScenarioId) {
      setSimProgress(null)
      return
    }

    let active = true
    const pollProgress = async () => {
      try {
        const data = await scenariosApi.getProgress(activeScenarioId)
        if (active) {
          setSimProgress(data)
        }
      } catch (e) {
        console.warn('Failed to fetch simulation progress:', e)
      }
    }

    pollProgress()
    const timer = setInterval(pollProgress, 1500)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [simRunning, customSimLoading, activeScenarioId])

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
      // Reset sandbox state to avoid leakage across scenarios
      setSelectedNode(null)
      setSignalOverrides({})
      setCustomSimResult(null)
      setEditMode(false)
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
        red_s: val.red_s,
        is_signal: val.is_signal !== false,
        lanes: val.lanes !== undefined ? val.lanes : null,
        has_sidewalk: val.has_sidewalk !== undefined ? val.has_sidewalk : null,
        has_dustbin: val.has_dustbin !== undefined ? val.has_dustbin : null
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
  const agentNarrative = dashboardData?.run?.agent_narrative

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
            onChange={e => {
              setActiveScenarioId(Number(e.target.value))
              // Reset sandbox state to avoid leakage across scenarios
              setSelectedNode(null)
              setSignalOverrides({})
              setCustomSimResult(null)
              setEditMode(false)
            }}
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
          {activeScenarioId && (
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
              {!simRunning && (
                <>
                  <button
                    className="btn btn-primary"
                    onClick={handleRunSimulation}
                    id="btn-run-simulation"
                    disabled={loading}
                  >
                    {hasRun ? '▶ Re-simulate' : '▶ Run Simulation'}
                  </button>
                  {activeScenarioId && (
                    <button
                      className={`btn ${editMode ? 'btn-primary' : 'btn-ghost'}`}
                      onClick={() => {
                        const next = !editMode
                        setEditMode(next)
                        setSelectedNode(null)
                        setCustomSimResult(null)
                        if (next) setRightSidebarOpen(true)  // auto-open right panel when entering sandbox
                      }}
                      id="btn-toggle-edit-mode"
                    >
                      {editMode ? '⚙️ Exit Sandbox' : '🛠️ Signal Sandbox'}
                    </button>
                  )}
                </>
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
        {/* Left sidebar toggle handle when collapsed */}
        {!leftSidebarOpen && (
          <button 
            className="floating-toggle-btn toggle-left-floating"
            onClick={() => setLeftSidebarOpen(true)}
            title="Expand left panel"
          >
            ▶
          </button>
        )}

        {/* Left sidebar collapse handle when open (direct sibling to avoid overflow clipping) */}
        {leftSidebarOpen && (
          <button 
            className="sidebar-collapse-handle handle-left-open"
            onClick={() => setLeftSidebarOpen(false)}
            title="Collapse left panel"
            style={{ left: 'calc(var(--sidebar-width) + 20px)' }}
          >
            ◀
          </button>
        )}

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

          {isReady && agentNarrative && (
            <div className="sidebar-section">
              <div className="sidebar-section-header">
                <span className="sidebar-section-title">🤖 AI Agent Narrative</span>
              </div>
              <div 
                className="glass-card" 
                style={{ 
                  padding: 14, 
                  fontSize: 12, 
                  lineHeight: 1.6, 
                  color: 'var(--text-secondary)', 
                  background: 'rgba(10, 132, 255, 0.05)', 
                  border: '1px solid rgba(10, 132, 255, 0.15)', 
                  borderRadius: 12,
                  whiteSpace: 'pre-line'
                }}
              >
                {agentNarrative}
              </div>
            </div>
          )}

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
            <div className="sim-progress-card" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 10 }}>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <div className="spinner" style={{ width: 20, height: 20, borderWidth: 3 }} />
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>Simulation in progress</div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 2 }}>
                    Running SUMO traffic model & extracting metrics…
                  </div>
                </div>
              </div>
              
              {simProgress && simProgress.progress > 0 && (
                <div style={{ width: '100%', marginTop: 4 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4, fontFamily: 'var(--font-mono)' }}>
                    <span>Progress</span>
                    <span>{simProgress.progress}%</span>
                  </div>
                  <div style={{ width: '100%', height: 6, background: 'rgba(255,255,255,0.08)', borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ width: `${simProgress.progress}%`, height: '100%', background: 'linear-gradient(90deg, #10b981, #3b82f6)', transition: 'width 0.3s ease' }} />
                  </div>
                </div>
              )}
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
            signalOverrides={signalOverrides}
            simRunning={simRunning || customSimLoading}
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

        {/* Right sidebar toggle handle when collapsed */}
        {!rightSidebarOpen && activeScenarioId && (
          <button 
            className="floating-toggle-btn toggle-right-floating"
            onClick={() => setRightSidebarOpen(true)}
            title="Expand right panel"
          >
            ◀
          </button>
        )}
        {/* Right sidebar collapse handle when open */}
        {rightSidebarOpen && activeScenarioId && (
          <button 
            className="sidebar-collapse-handle handle-right-open"
            onClick={() => setRightSidebarOpen(false)}
            title="Collapse right panel"
            style={{ right: 'calc(var(--sidebar-width) + 20px)', left: 'auto' }}
          >
            ▶
          </button>
        )}

        {/* Right sidebar — always shown when a scenario is selected */}
        {activeScenarioId && (
          <aside className={`sidebar-right ${rightSidebarOpen ? 'open' : 'collapsed'}`}>

            {!editMode ? (
              <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                {/* Sandbox Entry Card */}
                <div style={{
                  margin: '12px 12px 0',
                  padding: '14px',
                  borderRadius: 10,
                  background: 'linear-gradient(135deg, rgba(99,102,241,0.15), rgba(139,92,246,0.10))',
                  border: '1px solid rgba(99,102,241,0.3)',
                }}>
                  <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>🛠️ Signal Sandbox</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 10, lineHeight: 1.5 }}>
                    Interactively install/remove signals, tune timings with AI optimization, and test in SUMO.
                  </div>
                  <button
                    className="btn btn-primary"
                    onClick={() => {
                      setEditMode(true)
                      setRightSidebarOpen(true)
                    }}
                    style={{ width: '100%', justifyContent: 'center', fontSize: 12, padding: '8px 12px' }}
                  >
                    ⚡ Enter Signal Sandbox
                  </button>
                  {!isReady && (
                    <div style={{ marginTop: 8, fontSize: 11, color: '#f59e0b', textAlign: 'center' }}>
                      Run a simulation first to enable SUMO testing
                    </div>
                  )}
                </div>

                {/* AI Proposals */}
                <div className="sidebar-section" style={{ flex: 1, marginTop: 0 }}>
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
              </div>
            ) : (
              <SignalSandboxPanel
                selectedNode={selectedNode}
                overrides={signalOverrides}
                setOverrides={setSignalOverrides}
                onRunCustomTest={handleRunCustomTest}
                customSimLoading={customSimLoading}
                customSimResult={customSimResult}
                scenarioId={activeScenarioId}
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
  scenarioId,
  onClose
}) {
  const nodeId = selectedNode?.osmid
  const [green, setGreen] = useState(35)
  const [amber, setAmber] = useState(3)
  const [red, setRed] = useState(35)
  const [lanes, setLanes] = useState(2)
  const [hasSidewalk, setHasSidewalk] = useState(false)
  const [hasDustbin, setHasDustbin] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiResult, setAiResult] = useState(null)
  const [aiError, setAiError] = useState(null)
  const [aiRedesignLoading, setAiRedesignLoading] = useState(false)
  const [aiRedesignResult, setAiRedesignResult] = useState(null)
  const [aiRedesignError, setAiRedesignError] = useState(null)

  // Synchronize slider state when selected node or overrides change
  useEffect(() => {
    if (!nodeId) return
    const isNodeOriginallySignal = selectedNode?.highway === 'traffic_signals'
    const defaultLanes = selectedNode?.street_count >= 4 ? 2 : 1
    const currentOverride = overrides[nodeId] || { 
      green_s: 35, 
      amber_s: 3, 
      red_s: 35, 
      is_signal: isNodeOriginallySignal,
      lanes: defaultLanes,
      has_sidewalk: false,
      has_dustbin: false
    }
    setGreen(currentOverride.green_s)
    setAmber(currentOverride.amber_s)
    setRed(currentOverride.red_s)
    setLanes(currentOverride.lanes ?? defaultLanes)
    setHasSidewalk(!!currentOverride.has_sidewalk)
    setHasDustbin(!!currentOverride.has_dustbin)
    setAiResult(null)
    setAiError(null)
    setAiRedesignResult(null)
    setAiRedesignError(null)
  }, [nodeId, overrides, selectedNode])

  const isNodeOriginallySignal = selectedNode?.highway === 'traffic_signals'
  const currentOverride = nodeId ? (overrides[nodeId] || { 
    green_s: 35, 
    amber_s: 3, 
    red_s: 35, 
    is_signal: isNodeOriginallySignal,
    lanes: selectedNode?.street_count >= 4 ? 2 : 1,
    has_sidewalk: false,
    has_dustbin: false
  }) : null
  const isSignal = currentOverride?.is_signal !== false

  const handleSliderChange = (type, val) => {
    if (!nodeId) return
    const updated = {
      ...(overrides[nodeId] || { 
        is_signal: isSignal,
        lanes: lanes,
        has_sidewalk: hasSidewalk,
        has_dustbin: hasDustbin
      }),
      green_s: type === 'green' ? val : green,
      amber_s: type === 'amber' ? val : amber,
      red_s:   type === 'red'   ? val : red,
    }
    if (type === 'green') setGreen(val)
    if (type === 'amber') setAmber(val)
    if (type === 'red') setRed(val)
    setOverrides(prev => ({ ...prev, [nodeId]: updated }))
  }

  const handleLanesChange = (val) => {
    if (!nodeId) return
    const updated = {
      ...(overrides[nodeId] || { 
        green_s: green, 
        amber_s: amber, 
        red_s: red, 
        is_signal: isSignal,
        has_sidewalk: hasSidewalk,
        has_dustbin: hasDustbin
      }),
      lanes: val
    }
    setLanes(val)
    setOverrides(prev => ({ ...prev, [nodeId]: updated }))
  }

  const handleSidewalkChange = (val) => {
    if (!nodeId) return
    const updated = {
      ...(overrides[nodeId] || { 
        green_s: green, 
        amber_s: amber, 
        red_s: red, 
        is_signal: isSignal,
        lanes: lanes,
        has_dustbin: hasDustbin
      }),
      has_sidewalk: val
    }
    setHasSidewalk(val)
    setOverrides(prev => ({ ...prev, [nodeId]: updated }))
  }

  const handleDustbinChange = (val) => {
    if (!nodeId) return
    const updated = {
      ...(overrides[nodeId] || { 
        green_s: green, 
        amber_s: amber, 
        red_s: red, 
        is_signal: isSignal,
        lanes: lanes,
        has_sidewalk: hasSidewalk
      }),
      has_dustbin: val
    }
    setHasDustbin(val)
    setOverrides(prev => ({ ...prev, [nodeId]: updated }))
  }

  const handleToggleSignal = () => {
    if (!nodeId) return
    const newIsSignal = !isSignal
    setOverrides(prev => ({
      ...prev,
      [nodeId]: { 
        ...(prev[nodeId] || { 
          green_s: green, 
          amber_s: amber, 
          red_s: red,
          lanes: lanes,
          has_sidewalk: hasSidewalk,
          has_dustbin: hasDustbin
        }), 
        is_signal: newIsSignal 
      }
    }))
  }

  const handleResetNode = () => {
    if (!nodeId) return
    const defaultLanes = selectedNode?.street_count >= 4 ? 2 : 1
    setGreen(35); setAmber(3); setRed(35); setLanes(defaultLanes); setHasSidewalk(false); setHasDustbin(false)
    setOverrides(prev => { const copy = { ...prev }; delete copy[nodeId]; return copy })
    setAiResult(null)
    setAiRedesignResult(null)
    setAiRedesignError(null)
  }

  const handleAiOptimize = async () => {
    if (!nodeId || !scenarioId) return
    setAiLoading(true)
    setAiError(null)
    try {
      const result = await scenariosApi.optimizeSignal(scenarioId, nodeId)
      setAiResult(result)
      // Auto-apply the optimized splits to the sliders
      setGreen(result.green_s)
      setAmber(result.amber_s)
      setRed(result.red_s)
      setOverrides(prev => ({
        ...prev,
        [nodeId]: { ...(prev[nodeId] || {}), green_s: result.green_s, amber_s: result.amber_s, red_s: result.red_s, is_signal: true }
      }))
    } catch (e) {
      setAiError(e.message)
    } finally {
      setAiLoading(false)
    }
  }

  const handleAiRedesign = async () => {
    if (!nodeId || !scenarioId) return
    setAiRedesignLoading(true)
    setAiRedesignError(null)
    try {
      const result = await scenariosApi.aiRedesign(scenarioId, nodeId)
      setAiRedesignResult(result)
      setGreen(result.green_s)
      setAmber(result.amber_s)
      setRed(result.red_s)
      setLanes(result.lanes)
      setHasSidewalk(result.has_sidewalk)
      setHasDustbin(result.has_dustbin)
      setOverrides(prev => ({
        ...prev,
        [nodeId]: {
          green_s: result.green_s,
          amber_s: result.amber_s,
          red_s: result.red_s,
          is_signal: result.is_signal,
          lanes: result.lanes,
          has_sidewalk: result.has_sidewalk,
          has_dustbin: result.has_dustbin
        }
      }))
    } catch (e) {
      setAiRedesignError(e.message)
    } finally {
      setAiRedesignLoading(false)
    }
  }

  const totalCycle = green + amber + red

  return (
    <div className="sandbox-panel-root" style={{ display: 'flex', flexDirection: 'column', height: '100%', paddingTop: '18px' }}>
      <div className="sidebar-section-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 18px 12px' }}>
        <span className="sidebar-section-title">🚦 Signal Sandbox</span>
        <button className="btn btn-ghost" style={{ padding: '2px 6px', fontSize: 12 }} onClick={onClose}>✕ Exit</button>
      </div>

      <div className="sandbox-content" style={{ display: 'flex', flexDirection: 'column', gap: '14px', overflowY: 'auto', flex: 1, paddingRight: '4px' }}>
        {!selectedNode ? (
          <div className="empty-state" style={{ padding: '32px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>🧭</div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>Select an Intersection</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
              Click any junction on the map to customize its signal configuration.
            </div>
          </div>
        ) : (
          <>
            {/* Node info card */}
            <div className="glass-card" style={{ padding: '12px 14px', marginTop: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <span style={{ fontWeight: 700, fontSize: 14 }}>
                  {selectedNode.name || `Node ${nodeId}`}
                </span>
                <span className="badge badge-info" style={{ fontSize: 10 }}>{selectedNode.street_count || 3} arms</span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                OSM ID: {nodeId}
              </div>

              {/* Install / Remove Signal Toggle */}
              <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
                <button
                  onClick={handleToggleSignal}
                  style={{
                    flex: 1, fontSize: 12, padding: '7px 10px', borderRadius: 8,
                    border: `1.5px solid ${isSignal ? '#ef4444' : '#10b981'}`,
                    background: isSignal ? 'rgba(239,68,68,0.10)' : 'rgba(16,185,129,0.10)',
                    color: isSignal ? '#ef4444' : '#10b981',
                    fontWeight: 700, cursor: 'pointer', transition: 'all 0.2s'
                  }}
                >
                  {isSignal ? '🔴 Remove Signal' : '🟢 Install Signal'}
                </button>
              </div>

              {!isSignal && (
                <div style={{
                  marginTop: 8, padding: '6px 10px', borderRadius: 6,
                  background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.3)',
                  fontSize: 11, color: '#f59e0b'
                }}>
                  ⚠ This junction will be simulated as an unsignalized priority intersection.
                </div>
              )}
            </div>

            {/* Signal timing controls (only when signal is active) */}
            {isSignal && (
              <div className="glass-card" style={{ padding: '14px', gap: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <span style={{ fontSize: 13, fontWeight: 700 }}>Signal Timing</span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    Cycle: {totalCycle}s
                  </span>
                </div>

                {/* Cycle bar visualization */}
                <div style={{ display: 'flex', height: 10, borderRadius: 5, overflow: 'hidden', marginBottom: 14 }}>
                  <div style={{ flex: green, background: '#10b981' }} title={`Green: ${green}s`} />
                  <div style={{ flex: amber, background: '#f59e0b' }} title={`Amber: ${amber}s`} />
                  <div style={{ flex: red, background: '#ef4444' }} title={`Red: ${red}s`} />
                </div>

                {[
                  { type: 'green', label: '🟢 Green Phase', val: green, min: 10, max: 120, step: 5, color: '#10b981' },
                  { type: 'amber', label: '🟡 Amber', val: amber, min: 2, max: 8, step: 1, color: '#f59e0b' },
                  { type: 'red',   label: '🔴 Red Phase', val: red, min: 10, max: 120, step: 5, color: '#ef4444' }
                ].map(({ type, label, val, min, max, step, color }) => (
                  <div key={type} style={{ marginBottom: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <label style={{ fontSize: 12, fontWeight: 600 }}>{label}</label>
                      <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color }}>{val}s</span>
                    </div>
                    <input
                      type="range" min={min} max={max} step={step} value={val}
                      onChange={e => handleSliderChange(type, Number(e.target.value))}
                      style={{ width: '100%', accentColor: color }}
                    />
                  </div>
                ))}

                {/* AI Auto-Optimize */}
                <div style={{
                  marginTop: 4, padding: '10px 12px', borderRadius: 8,
                  background: 'linear-gradient(135deg, rgba(99,102,241,0.12), rgba(139,92,246,0.12))',
                  border: '1px solid rgba(99,102,241,0.25)'
                }}>
                  <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6, color: '#a78bfa' }}>
                    🤖 Webster's AI Optimizer
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>
                    Computes optimal green split using IRC:106 / Webster's Equation based on real approach flows.
                  </div>
                  <button
                    onClick={handleAiOptimize}
                    disabled={aiLoading}
                    style={{
                      width: '100%', padding: '8px 12px', borderRadius: 7, fontSize: 12, fontWeight: 700,
                      background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                      color: '#fff', border: 'none', cursor: aiLoading ? 'not-allowed' : 'pointer',
                      opacity: aiLoading ? 0.7 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8
                    }}
                  >
                    {aiLoading ? <><div className="spinner" style={{ width: 12, height: 12, borderColor: '#fff #fff transparent' }} /> Optimizing…</> : '⚡ AI Auto-Optimize Timing'}
                  </button>

                  {aiError && (
                    <div style={{ marginTop: 8, fontSize: 11, color: '#ef4444' }}>⚠ {aiError}</div>
                  )}
                  {aiResult && !aiLoading && (
                    <div style={{ marginTop: 8, padding: '8px 10px', borderRadius: 6, background: 'rgba(16,185,129,0.10)', border: '1px solid rgba(16,185,129,0.25)' }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: '#10b981', marginBottom: 4 }}>
                        ✅ Optimal splits applied
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.6 }}>
                        Cycle: <b style={{ color: 'var(--text-primary)' }}>{aiResult.cycle_s}s</b> · Y-ratio: <b style={{ color: 'var(--text-primary)' }}>{aiResult.Y}</b> · {aiResult.approaches} approaches
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Infrastructure Editor (Road width/lanes, sidewalk/footpath, dustbins) */}
            <div className="glass-card" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '12px', marginTop: 10 }}>
              <div style={{ fontSize: 13, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6 }}>
                <span>🏗️</span> Infrastructure Sandbox
              </div>
              
              {/* Lanes slider */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 600 }}>🛣️ Road Lanes (Width)</span>
                  <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: '#6366f1', fontWeight: 700 }}>{lanes} lanes</span>
                </div>
                <input
                  type="range" min={1} max={4} step={1} value={lanes}
                  onChange={e => handleLanesChange(Number(e.target.value))}
                  style={{ width: '100%', accentColor: '#6366f1', cursor: 'pointer' }}
                />
              </div>

              <div style={{ height: '1px', background: 'rgba(255,255,255,0.08)' }} />

              {/* Sidewalk checkbox */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 12, fontWeight: 600 }}>🚶‍♂️ Sidewalk / Footpath</span>
                <input
                  type="checkbox"
                  checked={hasSidewalk}
                  onChange={e => handleSidewalkChange(e.target.checked)}
                  style={{ width: 16, height: 16, cursor: 'pointer', accentColor: '#6366f1' }}
                />
              </div>

              <div style={{ height: '1px', background: 'rgba(255,255,255,0.08)' }} />

              {/* Dustbin checkbox */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <span style={{ fontSize: 12, fontWeight: 600, display: 'block' }}>🗑️ Dustbin Placement</span>
                  <span style={{ fontSize: 10, color: 'var(--text-muted)', display: 'block', marginTop: 2 }}>Urban recommendation POI layer</span>
                </div>
                <input
                  type="checkbox"
                  checked={hasDustbin}
                  onChange={e => handleDustbinChange(e.target.checked)}
                  style={{ width: 16, height: 16, cursor: 'pointer', accentColor: '#6366f1' }}
                />
              </div>

              <div style={{ height: '1px', background: 'rgba(255,255,255,0.08)' }} />
              
              {/* AI Auto-Redesign */}
              <div style={{
                padding: '10px 12px', borderRadius: 8,
                background: 'linear-gradient(135deg, rgba(16,185,129,0.08), rgba(99,102,241,0.08))',
                border: '1px solid rgba(16,185,129,0.2)'
              }}>
                <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6, color: '#34d399' }}>
                  🤖 AI Agent Auto-Redesign
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>
                  Redesigns the intersection structure (width, sidewalks, dustbins, timings) automatically using optimal capacity guidelines.
                </div>
                <button
                  onClick={handleAiRedesign}
                  disabled={aiRedesignLoading}
                  style={{
                    width: '100%', padding: '8px 12px', borderRadius: 7, fontSize: 12, fontWeight: 700,
                    background: 'linear-gradient(135deg, #10b981, #6366f1)',
                    color: '#fff', border: 'none', cursor: aiRedesignLoading ? 'not-allowed' : 'pointer',
                    opacity: aiRedesignLoading ? 0.7 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8
                  }}
                >
                  {aiRedesignLoading ? <><div className="spinner" style={{ width: 12, height: 12, borderColor: '#fff #fff transparent' }} /> Re-designing…</> : '⚡ AI Redesign Junction'}
                </button>

                {aiRedesignError && (
                  <div style={{ marginTop: 8, fontSize: 11, color: '#ef4444' }}>⚠ {aiRedesignError}</div>
                )}
                {aiRedesignResult && !aiRedesignLoading && (
                  <div style={{ marginTop: 8, padding: '8px 10px', borderRadius: 6, background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.20)' }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#10b981', marginBottom: 4 }}>
                      ✅ Proposed Redesign Reasoning:
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-primary)', lineHeight: 1.5, fontStyle: 'italic' }}>
                      "{aiRedesignResult.reasoning}"
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Action buttons */}
            <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
              <button className="btn btn-ghost" onClick={handleResetNode} style={{ flex: 1, fontSize: 12, justifyContent: 'center' }}>
                Reset
              </button>
              <button
                className="btn btn-primary" onClick={onRunCustomTest} disabled={customSimLoading}
                style={{ flex: 2, fontSize: 12, justifyContent: 'center' }}
              >
                {customSimLoading ? <div className="spinner" style={{ width: 12, height: 12 }} /> : '⚡ Test in SUMO'}
              </button>
            </div>
          </>
        )}

        {/* Running indicator */}
        {customSimLoading && (
          <div className="sim-progress-card" style={{ marginTop: 8, flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
              <div style={{ fontSize: 12, fontWeight: 600 }}>Running SUMO sandbox simulation…</div>
            </div>
            
            {simProgress && simProgress.progress > 0 && (
              <div style={{ width: '100%' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 2, fontFamily: 'var(--font-mono)' }}>
                  <span>Simulating Steps</span>
                  <span>{simProgress.progress}%</span>
                </div>
                <div style={{ width: '100%', height: 4, background: 'rgba(255,255,255,0.08)', borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{ width: `${simProgress.progress}%`, height: '100%', background: '#6366f1', transition: 'width 0.3s ease' }} />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Before/After results */}
        {customSimResult && !customSimLoading && (
          <div style={{ marginTop: 8 }}>
            <div style={{
              fontSize: 13, fontWeight: 700, marginBottom: 10,
              display: 'flex', alignItems: 'center', gap: 6
            }}>
              <span>📊</span> Before / After Comparison
            </div>

            {/* Summary bar */}
            {customSimResult.deltas?.efficiency_score && (
              <div style={{
                marginBottom: 10, padding: '10px 12px', borderRadius: 8,
                background: customSimResult.deltas.efficiency_score.diff > 0
                  ? 'linear-gradient(135deg, rgba(16,185,129,0.15), rgba(16,185,129,0.05))'
                  : 'linear-gradient(135deg, rgba(239,68,68,0.12), rgba(239,68,68,0.04))',
                border: `1px solid ${customSimResult.deltas.efficiency_score.diff > 0 ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`,
              }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>Overall Efficiency</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <span style={{ fontSize: 22, fontWeight: 800, color: customSimResult.deltas.efficiency_score.diff > 0 ? '#10b981' : '#ef4444' }}>
                    {customSimResult.deltas.efficiency_score.after}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    vs <b>{customSimResult.deltas.efficiency_score.before}</b> baseline
                  </span>
                  <span style={{
                    marginLeft: 'auto', fontSize: 13, fontWeight: 700,
                    color: customSimResult.deltas.efficiency_score.diff > 0 ? '#10b981' : '#ef4444'
                  }}>
                    {customSimResult.deltas.efficiency_score.diff > 0 ? '↑' : '↓'} {Math.abs(customSimResult.deltas.efficiency_score.pct)}%
                  </span>
                </div>
              </div>
            )}

            <div style={{ display: 'grid', gap: 7 }}>
              {Object.entries(customSimResult.deltas).map(([key, item]) => {
                const labels = {
                  avg_wait_time_s:    { label: 'Avg Wait', unit: 's', lowerIsBetter: true },
                  avg_travel_time_s:  { label: 'Travel Time', unit: 's', lowerIsBetter: true },
                  avg_speed_kph:      { label: 'Avg Speed', unit: ' km/h', lowerIsBetter: false },
                  congestion_ratio:   { label: 'Congestion', unit: '%', lowerIsBetter: true, pct: true },
                  total_delay_s:      { label: 'Total Delay', unit: 's', lowerIsBetter: true },
                  noise_pollution_db: { label: 'Noise', unit: ' dB', lowerIsBetter: true },
                  emissions_proxy:    { label: 'Emissions', unit: '', lowerIsBetter: true },
                }
                const conf = labels[key]
                if (!conf || key === 'efficiency_score') return null

                const isImprov = conf.lowerIsBetter ? item.diff < 0 : item.diff > 0
                const neutral = item.diff === 0
                const col = neutral ? 'var(--text-muted)' : isImprov ? '#10b981' : '#ef4444'
                const arrow = neutral ? '—' : isImprov ? '▼' : '▲'
                const beforeVal = conf.pct ? `${round(item.before * 100, 1)}%` : `${item.before}${conf.unit}`
                const afterVal  = conf.pct ? `${round(item.after  * 100, 1)}%` : `${item.after}${conf.unit}`

                return (
                  <div key={key} className="glass-card" style={{
                    padding: '8px 12px', display: 'flex', justifyContent: 'space-between',
                    alignItems: 'center', fontSize: 12, borderLeft: `3px solid ${col}`
                  }}>
                    <div>
                      <div style={{ fontWeight: 600 }}>{conf.label}</div>
                      <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                        {beforeVal} → <b style={{ color: 'var(--text-primary)' }}>{afterVal}</b>
                      </div>
                    </div>
                    <div style={{ color: col, fontWeight: 800, fontSize: 14 }}>
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
