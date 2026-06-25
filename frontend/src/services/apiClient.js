import axios from 'axios'

const BASE_URL = '/api'

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 120000,  // 2 minutes — simulations can take time
  headers: { 'Content-Type': 'application/json' },
})

// ── Request / Response interceptors ──────────────────────────────────────────

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      'An unknown error occurred'
    return Promise.reject(new Error(message))
  }
)

// ── Scenarios ─────────────────────────────────────────────────────────────────

export const scenariosApi = {
  list: () => api.get('/scenarios'),

  get: (id) => api.get(`/scenarios/${id}`),

  create: (payload) =>
    api.post('/scenarios', {
      name:          payload.name,
      city:          payload.city || 'Davanagere, Karnataka, India',
      description:   payload.description || '',
      force_rebuild: payload.forceRebuild || false,
    }),

  simulate: (id, options = {}) =>
    api.post(`/scenarios/${id}/simulate`, {
      engine:     options.engine || 'synthetic',
      duration_s: options.duration || 3600,
      seed:       options.seed || 42,
    }),

  listRuns: (id) => api.get(`/scenarios/${id}/runs`),

  getMetrics: (id) => api.get(`/scenarios/${id}/metrics`),

  getIssues: (id, params = {}) =>
    api.get(`/scenarios/${id}/issues`, { params }),

  getProposals: (id, params = {}) =>
    api.get(`/scenarios/${id}/proposals`, { params }),

  testCustomConfig: (id, overrides) =>
    api.post(`/scenarios/${id}/test-custom-config`, { overrides }),
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export const dashboardApi = {
  get: (scenarioId) => api.get(`/dashboard/${scenarioId}`),
  getNetworkGeoJson: (scenarioId) =>
    api.get(`/dashboard/${scenarioId}/geojson/network`),
  getNodesGeoJson: (scenarioId) =>
    api.get(`/dashboard/${scenarioId}/geojson/nodes`),
}

// ── Proposals ─────────────────────────────────────────────────────────────────

export const proposalsApi = {
  get: (proposalDbId) => api.get(`/proposals/${proposalDbId}`),
  validate: (proposalDbId) => api.post(`/proposals/${proposalDbId}/validate`),
}

// ── System ────────────────────────────────────────────────────────────────────

export const systemApi = {
  health: () => axios.get('/health').then((r) => r.data),
}

export default api
