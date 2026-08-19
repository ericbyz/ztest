export type NavKey =
  | 'overview'
  | 'documents'
  | 'requirements'
  | 'api'
  | 'scenarios'
  | 'reports'

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
  created_at: string
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
