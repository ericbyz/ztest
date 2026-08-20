"""Pydantic request and response contracts."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr


class ProjectCreate(BaseModel):
    """Payload for creating a project."""

    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=2000)
    default_environment: Literal["local", "dev", "test", "staging", "production"] = "test"


class ProjectView(ProjectCreate):
    """Project response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    archived: bool
    created_at: datetime


class ProjectUpdate(BaseModel):
    """Editable project properties."""

    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    default_environment: Literal["local", "dev", "test", "staging", "production"] | None = None
    archived: bool | None = None


class EnvironmentCreate(BaseModel):
    """Reusable execution environment without plaintext credentials."""

    name: str = Field(min_length=2, max_length=120)
    kind: Literal["local", "dev", "test", "staging", "production"] = "test"
    base_url: str = Field(default="", max_length=500)
    auth_type: Literal["none", "bearer", "api_key", "static_header"] = "none"
    auth_header: str = Field(default="Authorization", max_length=120)
    secret_ref: str = Field(default="", pattern=r"^[A-Z][A-Z0-9_]*$|^$")
    allow_hosts: list[str] = Field(default_factory=list, max_length=20)
    is_default: bool = False


class EnvironmentView(EnvironmentCreate):
    """Environment response."""

    id: str
    project_id: str
    created_at: datetime


class DocumentView(BaseModel):
    """Document metadata response."""

    id: str
    name: str
    kind: str
    version: int
    checksum: str
    status: str
    issues: list[str]
    source_type: str
    source_uri: str
    knowledge_base_id: str | None
    size_bytes: int
    created_at: datetime


ApiSpecType = Literal["auto", "openapi", "swagger", "postman", "har"]


class ApiSpecUrlImport(BaseModel):
    """API specification URL import payload."""

    url: HttpUrl
    spec_type: ApiSpecType = "auto"


class SourceConnectorCreate(BaseModel):
    """TAPD or external knowledge source with a write-only credential."""

    name: str = Field(min_length=2, max_length=160)
    source_type: Literal["tapd", "external_knowledge"]
    endpoint_url: HttpUrl
    workspace_id: str = Field(default="", max_length=160)
    auth_type: Literal["none", "bearer", "api_key", "basic"] = "bearer"
    auth_header: str = Field(default="Authorization", max_length=120)
    secret: SecretStr | None = None
    request_params: dict[str, str] = Field(default_factory=dict)


class SourceConnectorView(BaseModel):
    """Connector metadata that never serializes its credential."""

    id: str
    project_id: str
    name: str
    source_type: str
    endpoint_url: str
    workspace_id: str
    auth_type: str
    auth_header: str
    request_params: dict[str, str]
    status: str
    has_secret: bool
    last_sync_at: datetime | None
    created_at: datetime


class TapdMcpDiscover(BaseModel):
    """Optional manual endpoint used alongside automatic local discovery."""

    endpoint_url: str = Field(default="", max_length=500)


class McpServerView(BaseModel):
    """Sanitized local MCP discovery result; never includes process env or credentials."""

    name: str
    endpoint_url: str
    transport: Literal["streamable_http", "stdio"]
    connectable: bool
    tapd_capable: bool
    tools: list[str]
    project_tool: str
    requirement_tool: str
    error: str


class McpServerConfiguration(BaseModel):
    """Write-only-secret configuration for a user-managed HTTP MCP server."""

    name: str = Field(min_length=2, max_length=160)
    endpoint_url: str = Field(min_length=8, max_length=500)
    transport: Literal["streamable_http"] = "streamable_http"
    auth_type: Literal["none", "bearer", "api_key"] = "none"
    auth_header: str = Field(default="Authorization", max_length=120)
    secret: SecretStr | None = None
    enabled: bool = True


class McpServerConfigurationView(BaseModel):
    """Sanitized managed MCP metadata returned to the browser."""

    id: str
    name: str
    endpoint_url: str
    transport: Literal["streamable_http"]
    auth_type: Literal["none", "bearer", "api_key"]
    auth_header: str
    enabled: bool
    has_secret: bool
    created_at: datetime
    updated_at: datetime


class TapdMcpProjectView(BaseModel):
    """A selectable TAPD workspace/project exposed by the local MCP server."""

    id: str
    name: str


