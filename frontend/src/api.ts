import type {
  Dashboard,
  DocumentItem,
  EnvironmentItem,
  KnowledgeBaseItem,
  LlmConfiguration,
  LlmConfigurationUpdate,
  OperationItem,
  Project,
  RequirementItem,
  Run,
  Scenario,
  SourceConnector,
  SourceConnectorCreate,
  McpServerCandidate,
  McpServerConfiguration,
  McpServerConfigurationUpdate,
  TapdMcpConnect,
  TapdMcpProjects,
  ApiSpecType,
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
  sources: (projectId: string) =>
    request<SourceConnector[]>(`/api/projects/${projectId}/sources`),
  createSource: (projectId: string, payload: SourceConnectorCreate) =>
    request<SourceConnector>(`/api/projects/${projectId}/sources`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  syncSource: (sourceId: string) =>
    request<DocumentItem>(`/api/sources/${sourceId}:sync`, { method: 'POST' }),
  mcpServers: () => request<McpServerConfiguration[]>('/api/mcp/servers'),
  createMcpServer: (payload: McpServerConfigurationUpdate) =>
    request<McpServerConfiguration>('/api/mcp/servers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  updateMcpServer: (serverId: string, payload: McpServerConfigurationUpdate) =>
    request<McpServerConfiguration>(`/api/mcp/servers/${serverId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  deleteMcpServer: (serverId: string) =>
    request<{ ok: boolean }>(`/api/mcp/servers/${serverId}`, { method: 'DELETE' }),
  testMcpServer: (serverId: string) =>
    request<McpServerCandidate>(`/api/mcp/servers/${serverId}:test`, { method: 'POST' }),
  discoverTapdMcp: (endpointUrl = '') =>
    request<McpServerCandidate[]>('/api/mcp/tapd:discover', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint_url: endpointUrl }),
    }),
  tapdMcpProjects: (endpointUrl: string) =>
    request<TapdMcpProjects>('/api/mcp/tapd:projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint_url: endpointUrl }),
    }),
  connectTapdMcp: (projectId: string, payload: TapdMcpConnect) =>
    request<SourceConnector>(`/api/projects/${projectId}/sources:connect-tapd-mcp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  knowledgeBases: (projectId: string) =>
    request<KnowledgeBaseItem[]>(`/api/projects/${projectId}/knowledge-bases`),
  createKnowledgeBase: (projectId: string, payload: { name: string; description: string }) =>
    request<KnowledgeBaseItem>(`/api/projects/${projectId}/knowledge-bases`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  uploadKnowledgeDocument: async (knowledgeBaseId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DocumentItem>(`/api/knowledge-bases/${knowledgeBaseId}/documents`, {
      method: 'POST', body: form,
    })
  },
  extractKnowledgeRequirements: (knowledgeBaseId: string) =>
    request<{ documents: number; requirements: number }>(
      `/api/knowledge-bases/${knowledgeBaseId}:extract-requirements`,
      { method: 'POST' },
    ),
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
  uploadDocument: async (projectId: string, kind: 'requirement' | 'api', file: File, specType: ApiSpecType = 'auto') => {
    const form = new FormData()
    form.append('file', file)
    if (kind === 'api') form.append('spec_type', specType)
    const path = kind === 'api' ? 'api-specs' : 'documents'
    return request<DocumentItem>(`/api/projects/${projectId}/${path}`, { method: 'POST', body: form })
  },
  importApiUrl: (projectId: string, url: string, specType: ApiSpecType) =>
    request<DocumentItem>(`/api/projects/${projectId}/api-specs:url`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, spec_type: specType }),
    }),
  llmConfiguration: () => request<LlmConfiguration>('/api/settings/llm'),
  updateLlmConfiguration: (payload: LlmConfigurationUpdate) =>
    request<LlmConfiguration>('/api/settings/llm', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  testLlmConfiguration: () =>
    request<{ ok: boolean; provider: string; model: string }>('/api/settings/llm:test', {
      method: 'POST',
    }),
  analyze: (projectId: string) =>
    request<{ requirements: number; operations: number }>(`/api/projects/${projectId}/analysis`, {
      method: 'POST',
    }),
  exportUrl: (projectId: string) => `/api/projects/${projectId}/exports`,
}
