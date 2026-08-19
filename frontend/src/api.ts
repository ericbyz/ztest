import type {
  Dashboard,
  DocumentItem,
  EnvironmentItem,
  OperationItem,
  Project,
  RequirementItem,
  Run,
  Scenario,
} from './types'

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: '请求失败' }))
    const detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail)
    throw new ApiError(detail, response.status)
  }
  return response.json() as Promise<T>
}

export const api = {
  projects: () => request<Project[]>('/api/projects'),
  createProject: (payload: { name: string; description: string; default_environment: string }) =>
    request<Project>('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  dashboard: (projectId: string) => request<Dashboard>(`/api/projects/${projectId}/dashboard`),
  documents: (projectId: string) => request<DocumentItem[]>(`/api/projects/${projectId}/documents`),
  requirements: (projectId: string) =>
    request<RequirementItem[]>(`/api/projects/${projectId}/requirements`),
  operations: (projectId: string) => request<OperationItem[]>(`/api/projects/${projectId}/operations`),
  scenarios: (projectId: string) => request<Scenario[]>(`/api/projects/${projectId}/scenarios`),
  environments: (projectId: string) =>
    request<EnvironmentItem[]>(`/api/projects/${projectId}/environments`),
  createEnvironment: (projectId: string, payload: Omit<EnvironmentItem, 'id' | 'project_id' | 'created_at'>) =>
    request<EnvironmentItem>(`/api/projects/${projectId}/environments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  generateScenario: (projectId: string, requirementIds: string[]) =>
    request<Scenario>(`/api/projects/${projectId}/scenarios:generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ requirement_ids: requirementIds }),
    }),
  updateScenario: (scenarioId: string, ir: Scenario['ir']) =>
    request<Scenario>(`/api/scenarios/${scenarioId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ir }),
    }),
  approveScenario: (scenarioId: string) =>
    request<Scenario>(`/api/scenarios/${scenarioId}:approve`, { method: 'POST' }),
  runScenario: (scenarioId: string, environmentId: string | undefined, mode: 'simulated' | 'live') =>
    request<Run>('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario_id: scenarioId, environment_id: environmentId, mode }),
    }),
  updateRequirement: (requirementId: string, status: string) =>
    request<RequirementItem>(`/api/requirements/${requirementId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    }),
  uploadDocument: async (projectId: string, kind: 'requirement' | 'openapi', file: File) => {
    const form = new FormData()
    form.append('file', file)
    const path = kind === 'openapi' ? 'api-specs' : 'documents'
    return request<DocumentItem>(`/api/projects/${projectId}/${path}`, { method: 'POST', body: form })
  },
  analyze: (projectId: string) =>
    request<{ requirements: number; operations: number }>(`/api/projects/${projectId}/analysis`, {
      method: 'POST',
    }),
  exportUrl: (projectId: string) => `/api/projects/${projectId}/exports`,
}
