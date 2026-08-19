"""Pydantic request and response contracts."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


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
    created_at: datetime


class OpenApiUrlImport(BaseModel):
    """OpenAPI URL import payload."""

    url: HttpUrl


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
