export type NavKey =
  | 'overview'
  | 'documents'
  | 'requirements'
  | 'api'
  | 'scenarios'
  | 'reports'
  | 'settings'

export interface Project {
  id: string
  name: string
  description: string
  default_environment: string
  archived: boolean
  created_at: string
}

export interface EnvironmentItem {
  id: string
  project_id: string
  name: string
  kind: string
  base_url: string
  auth_type: 'none' | 'bearer' | 'api_key' | 'static_header'
  auth_header: string
  secret_ref: string
  allow_hosts: string[]
  is_default: boolean
  created_at: string
}

export interface TestStep {
  id: string
  type: string
  operation_id: string
  method: string
  path: string
  input: Record<string, unknown>
  extract: Record<string, string>
  assertions: Array<Record<string, unknown>>
}

export interface Scenario {
  id: string
  name: string
  status: string
  risk_level: string
  confidence: number
  version: number
  ir: {
    schema_version: string
    scenario_id: string
    name: string
    requirement_refs: Array<{ id: string; source: string }>
    steps: TestStep[]
    cleanup: Array<Record<string, unknown>>
  }
  validation_errors: string[]
  updated_at: string
}

export interface Run {
  id: string
  scenario_id: string
  scenario_name: string
  environment: string
  status: string
  trigger: string
  duration_ms: number
  pass_rate: number
  result: {
    summary?: { passed: number; failed: number }
    steps?: Array<Record<string, unknown>>
    cleanup?: Array<Record<string, unknown>>
    mode?: string
  }
  started_at: string
  finished_at: string | null
}

export interface Dashboard {
  project: Project
  metrics: {
    requirement_coverage: number
    api_coverage: number
    scenario_pass_rate: number
    pending_reviews: number
  }
  coverage: Array<{ module: string; requirements: number; api: number }>
  recent_runs: Run[]
  pending_reviews: Array<{ label: string; count: number }>
  warnings: Array<{ severity: string; title: string; message: string }>
  featured_scenario: Scenario | null
}

export interface DocumentItem {
  id: string
  name: string
  kind: string
  version: number
  checksum: string
  status: string
  issues: string[]
  source_type: string
  source_uri: string
  knowledge_base_id: string | null
  size_bytes: number
  created_at: string
}

export type ApiSpecType = 'auto' | 'openapi' | 'swagger' | 'postman' | 'har'

export interface SourceConnector {
  id: string
  project_id: string
  name: string
  source_type: 'tapd' | 'external_knowledge'
  endpoint_url: string
  workspace_id: string
  auth_type: 'none' | 'bearer' | 'api_key' | 'basic'
  auth_header: string
  request_params: Record<string, string>
  status: string
  has_secret: boolean
  last_sync_at: string | null
  created_at: string
}

export interface SourceConnectorCreate {
  name: string
  source_type: 'tapd' | 'external_knowledge'
  endpoint_url: string
  workspace_id: string
  auth_type: 'none' | 'bearer' | 'api_key' | 'basic'
  auth_header: string
  secret?: string
  request_params: Record<string, string>
}

export interface McpServerCandidate {
  name: string
  endpoint_url: string
  transport: 'streamable_http' | 'stdio'
  connectable: boolean
  tapd_capable: boolean
  tools: string[]
  project_tool: string
  requirement_tool: string
  error: string
}

export interface McpServerConfiguration {
  id: string
  name: string
  endpoint_url: string
  transport: 'streamable_http'
  auth_type: 'none' | 'bearer' | 'api_key'
  auth_header: string
  enabled: boolean
  has_secret: boolean
  created_at: string
  updated_at: string
}

export interface McpServerConfigurationUpdate {
  name: string
  endpoint_url: string
  transport: 'streamable_http'
  auth_type: McpServerConfiguration['auth_type']
  auth_header: string
  secret?: string
  enabled: boolean
}

export interface TapdMcpProject {
  id: string
  name: string
}

export interface TapdMcpProjects {
  projects: TapdMcpProject[]
  project_tool: string
  requirement_tool: string
}

export interface TapdMcpConnect {
  endpoint_url: string
  tapd_project_id: string
  tapd_project_name: string
  name: string
}

export interface KnowledgeBaseItem {
  id: string
  project_id: string
  name: string
  description: string
  document_count: number
  size_bytes: number
  created_at: string
}

export interface LlmConfiguration {
  provider: 'openai' | 'azure_openai' | 'anthropic' | 'openai_compatible'
  model: string
  base_url: string
  enabled: boolean
  has_api_key: boolean
  api_key_masked: string
  storage: 'local_only'
  updated_at: string | null
}

export interface LlmConfigurationUpdate {
  provider: LlmConfiguration['provider']
  model: string
  base_url: string
  enabled: boolean
  api_key?: string
  clear_api_key?: boolean
}

export interface RequirementItem {
  id: string
  record_id: string
  title: string
  text: string
  source: string
  priority: string
  confidence: number
  status: string
  business_rules: string[]
  ambiguities: string[]
  mapped_operations: Array<{
    operation_id: string
    confidence: number
    reason: string
  }>
}

export interface OperationItem {
  id: string
  method: string
  path: string
  summary: string
  tags: string[]
  auth_required: boolean
  readiness: number
}

export type OperationRelationKind = 'scenario_flow' | 'schema_flow' | 'resource_relation'

export interface OperationGraphEdge {
  id: string
  source: string
  target: string
  kind: OperationRelationKind
  basis: 'explicit' | 'inferred' | 'structural'
  label: string
  evidence: string
  confidence: number
}

export interface OperationGraph {
  nodes: OperationItem[]
  edges: OperationGraphEdge[]
  groups: string[]
}
