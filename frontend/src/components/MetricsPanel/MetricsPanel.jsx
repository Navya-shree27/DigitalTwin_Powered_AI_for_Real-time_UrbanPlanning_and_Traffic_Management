import React from 'react'
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, BarElement, LineElement,
  PointElement, ArcElement, Title, Tooltip, Legend, Filler,
} from 'chart.js'
import { Bar, Doughnut } from 'react-chartjs-2'
import './MetricsPanel.css'

ChartJS.register(
  CategoryScale, LinearScale, BarElement, LineElement,
  PointElement, ArcElement, Title, Tooltip, Legend, Filler,
)

const CHART_COLORS = {
  primary:   '#00d4aa',
  secondary: '#3b82f6',
  warning:   '#f59e0b',
  danger:    '#ef4444',
  success:   '#22c55e',
  muted:     '#475569',
}

const COMMON_CHART_OPTS = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: {
      grid: { color: 'rgba(255,255,255,0.04)' },
      ticks: { color: '#475569', font: { size: 10 } },
    },
    y: {
      grid: { color: 'rgba(255,255,255,0.04)' },
      ticks: { color: '#475569', font: { size: 10 } },
      beginAtZero: true,
    },
  },
}

export default function MetricsPanel({ metrics, isLoading, isReady }) {
  if (isLoading) {
    return (
      <div className="metrics-loading">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="metric-skeleton loading-pulse" />
        ))}
      </div>
    )
  }

  if (!metrics || !isReady) {
    return (
      <div className="metrics-empty">
        <p>Run a simulation to see KPIs</p>
      </div>
    )
  }

  const {
    avg_speed_kph = 0,
    avg_travel_time_s = 0,
    avg_wait_time_s = 0,
    congestion_ratio = 0,
    efficiency_score = 0,
    emissions_proxy = 0,
    throughput_index = 0,
    congested_edges = 0,
    total_edges = 0,
    noise_pollution_db = 0,
  } = metrics

  return (
    <div className="metrics-panel">
      {/* KPI grid */}
      <div className="kpi-grid">
        <KPICard
          label="Avg Speed"
          value={`${avg_speed_kph.toFixed(1)}`}
          unit="km/h"
          color={avg_speed_kph > 30 ? CHART_COLORS.success : avg_speed_kph > 15 ? CHART_COLORS.warning : CHART_COLORS.danger}
        />
        <KPICard
          label="Avg Wait"
          value={`${avg_wait_time_s.toFixed(0)}`}
          unit="sec"
          color={avg_wait_time_s < 30 ? CHART_COLORS.success : avg_wait_time_s < 60 ? CHART_COLORS.warning : CHART_COLORS.danger}
        />
        <KPICard
          label="Congestion"
          value={`${(congestion_ratio * 100).toFixed(1)}`}
          unit="%"
          color={congestion_ratio < 0.2 ? CHART_COLORS.success : congestion_ratio < 0.4 ? CHART_COLORS.warning : CHART_COLORS.danger}
        />
        <KPICard
          label="Efficiency"
          value={`${efficiency_score.toFixed(0)}`}
          unit="/100"
          color={efficiency_score > 70 ? CHART_COLORS.success : efficiency_score > 50 ? CHART_COLORS.warning : CHART_COLORS.danger}
        />
        <KPICard
          label="Noise Level"
          value={`${(noise_pollution_db || 0).toFixed(1)}`}
          unit="dBA"
          color={(noise_pollution_db || 0) < 65 ? CHART_COLORS.success : (noise_pollution_db || 0) < 75 ? CHART_COLORS.warning : CHART_COLORS.danger}
        />
        <KPICard
          label="Emissions"
          value={`${(emissions_proxy * 1000).toFixed(0)}`}
          unit="g/km"
          color={emissions_proxy < 0.02 ? CHART_COLORS.success : emissions_proxy < 0.05 ? CHART_COLORS.warning : CHART_COLORS.danger}
        />
      </div>

      {/* Efficiency doughnut */}
      <div className="chart-section">
        <div className="chart-label">Network Efficiency Score</div>
        <div className="doughnut-wrap">
          <Doughnut
            data={{
              datasets: [{
                data: [efficiency_score, 100 - efficiency_score],
                backgroundColor: [
                  efficiency_score > 70 ? CHART_COLORS.success : efficiency_score > 50 ? CHART_COLORS.warning : CHART_COLORS.danger,
                  'rgba(255,255,255,0.04)',
                ],
                borderWidth: 0,
                circumference: 270,
                rotation: -135,
              }],
            }}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              cutout: '72%',
              plugins: { legend: { display: false }, tooltip: { enabled: false } },
            }}
          />
          <div className="doughnut-center">
            <span className="doughnut-value">{efficiency_score.toFixed(0)}</span>
            <span className="doughnut-unit">/100</span>
          </div>
        </div>
      </div>

      {/* KPI bar chart */}
      <div className="chart-section">
        <div className="chart-label">Key Indicators</div>
        <div style={{ height: 110 }}>
          <Bar
            data={{
              labels: ['Speed', 'Throughput', 'Emissions'],
              datasets: [{
                data: [
                  Math.min(avg_speed_kph / 60 * 100, 100),
                  throughput_index * 100,
                  Math.min(emissions_proxy * 5000, 100),
                ],
                backgroundColor: [
                  CHART_COLORS.primary + 'CC',
                  CHART_COLORS.secondary + 'CC',
                  CHART_COLORS.warning + 'CC',
                ],
                borderRadius: 4,
                borderSkipped: false,
              }],
            }}
            options={{
              ...COMMON_CHART_OPTS,
              scales: {
                ...COMMON_CHART_OPTS.scales,
                y: { ...COMMON_CHART_OPTS.scales.y, max: 100 },
              },
            }}
          />
        </div>
      </div>

      {/* Congestion summary */}
      <div className="congestion-summary">
        <div className="congestion-row">
          <span style={{ color: 'var(--text-muted)' }}>Congested edges</span>
          <span style={{ fontWeight: 600, color: congested_edges > 0 ? CHART_COLORS.danger : CHART_COLORS.success }}>
            {congested_edges} / {total_edges}
          </span>
        </div>
        <div className="congestion-bar-track">
          <div
            className="congestion-bar-fill"
            style={{
              width: `${congestion_ratio * 100}%`,
              background: congestion_ratio < 0.2 ? CHART_COLORS.success : congestion_ratio < 0.4 ? CHART_COLORS.warning : CHART_COLORS.danger,
            }}
          />
        </div>
      </div>
    </div>
  )
}

function KPICard({ label, value, unit, color }) {
  return (
    <div className="kpi-card">
      <div className="kpi-value" style={{ color }}>{value}</div>
      <div className="kpi-unit">{unit}</div>
      <div className="kpi-label">{label}</div>
    </div>
  )
}
