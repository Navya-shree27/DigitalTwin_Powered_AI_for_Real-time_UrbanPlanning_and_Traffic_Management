import React, { useState, useEffect, useCallback, useRef } from 'react'
import MapView from '../components/MapView/MapView.jsx'
import MetricsPanel from '../components/MetricsPanel/MetricsPanel.jsx'
import IssueList from '../components/IssueList/IssueList.jsx'
import BeforeAfterToggle from '../components/BeforeAfterToggle/BeforeAfterToggle.jsx'
import ScenarioDropdown from '../components/ScenarioDropdown/ScenarioDropdown.jsx'
import { scenariosApi, dashboardApi, proposalsApi, statusApi, googleMapsApi } from '../services/apiClient.js'
import { formatElapsed, formatETA, formatDuration } from '../utils/timeFormat.js'
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

  // Live Timer State
  const [simStartTime, setSimStartTime]           = useState(null)
  const [elapsedSeconds, setElapsedSeconds]       = useState(0)
  const [lastCompletedDuration, setLastCompletedDuration] = useState(null)
  const [justCompleted, setJustCompleted]         = useState(false)

  // System status (SUMO / LLM availability)
  const [systemStatus, setSystemStatus]   = useState(null)

  useEffect(() => {
    statusApi.get().then(s => setSystemStatus(s)).catch(() => {})
  }, [])

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

  const handleDeleteScenario = async (scenarioId) => {
    try {
      await scenariosApi.delete(scenarioId)
      const res = await scenariosApi.list()
      const list = res.scenarios || []
      setScenarios(list)
      if (activeScenarioId === scenarioId) {
        if (list.length > 0) {
          setActiveScenarioId(list[0].id)
        } else {
          setActiveScenarioId(null)
          setDashboardData(null)
        }
      }
    } catch (err) {
      setError(`Failed to delete scenario: ${err.message}`)
    }
  }

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

  // ── Poll dashboard while simulation is running ──────────────────────────
  useEffect(() => {
    if (!simRunning || !activeScenarioId) return
    const timer = setInterval(() => loadDashboard(activeScenarioId), POLL_INTERVAL)
    return () => clearInterval(timer)
  }, [simRunning, activeScenarioId, loadDashboard])

  // ── Live Simulation Stopwatch Timer (250ms ticking) ──────────────────────
  useEffect(() => {
    const isRunning = simRunning || customSimLoading
    if (!isRunning) {
      return
    }

    const startTs = simProgress?.started_timestamp
      ? simProgress.started_timestamp * 1000
      : (simStartTime || Date.now())

    if (!simStartTime) {
      setSimStartTime(startTs)
    }

    const timer = setInterval(() => {
      const currentStart = simProgress?.started_timestamp
        ? simProgress.started_timestamp * 1000
        : startTs
      const now = Date.now()
      const diff = Math.max(0, (now - currentStart) / 1000)
      setElapsedSeconds(diff)
    }, 250)

    return () => clearInterval(timer)
  }, [simRunning, customSimLoading, simProgress?.started_timestamp, simStartTime])

  // ── Poll progress while simulation is running (800ms) ────────────────────
  useEffect(() => {
    if ((!simRunning && !customSimLoading) || !activeScenarioId) {
      setSimProgress(null)
      return
    }

    let active = true
    const pollProgress = async () => {
      try {
        const data = await scenariosApi.getProgress(activeScenarioId)
        if (active && data) {
          setSimProgress(data)
          if (data.status === 'done') {
            if (data.total_duration_s) {
              setLastCompletedDuration(data.total_duration_s)
            }
            setJustCompleted(true)
            setTimeout(() => setJustCompleted(false), 10000)
            loadDashboard(activeScenarioId)
          }
        }
      } catch (e) {
        console.warn('Failed to fetch simulation progress:', e)
      }
    }

    pollProgress()
    const timer = setInterval(pollProgress, 800)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [simRunning, customSimLoading, activeScenarioId, loadDashboard])

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
    const now = Date.now()
    setSimStartTime(now)
    setElapsedSeconds(0)
    setJustCompleted(false)
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
      setSimRunning(false)
    }
  }

  // ── Run Custom Sandbox Simulation ──────────────────────────────────────────
  const handleRunCustomTest = async () => {
    if (!activeScenarioId) return
    setCustomSimLoading(true)
    setError(null)
    const now = Date.now()
    setSimStartTime(now)
    setElapsedSeconds(0)
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
          <ScenarioDropdown
            scenarios={scenarios}
            activeScenarioId={activeScenarioId}
            onSelectScenario={id => {
              setActiveScenarioId(id)
              // Reset sandbox state to avoid leakage across scenarios
              setSelectedNode(null)
              setSignalOverrides({})
              setCustomSimResult(null)
              setEditMode(false)
            }}
            onDeleteScenario={handleDeleteScenario}
          />
          <button
            className="btn btn-ghost"
            onClick={() => setShowNewScenario(true)}
            id="btn-new-scenario"
          >+ New Scenario</button>
        </div>

        <div className="header-right">
          {/* SUMO / Engine status chip */}
          {systemStatus && (
            <div
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '4px 10px', borderRadius: 20,
                fontSize: 11, fontWeight: 600,
                background: systemStatus.sumo?.available
                  ? 'rgba(34,197,94,0.15)' : 'rgba(251,191,36,0.15)',
                border: `1px solid ${systemStatus.sumo?.available
                  ? 'rgba(34,197,94,0.4)' : 'rgba(251,191,36,0.4)'}`,
                color: systemStatus.sumo?.available ? '#86efac' : '#fde68a',
              }}
              title={systemStatus.sumo?.available
                ? `SUMO v${systemStatus.sumo.version} — Live simulation available`
                : 'SUMO not installed — using synthetic simulation (set SUMO_HOME in .env)'}
            >
              <span style={{ fontSize: 8 }}>●</span>
              {systemStatus.sumo?.available
                ? `SUMO v${systemStatus.sumo.version}`
                : 'Synthetic Mode'}
            </div>
          )}
          {simRunning && (
            <div className="sim-status sim-status-timer">
              <div className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} />
              <span className="header-timer-text">
                ⏱️ {formatElapsed(elapsedSeconds)} • ETA {formatETA(simProgress?.eta_s)} ({simProgress?.progress ? Math.round(simProgress.progress) : 0}%)
              </span>
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

            {/* Run completion duration banner */}
            {(justCompleted || dashboardData?.run?.total_duration_s || lastCompletedDuration) && !simRunning && (
              <div className="sim-completed-pill">
                <span className="completed-icon">⚡</span>
                <span>
                  Last run completed in <strong>{formatDuration(dashboardData?.run?.total_duration_s || lastCompletedDuration)}</strong>
                </span>
              </div>
            )}

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
            <div className="sim-progress-card full-timer-card">
              <div className="sim-progress-header">
                <div className="sim-progress-title-row">
                  <div className="sim-spinner-container">
                    <div className="spinner" style={{ width: 18, height: 18, borderWidth: 2.5 }} />
                  </div>
                  <div>
                    <div className="sim-title">Simulation in Progress</div>
                    <div className="sim-stage-desc">
                      {simProgress?.stage_label || 'Executing TraCI loops & vehicle flow simulations…'}
                    </div>
                  </div>
                </div>
              </div>

              {/* High-Precision Timer & Dynamic ETA Display */}
              <div className="sim-timer-grid">
                <div className="sim-timer-box elapsed">
                  <span className="sim-timer-label">⏱️ Elapsed Time</span>
                  <span className="sim-timer-value digital-clock">
                    {formatElapsed(elapsedSeconds)}
                  </span>
                </div>
                <div className="sim-timer-box eta">
                  <span className="sim-timer-label">⏳ Estimated Remaining</span>
                  <span className="sim-timer-value eta-highlight">
                    {formatETA(simProgress?.eta_s)}
                  </span>
                </div>
              </div>

              {/* Real-Time Stepping & Flow Metrics */}
              {simProgress && simProgress.total_steps > 0 && (
                <div className="sim-stats-bar">
                  <span className="sim-stat-item">
                    <strong>Step:</strong> {simProgress.step || 0} / {simProgress.total_steps}
                  </span>
                  {simProgress.steps_per_s > 0 && (
                    <span className="sim-stat-item">
                      <strong>Speed:</strong> {simProgress.steps_per_s} stp/s
                    </span>
                  )}
                  {simProgress.active_vehicles != null && (
                    <span className="sim-stat-item">
                      <strong>Vehicles:</strong> {simProgress.active_vehicles}
                    </span>
                  )}
                </div>
              )}

              {/* Accurate Multi-Stage Progress Bar */}
              <div className="sim-bar-wrapper">
                <div className="sim-bar-labels">
                  <span>Progress</span>
                  <span className="sim-bar-pct">
                    {simProgress?.progress ? `${Math.round(simProgress.progress)}%` : '0%'}
                  </span>
                </div>
                <div className="sim-bar-track">
                  <div
                    className="sim-bar-fill"
                    style={{
                      width: `${Math.min(100, Math.max(simProgress?.progress || 2, 2))}%`,
                    }}
                  />
                </div>
              </div>
            </div>
          )}
        </aside>

        {/* Map — main content */}
        <main className="map-area">
          <MapView
            scenarioId={activeScenarioId}
            scenario={scenario}
            selectedIssue={selectedIssue}
            isReady={isReady}
            selectedNode={selectedNode}
            onSelectNode={(node) => {
              setSelectedNode(node)
              if (node) {
                setEditMode(true)
                setRightSidebarOpen(true)
              }
            }}
            editMode={editMode}
            customTelemetry={customSimResult?.telemetry}
            leftSidebarOpen={leftSidebarOpen}
            rightSidebarOpen={rightSidebarOpen}
            signalOverrides={signalOverrides}
            simRunning={simRunning || customSimLoading}
            simProgress={simProgress}
            elapsedSeconds={elapsedSeconds}
          />

          {/* Before/after overlay — always visible when sim is ready and not in sandbox mode */}
          {isReady && !editMode && (
            <div className="ba-overlay">
              <BeforeAfterToggle
                view={view}
                onToggle={setView}
                metrics={metrics}
                proposals={proposals}
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
                onDetourData={(detour) => {
                  // Future: render detour GeoJSON overlays on MapView
                  console.log('[Detour Plan] Routes computed:', detour?.detour_routes?.length)
                }}
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

      // Poll for result — retry every 2s for up to 60s (validation re-runs simulation)
      let attempts = 0
      const MAX_ATTEMPTS = 30
      const pollInterval = setInterval(async () => {
        attempts++
        try {
          const data = await pApi.get(proposal.id)
          if (data.validation) {
            clearInterval(pollInterval)
            setResult(data.validation)
            onValidated()
            setValidating(false)
          } else if (attempts >= MAX_ATTEMPTS) {
            clearInterval(pollInterval)
            setValidating(false)
          }
        } catch {
          if (attempts >= MAX_ATTEMPTS) {
            clearInterval(pollInterval)
            setValidating(false)
          }
        }
      }, 2000)
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
          <span className={`badge badge-${result?.verdict === 'APPROVED' ? 'approved' : result?.verdict === 'APPROVED_WITH_CONDITIONS' ? 'moderate' : 'rejected'}`}>
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
          {validating ? <><div className="spinner" style={{width:14,height:14}} /> Validating (may take ~30s)…</> : '⚡ Validate Proposal'}
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
  const [geoSearching, setGeoSearching] = useState(false)
  const [geoResult, setGeoResult] = useState(null)
  const [geoError, setGeoError] = useState(null)

  const handleGeocodeSearch = async () => {
    if (!city) return
    setGeoSearching(true)
    setGeoError(null)
    setGeoResult(null)
    try {
      const res = await googleMapsApi.geocode(city)
      if (res.is_live_data && res.formatted_address) {
        setCity(res.formatted_address)
        setGeoResult(res)
        if (!name || name === 'Davanagere Peak Hour') {
          const shortName = res.formatted_address.split(',')[0]
          setName(`${shortName} Traffic Simulation`)
        }
      } else {
        setGeoError(res.error_message || res.message || 'Could not find location')
      }
    } catch (e) {
      setGeoError(e.message || 'Failed to connect to geocoding service')
    } finally {
      setGeoSearching(false)
    }
  }

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
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <label className="form-label" style={{ margin: 0 }}>City / Place Name</label>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={handleGeocodeSearch}
                disabled={geoSearching || !city}
                style={{
                  padding: '3px 10px', fontSize: 11,
                  background: 'rgba(56,189,248,0.15)',
                  border: '1px solid rgba(56,189,248,0.3)',
                  color: '#38bdf8',
                  borderRadius: 6,
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6
                }}
              >
                {geoSearching ? (
                  <><div className="spinner" style={{ width: 10, height: 10, borderWidth: 1.5 }} /> Geocoding…</>
                ) : (
                  '🔍 Google Geocode'
                )}
              </button>
            </div>
            <input
              className="form-input"
              value={city}
              onChange={e => { setCity(e.target.value); setGeoResult(null); setGeoError(null); }}
              placeholder="e.g. Davanagere, Karnataka, India"
              id="input-scenario-city"
            />
            <small className="form-hint">Type any city, area, or landmark and click "Google Geocode".</small>

            {geoResult?.is_live_data && (
              <div style={{
                marginTop: 8, padding: '8px 12px', borderRadius: 8,
                background: 'linear-gradient(135deg, rgba(16,185,129,0.15), rgba(6,182,212,0.08))',
                border: '1px solid rgba(16,185,129,0.35)',
                fontSize: 11.5, color: '#e2e8f0'
              }}>
                <div style={{ fontWeight: 700, color: '#34d399', marginBottom: 2, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span>✓ Location Geocoded ({geoResult.provider || 'Google Maps'})</span>
                </div>
                <div style={{ color: '#f8fafc', fontSize: 12, fontWeight: 600 }}>{geoResult.formatted_address}</div>
                <div style={{ marginTop: 4, display: 'flex', gap: 10, fontSize: 10.5, color: '#94a3b8', fontFamily: 'var(--font-mono)' }}>
                  <span>Lat: <strong>{geoResult.center?.lat?.toFixed(4)}</strong></span>
                  <span>Lon: <strong>{geoResult.center?.lon?.toFixed(4)}</strong></span>
                </div>
              </div>
            )}

            {geoError && (
              <div style={{ marginTop: 6, padding: '6px 10px', borderRadius: 6, background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.3)', fontSize: 11, color: '#fca5a5' }}>
                ⚠ {geoError}
              </div>
            )}
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

          {/* Informational note for large city downloads */}
          <div style={{
            marginTop: 10, padding: '8px 12px', borderRadius: 8,
            background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.2)',
            fontSize: 11, color: '#93c5fd', lineHeight: 1.4
          }}>
            ℹ️ <strong>City Download Notice:</strong> Major cities (e.g. Bengaluru, Delhi) contain thousands of road segments and building footprints. Map download and SUMO digital twin compilation typically takes 20–45 seconds.
          </div>

          {loading && (
            <div style={{
              marginTop: 12, padding: '10px 14px', borderRadius: 8,
              background: 'linear-gradient(135deg, rgba(16,185,129,0.12), rgba(59,130,246,0.10))',
              border: '1px solid rgba(16,185,129,0.3)',
              fontSize: 12, color: '#f8fafc'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, fontWeight: 700, color: '#34d399' }}>
                <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                <span>Downloading & Building Road Network…</span>
              </div>
              <div style={{ fontSize: 11, color: '#cbd5e1', lineHeight: 1.5 }}>
                📡 Fetching OpenStreetMap road graph &amp; Google geocoordinates…<br />
                🚦 Computing intersection topology, lane counts &amp; signal phasings…
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose} disabled={loading}>Cancel</button>
          <button
            className="btn btn-primary"
            onClick={() => onCreate({ name, city, description: desc, forceRebuild: force })}
            disabled={loading || !name || !city}
            id="btn-create-scenario"
          >
            {loading ? <><div className="spinner" style={{width:14,height:14}} /> Building Network…</> : '🚀 Create & Download Map'}
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
  onClose,
  onDetourData
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

  // Tab navigation: signal | capacity | detour | google
  const [sandboxTab, setSandboxTab] = useState('signal')

  // Capacity What-If Analyzer state
  const [capFlow, setCapFlow] = useState(600)
  const [capResult, setCapResult] = useState(null)
  const [capLoading, setCapLoading] = useState(false)
  const [capError, setCapError] = useState(null)

  // Service Detour Planner state
  const [detourClosureType, setDetourClosureType] = useState('full')
  const [detourDays, setDetourDays] = useState(7)
  const [detourResult, setDetourResult] = useState(null)
  const [detourLoading, setDetourLoading] = useState(false)
  const [detourError, setDetourError] = useState(null)

  // Google Maps Platform state
  const [gmapsStatus, setGmapsStatus] = useState(null)
  const [gmapsStreetView, setGmapsStreetView] = useState(null)
  const [gmapsHeading, setGmapsHeading] = useState(0)
  const [gmapsTraffic, setGmapsTraffic] = useState(null)
  const [gmapsPois, setGmapsPois] = useState(null)
  const [gmapsLoading, setGmapsLoading] = useState(false)
  const [gmapsError, setGmapsError] = useState(null)

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

  // ── Capacity What-If Analyzer handler ────────────────────────────────────
  const handleCapacityAnalysis = async () => {
    if (!nodeId || !scenarioId) return
    setCapLoading(true)
    setCapError(null)
    try {
      const result = await scenariosApi.capacityAnalysis(scenarioId, nodeId, {
        flow: capFlow,
        green_s: green,
        amber_s: amber,
        red_s: red,
        lanes,
      })
      setCapResult(result.analysis)
    } catch (e) {
      setCapError(e.message)
    } finally {
      setCapLoading(false)
    }
  }

  // Auto-update capacity when slider or signal params change
  useEffect(() => {
    if (sandboxTab === 'capacity' && nodeId && scenarioId) {
      handleCapacityAnalysis()
    }
  }, [capFlow, green, amber, red, lanes, sandboxTab, nodeId])

  // ── Road Service Detour handler ──────────────────────────────────────────
  const handleServiceDetour = async () => {
    if (!nodeId || !scenarioId) return
    setDetourLoading(true)
    setDetourError(null)
    try {
      const result = await scenariosApi.serviceDetour(scenarioId, nodeId, {
        closure_type: detourClosureType,
        duration_days: detourDays,
      })
      setDetourResult(result.detour)
      if (onDetourData) onDetourData(result.detour)
    } catch (e) {
      setDetourError(e.message)
    } finally {
      setDetourLoading(false)
    }
  }

  // ── Google Maps Platform handlers ─────────────────────────────────────
  const loadGoogleMapsData = async () => {
    if (!selectedNode || !nodeId) return
    const lat = selectedNode.lat || selectedNode.y
    const lon = selectedNode.lon || selectedNode.x
    if (!lat || !lon) return

    setGmapsLoading(true)
    setGmapsError(null)
    try {
      // 1. Status & Street View
      const [statusRes, svRes] = await Promise.all([
        googleMapsApi.getStatus(),
        googleMapsApi.getStreetView(lat, lon, { heading: gmapsHeading }),
      ])
      setGmapsStatus(statusRes)
      setGmapsStreetView(svRes)

      // 2. Nearby Safety POIs
      const poisRes = await googleMapsApi.getNearbyPois(lat, lon, 500)
      setGmapsPois(poisRes)

      // 3. Traffic comparison against adjacent junction
      const trafficRes = await googleMapsApi.trafficCompare({
        origin_lat: lat,
        origin_lon: lon,
        dest_lat: lat + 0.006,
        dest_lon: lon + 0.006,
        simulated_travel_time_s: 140.0,
      })
      setGmapsTraffic(trafficRes)
    } catch (e) {
      setGmapsError(e.message)
    } finally {
      setGmapsLoading(false)
    }
  }

  // Load Google Maps data when switching to google tab or rotating heading
  useEffect(() => {
    if (sandboxTab === 'google' && nodeId) {
      loadGoogleMapsData()
    }
  }, [sandboxTab, nodeId, gmapsHeading])

  const LOS_COLORS = { A: '#22c55e', B: '#84cc16', C: '#eab308', D: '#f97316', E: '#ef4444', F: '#7f1d1d' }

  return (
    <div className="sandbox-panel-root" style={{ display: 'flex', flexDirection: 'column', height: '100%', paddingTop: '18px' }}>
      <div className="sidebar-section-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 18px 12px' }}>
        <span className="sidebar-section-title">🏛️ Municipal Planner</span>
        <button className="btn btn-ghost" style={{ padding: '2px 6px', fontSize: 12 }} onClick={onClose}>✕ Exit</button>
      </div>

      {/* Tab Navigation */}
      <div className="sandbox-tab-bar">
        {[
          { key: 'signal',   label: '⚙️ Signal' },
          { key: 'capacity', label: '📊 Capacity' },
          { key: 'detour',   label: '🚧 Detour' },
          { key: 'google',   label: '🗺️ Google' },
        ].map(tab => (
          <button
            key={tab.key}
            className={`sandbox-tab-btn ${sandboxTab === tab.key ? 'active' : ''}`}
            onClick={() => setSandboxTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="sandbox-content" style={{ display: 'flex', flexDirection: 'column', gap: '14px', overflowY: 'auto', flex: 1, paddingRight: '4px' }}>
        {!selectedNode ? (
          <div className="empty-state" style={{ padding: '32px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>🧭</div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>Select an Intersection</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
              Click any junction on the map to access Signal Config, Capacity Analysis & Road Service Detour tools.
            </div>
          </div>
        ) : (
          <>
            {/* Node info card — always visible */}
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

            {/* ── TAB: Signal Config ─────────────────────────────── */}
            {sandboxTab === 'signal' && (
            <>

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

          {/* ── TAB: Capacity & N-Vehicle What-If Analyzer ─────── */}
          {sandboxTab === 'capacity' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div className="glass-card" style={{ padding: 14 }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10, color: '#f1f5f9' }}>
                  📊 Signal Capacity Analyzer
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 12 }}>
                  Based on IRC:106-2010 &amp; HCM v6 standards. Adjust N-vehicles to see real-world outcomes.
                </div>

                <div style={{ marginBottom: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <label style={{ fontSize: 12, fontWeight: 600 }}>🚗 Arriving Flow (veh/h)</label>
                    <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: '#38bdf8', fontWeight: 700 }}>{capFlow}</span>
                  </div>
                  <input
                    type="range" min={100} max={3500} step={50} value={capFlow}
                    onChange={e => setCapFlow(Number(e.target.value))}
                    style={{ width: '100%', accentColor: '#38bdf8' }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: '#64748b', marginTop: 2 }}>
                    <span>100 veh/h (light)</span><span>3500 veh/h (heavy)</span>
                  </div>
                </div>

                <div style={{ fontSize: 10.5, color: '#94a3b8', marginBottom: 10, fontFamily: 'var(--font-mono)', padding: '6px 8px', background: 'rgba(0,0,0,0.25)', borderRadius: 6 }}>
                  Config: 🟢{green}s / 🟡{amber}s / 🔴{red}s · {lanes} lane{lanes > 1 ? 's' : ''}
                </div>

                {capLoading && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div className="spinner" style={{ width: 14, height: 14 }} />
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Computing IRC/HCM metrics…</span>
                  </div>
                )}
                {capError && <div style={{ color: '#ef4444', fontSize: 11 }}>⚠ {capError}</div>}
              </div>

              {capResult && !capLoading && (
                <>
                  <div className="glass-card" style={{
                    padding: 14,
                    background: `linear-gradient(135deg, ${capResult.los.color}18, rgba(0,0,0,0.5))`,
                    border: `1px solid ${capResult.los.color}50`,
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                      <div>
                        <div style={{ fontSize: 11, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Level of Service</div>
                        <div style={{ fontSize: 11, color: '#cbd5e1', marginTop: 2 }}>{capResult.los.description}</div>
                        <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>Delay: <strong style={{ color: '#f1f5f9' }}>{capResult.los.delay_s}s/vehicle</strong></div>
                      </div>
                      <div style={{ fontSize: 40, fontWeight: 900, color: capResult.los.color, textShadow: `0 0 20px ${capResult.los.color}80`, fontFamily: 'var(--font-mono)', lineHeight: 1 }}>
                        {capResult.los.grade}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                    {[
                      { label: 'Approach Capacity', value: `${capResult.capacity.approach_capacity_pcu_hr.toLocaleString()} PCU/h`, warn: false },
                      { label: 'Max Safe Flow', value: `${capResult.capacity.max_safe_flow_veh_hr.toLocaleString()} veh/h`, warn: capFlow > capResult.capacity.max_safe_flow_veh_hr },
                      { label: 'v/c Saturation', value: (capResult.performance.x_vc * 100).toFixed(1) + '%', warn: capResult.performance.x_vc > 0.85 },
                      { label: 'Queue Backlog', value: `${capResult.performance.queue_vehicles} veh · ${capResult.performance.queue_length_m}m`, warn: capResult.performance.queue_vehicles > 10 },
                      { label: 'Throughput', value: `${capResult.performance.throughput_veh_hr.toLocaleString()} veh/h`, warn: false },
                      { label: 'Blocked/Hour', value: `${capResult.performance.blocked_veh_hr} veh`, warn: capResult.performance.blocked_veh_hr > 0 },
                    ].map((m, i) => (
                      <div key={i} style={{ padding: '8px 10px', borderRadius: 8, background: m.warn ? 'rgba(239,68,68,0.10)' : 'rgba(255,255,255,0.03)', border: `1px solid ${m.warn ? 'rgba(239,68,68,0.3)' : 'rgba(255,255,255,0.06)'}` }}>
                        <div style={{ fontSize: 9.5, color: '#94a3b8', marginBottom: 2 }}>{m.label}</div>
                        <div style={{ fontSize: 11.5, fontWeight: 700, color: m.warn ? '#ef4444' : '#f1f5f9', fontFamily: 'var(--font-mono)' }}>{m.value}</div>
                      </div>
                    ))}
                  </div>

                  {capResult.recommendations?.length > 0 && (
                    <div className="glass-card" style={{ padding: 12 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: '#f59e0b', marginBottom: 8 }}>🏛️ Municipal Engineer Recommendations</div>
                      {capResult.recommendations.map((r, i) => (
                        <div key={i} style={{ fontSize: 11, color: '#cbd5e1', marginBottom: 6, lineHeight: 1.5 }}>{r}</div>
                      ))}
                    </div>
                  )}

                  <div style={{ padding: '8px 10px', borderRadius: 8, background: 'rgba(66,133,244,0.10)', border: '1px solid rgba(66,133,244,0.25)', fontSize: 11, color: '#93c5fd' }}>
                    💡 <strong>Google Maps:</strong> Use Directions API with <code>traffic_model=pessimistic</code> to cross-validate against real-world travel times on this corridor.
                  </div>
                </>
              )}
            </div>
          )}

          {/* ── TAB: Road Service & Citizen Detour Planner ──────── */}
          {sandboxTab === 'detour' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div className="glass-card" style={{ padding: 14 }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6, color: '#f1f5f9' }}>🚧 Road Service &amp; Detour Planner</div>
                <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 12 }}>
                  Simulate road maintenance closure and compute citizen alternate routes with a municipal action plan.
                </div>

                <div style={{ marginBottom: 10 }}>
                  <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>Closure Type</label>
                  <select
                    value={detourClosureType}
                    onChange={e => setDetourClosureType(e.target.value)}
                    style={{ width: '100%', padding: '6px 10px', borderRadius: 7, background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.1)', color: '#f1f5f9', fontSize: 12 }}
                  >
                    <option value="full">Full Closure (No through traffic)</option>
                    <option value="partial">Partial Closure (One lane remains)</option>
                    <option value="junction">Junction Closure</option>
                  </select>
                </div>

                <div style={{ marginBottom: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <label style={{ fontSize: 12, fontWeight: 600 }}>📅 Duration (days)</label>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: '#f59e0b', fontWeight: 700 }}>{detourDays}d</span>
                  </div>
                  <input type="range" min={1} max={90} step={1} value={detourDays} onChange={e => setDetourDays(Number(e.target.value))} style={{ width: '100%', accentColor: '#f59e0b' }} />
                </div>

                <button className="btn btn-primary" onClick={handleServiceDetour} disabled={detourLoading} style={{ width: '100%', justifyContent: 'center', fontSize: 13 }}>
                  {detourLoading ? <><div className="spinner" style={{ width: 12, height: 12 }} /> Computing detour routes…</> : '🔀 Calculate Citizen Detour Routes'}
                </button>
                {detourError && <div style={{ color: '#ef4444', fontSize: 11, marginTop: 6 }}>⚠ {detourError}</div>}
              </div>

              {detourResult && !detourLoading && (
                <>
                  <div style={{ padding: '10px 12px', borderRadius: 8, background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.3)', fontSize: 11.5, color: '#fde68a', lineHeight: 1.5 }}>
                    📣 <strong>Citizen Advisory:</strong> {detourResult.citizen_advisory}
                  </div>

                  {detourResult.detour_routes?.map((route, i) => (
                    <div key={route.route_id} className="glass-card" style={{ padding: 12, border: `1px solid ${i === 0 ? 'rgba(6,182,212,0.35)' : 'rgba(245,158,11,0.3)'}`, background: i === 0 ? 'rgba(6,182,212,0.06)' : 'rgba(245,158,11,0.06)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                        <span style={{ fontWeight: 700, fontSize: 12, color: i === 0 ? '#06b6d4' : '#f59e0b' }}>{route.label}</span>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <span className="badge" style={{ background: 'rgba(239,68,68,0.15)', color: '#fca5a5', fontSize: 9.5 }}>+{route.extra_time_min}min</span>
                          <span className="badge" style={{ background: 'rgba(99,102,241,0.15)', color: '#a5b4fc', fontSize: 9.5 }}>+{route.extra_km}km</span>
                        </div>
                      </div>
                      {route.road_steps?.length > 0 && (
                        <div style={{ fontSize: 10.5, color: '#94a3b8', marginBottom: 6 }}>
                          <span style={{ fontWeight: 600, color: '#cbd5e1' }}>Via: </span>
                          {route.road_steps.slice(0, 4).join(' → ')}{route.road_steps.length > 4 && ' …'}
                        </div>
                      )}
                      <div style={{ display: 'flex', gap: 12, fontSize: 10.5, color: '#94a3b8' }}>
                        <span>🛣️ {(route.distance_m / 1000).toFixed(1)} km</span>
                        <span>⏱️ {Math.round(route.travel_time_s / 60)} min</span>
                        <span>🔀 {route.hops} junctions</span>
                      </div>
                      {route.spillover_roads?.length > 0 && (
                        <div style={{ marginTop: 6, fontSize: 10, color: '#f59e0b', background: 'rgba(245,158,11,0.08)', borderRadius: 5, padding: '4px 8px' }}>
                          ⚠️ Spillover risk: {route.spillover_roads.join(', ')}
                        </div>
                      )}
                    </div>
                  ))}

                  {detourResult.municipal_action_plan?.length > 0 && (
                    <div className="glass-card" style={{ padding: 12 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: '#f1f5f9', marginBottom: 8 }}>📋 Official Municipal Action Plan</div>
                      {detourResult.municipal_action_plan.map((step, i) => (
                        <div key={i} style={{ fontSize: 11, color: '#cbd5e1', marginBottom: 7, paddingBottom: 7, borderBottom: i < detourResult.municipal_action_plan.length - 1 ? '1px solid rgba(255,255,255,0.05)' : 'none', lineHeight: 1.5 }}>{step}</div>
                      ))}
                    </div>
                  )}

                  {detourResult.google_maps_closure_link && (
                    <a href={detourResult.google_maps_closure_link} target="_blank" rel="noopener noreferrer"
                       style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderRadius: 8, background: 'rgba(66,133,244,0.12)', border: '1px solid rgba(66,133,244,0.3)', color: '#93c5fd', fontSize: 11, textDecoration: 'none', fontWeight: 600 }}>
                      🗺️ View Closure Location on Google Maps <span style={{ marginLeft: 'auto', opacity: 0.6 }}>↗</span>
                    </a>
                  )}
                </>
              )}
            </div>
          )}

          {/* ── TAB: Google Maps Platform Intelligence ──────────── */}
          {sandboxTab === 'google' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {/* Google Cloud API Key status header */}
              <div className="glass-card" style={{ padding: 12, background: 'linear-gradient(135deg, rgba(66,133,244,0.12), rgba(52,168,83,0.06))', border: '1px solid rgba(66,133,244,0.3)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: '#93c5fd' }}>
                    🌐 Google Maps Platform
                  </span>
                  <span className={`badge ${gmapsStatus?.is_configured ? 'badge-success' : 'badge-warning'}`} style={{ fontSize: 9.5 }}>
                    {gmapsStatus?.is_configured ? '✓ Key Active ($200/mo Credit)' : '⚡ Simulation Mode (No Key Set)'}
                  </span>
                </div>
                <div style={{ fontSize: 11, color: '#cbd5e1', lineHeight: 1.4 }}>
                  Free tier includes ~40,000 directions/mo, ~28,500 Street View panoramas, and ~10,000 places POI lookups.
                </div>
              </div>

              {gmapsLoading && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 12 }}>
                  <div className="spinner" style={{ width: 14, height: 14 }} />
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Querying Google Maps Platform APIs…</span>
                </div>
              )}

              {/* 1. Street View 360° Visual Audit Card */}
              {gmapsStreetView && (
                <div className="glass-card" style={{ padding: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: '#f1f5f9' }}>📷 Street View 360° Visual Audit</span>
                    <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>Heading: {gmapsHeading}°</span>
                  </div>

                  <div style={{ position: 'relative', width: '100%', height: 160, borderRadius: 8, overflow: 'hidden', background: '#0f172a', border: '1px solid rgba(255,255,255,0.1)' }}>
                    <img
                      src={gmapsStreetView.image_url}
                      alt="Junction Street View"
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      onError={(e) => {
                        e.target.style.display = 'none';
                        e.target.nextSibling.style.display = 'flex';
                      }}
                    />
                    <div style={{ display: 'none', width: '100%', height: '100%', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 6, color: '#94a3b8', fontSize: 11, textAlign: 'center', padding: 12 }}>
                      <span>🏙️ Street View Panorama</span>
                      <small style={{ color: '#64748b' }}>Configure GOOGLE_MAPS_API_KEY in .env to render live imagery.</small>
                    </div>
                  </div>

                  {/* 360° Compass rotation buttons */}
                  <div style={{ display: 'flex', gap: 4, marginTop: 8 }}>
                    {[
                      { label: 'North (0°)', deg: 0 },
                      { label: 'East (90°)', deg: 90 },
                      { label: 'South (180°)', deg: 180 },
                      { label: 'West (270°)', deg: 270 },
                    ].map(h => (
                      <button
                        key={h.deg}
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => setGmapsHeading(h.deg)}
                        style={{
                          flex: 1, padding: '4px 2px', fontSize: 10,
                          background: gmapsHeading === h.deg ? 'rgba(56,189,248,0.2)' : 'rgba(255,255,255,0.03)',
                          borderColor: gmapsHeading === h.deg ? '#38bdf8' : 'rgba(255,255,255,0.06)',
                          color: gmapsHeading === h.deg ? '#38bdf8' : '#94a3b8',
                        }}
                      >
                        {h.label}
                      </button>
                    ))}
                  </div>

                  <a
                    href={gmapsStreetView.interactive_street_view_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 8, padding: '6px 10px', borderRadius: 6, background: 'rgba(59,130,246,0.15)', border: '1px solid rgba(59,130,246,0.3)', color: '#60a5fa', fontSize: 11, textDecoration: 'none', fontWeight: 600 }}
                  >
                    🔄 Open Interactive 360° Street View <span style={{ opacity: 0.6 }}>↗</span>
                  </a>
                </div>
              )}

              {/* 2. Live Real-World Traffic Comparison Card */}
              {gmapsTraffic && (
                <div className="glass-card" style={{ padding: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: '#f1f5f9' }}>🚦 Live Real-World Traffic Calibration</span>
                    <span className="badge" style={{ fontSize: 9.5, background: gmapsTraffic.is_live_data ? 'rgba(34,197,94,0.15)' : 'rgba(251,191,36,0.15)', color: gmapsTraffic.is_live_data ? '#86efac' : '#fde68a' }}>
                      {gmapsTraffic.is_live_data ? 'Live Google Traffic' : 'Calibrated Model'}
                    </span>
                  </div>

                  {gmapsTraffic.google_traffic && (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 8 }}>
                      <div style={{ padding: '6px 8px', background: 'rgba(0,0,0,0.3)', borderRadius: 6, border: '1px solid rgba(255,255,255,0.05)' }}>
                        <div style={{ fontSize: 9.5, color: '#94a3b8' }}>Real Travel Time (Live)</div>
                        <div style={{ fontSize: 13, fontWeight: 800, color: '#38bdf8', fontFamily: 'var(--font-mono)' }}>
                          {gmapsTraffic.google_traffic.duration_in_traffic_min} mins
                        </div>
                      </div>
                      <div style={{ padding: '6px 8px', background: 'rgba(0,0,0,0.3)', borderRadius: 6, border: '1px solid rgba(255,255,255,0.05)' }}>
                        <div style={{ fontSize: 9.5, color: '#94a3b8' }}>Simulated Duration</div>
                        <div style={{ fontSize: 13, fontWeight: 800, color: '#a78bfa', fontFamily: 'var(--font-mono)' }}>
                          {gmapsTraffic.simulated_vs_real_delta?.simulated_duration_min} mins
                        </div>
                      </div>
                    </div>
                  )}

                  <div style={{ fontSize: 11, color: '#cbd5e1', lineHeight: 1.4 }}>
                    <strong>Congestion State:</strong> {gmapsTraffic.google_traffic?.congestion_level}
                  </div>
                </div>
              )}

              {/* 3. Nearby Safety & Civic POIs Card */}
              {gmapsPois && (
                <div className="glass-card" style={{ padding: 12 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#f1f5f9', marginBottom: 8 }}>
                    🏫 Nearby Institutional &amp; Safety POIs
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 8 }}>
                    {gmapsPois.pois?.slice(0, 4).map((poi, i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 8px', borderRadius: 6, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)' }}>
                        <div>
                          <div style={{ fontSize: 11, fontWeight: 600, color: '#f8fafc' }}>{poi.name}</div>
                          <div style={{ fontSize: 9.5, color: '#94a3b8' }}>{poi.vicinity || 'Within 500m'}</div>
                        </div>
                        <span className="badge" style={{ fontSize: 9, background: poi.type === 'school' ? 'rgba(239,68,68,0.15)' : poi.type === 'hospital' ? 'rgba(245,158,11,0.15)' : 'rgba(59,130,246,0.15)', color: poi.type === 'school' ? '#fca5a5' : poi.type === 'hospital' ? '#fde68a' : '#93c5fd' }}>
                          {poi.type.toUpperCase()}
                        </span>
                      </div>
                    ))}
                  </div>

                  {gmapsPois.zoning_advice?.map((adv, i) => (
                    <div key={i} style={{ fontSize: 10.5, color: '#cbd5e1', padding: '4px 0', borderTop: '1px solid rgba(255,255,255,0.04)', lineHeight: 1.4 }}>
                      {adv}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

        {/* Running indicator */}
        {customSimLoading && (
          <div className="sim-progress-card full-timer-card" style={{ marginTop: 8 }}>
            <div className="sim-progress-header">
              <div className="sim-progress-title-row">
                <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700 }}>Running SUMO sandbox simulation…</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    {simProgress?.stage_label || 'Simulating custom signal timings in TraCI…'}
                  </div>
                </div>
              </div>
            </div>

            <div className="sim-timer-grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 6, margin: '8px 0' }}>
              <div className="sim-timer-box elapsed" style={{ padding: '6px 8px' }}>
                <span className="sim-timer-label" style={{ fontSize: 9 }}>⏱️ Elapsed</span>
                <span className="sim-timer-value digital-clock" style={{ fontSize: 12 }}>
                  {formatElapsed(elapsedSeconds)}
                </span>
              </div>
              <div className="sim-timer-box eta" style={{ padding: '6px 8px' }}>
                <span className="sim-timer-label" style={{ fontSize: 9 }}>⏳ ETA</span>
                <span className="sim-timer-value eta-highlight" style={{ fontSize: 12 }}>
                  {formatETA(simProgress?.eta_s)}
                </span>
              </div>
            </div>

            <div className="sim-bar-wrapper" style={{ marginTop: 4 }}>
              <div className="sim-bar-labels" style={{ fontSize: 10 }}>
                <span>Simulating Steps</span>
                <span>{simProgress?.progress ? `${Math.round(simProgress.progress)}%` : '0%'}</span>
              </div>
              <div className="sim-bar-track" style={{ height: 4 }}>
                <div
                  className="sim-bar-fill"
                  style={{
                    width: `${Math.min(100, Math.max(simProgress?.progress || 2, 2))}%`,
                    background: 'linear-gradient(90deg, #6366f1, #38bdf8)',
                  }}
                />
              </div>
            </div>
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
        </>
        )}
      </div>
    </div>
  )
}

function round(val, dec) {
  return Number(val).toFixed(dec)
}