class TapdMcpProjectsRequest(BaseModel):
    """Request project options from one loopback MCP endpoint."""

    endpoint_url: str = Field(min_length=8, max_length=500)


class TapdMcpProjectsView(BaseModel):
    """Project options and compatible tool metadata."""

    projects: list[TapdMcpProjectView]
    project_tool: str
    requirement_tool: str


class TapdMcpConnect(BaseModel):
    """Bind one TAPD project to the current test project through local MCP."""

    endpoint_url: str = Field(min_length=8, max_length=500)
    tapd_project_id: str = Field(min_length=1, max_length=160)
    tapd_project_name: str = Field(default="", max_length=160)
    name: str = Field(default="TAPD MCP", min_length=2, max_length=160)


class KnowledgeBaseCreate(BaseModel):
    """Create a project-scoped private file knowledge base."""

    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=2000)


class KnowledgeBaseView(KnowledgeBaseCreate):
    """Knowledge base summary without private file contents."""

    id: str
    project_id: str
    document_count: int
    size_bytes: int
    created_at: datetime


class KnowledgeSearchResult(BaseModel):
    """A local lexical knowledge match."""

    document_id: str
    document_name: str
    source: str
    snippet: str
    score: int


class LlmConfigurationUpdate(BaseModel):
    """Global LLM settings with a write-only API key."""

    provider: Literal["openai", "azure_openai", "anthropic", "openai_compatible"]
    model: str = Field(min_length=1, max_length=160)
    base_url: str = Field(default="", max_length=1000)
    enabled: bool = True
    api_key: SecretStr | None = None
    clear_api_key: bool = False


class LlmConfigurationView(BaseModel):
    """LLM settings response with a masked credential status only."""

    provider: str
    model: str
    base_url: str
    enabled: bool
    has_api_key: bool
    api_key_masked: str
    storage: Literal["local_only"] = "local_only"
    updated_at: datetime | None


class RequirementView(BaseModel):
    """Atomic requirement response."""

    id: str
    record_id: str
    title: str
    text: str
    source: str
    priority: str
    confidence: float
    status: str
    business_rules: list[str]
    ambiguities: list[str]
    mapped_operations: list[dict[str, Any]]


class RequirementUpdate(BaseModel):
    """Editable requirement fields."""

    title: str | None = Field(default=None, min_length=2, max_length=240)
    text: str | None = Field(default=None, min_length=2)
    status: Literal["pending", "approved", "ignored"] | None = None


class OperationView(BaseModel):
    """Normalized API operation response."""

    id: str
    method: str
    path: str
    summary: str
    tags: list[str]
    request_schema: dict[str, Any]
    response_schema: dict[str, Any]
    auth_required: bool
    readiness: int


class ScenarioGenerate(BaseModel):
    """Scenario generation request."""

    requirement_ids: list[str] = Field(min_length=1, max_length=20)


class ScenarioUpdate(BaseModel):
    """Scenario Test IR update."""

    name: str | None = Field(default=None, min_length=2, max_length=240)
    ir: dict[str, Any] | None = None


class ScenarioView(BaseModel):
    """Scenario response."""

    id: str
    name: str
    status: str
    risk_level: str
    confidence: float
    version: int
    ir: dict[str, Any]
    validation_errors: list[str] = Field(default_factory=list)
    updated_at: datetime


class RunCreate(BaseModel):
    """Run request with safe simulated execution as the default."""

    scenario_id: str
    environment_id: str | None = None
    environment: Literal["local", "dev", "test", "staging", "production"] = "test"
    mode: Literal["simulated", "live"] = "simulated"
    base_url: str | None = None
    allow_hosts: list[str] = Field(default_factory=list, max_length=20)


class RunView(BaseModel):
    """Run report response."""

    id: str
    scenario_id: str
    scenario_name: str
    environment: str
    status: str
    trigger: str
    duration_ms: int
    pass_rate: int
    result: dict[str, Any]
    started_at: datetime
    finished_at: datetime | None


class DashboardView(BaseModel):
    """Aggregated project dashboard response."""

    project: ProjectView
    metrics: dict[str, int]
    coverage: list[dict[str, Any]]
    recent_runs: list[RunView]
    pending_reviews: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    featured_scenario: ScenarioView | None
