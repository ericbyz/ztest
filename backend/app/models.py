"""Persisted domain entities for the MVP."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    """Create a compact, readable identifier."""

    return f"{prefix}_{uuid4().hex[:12]}"


class Project(Base):
    """An isolated API testing project."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    default_environment: Mapped[str] = mapped_column(String(32), default="test")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    documents: Mapped[list["Document"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    requirements: Mapped[list["Requirement"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    operations: Mapped[list["ApiOperation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    scenarios: Mapped[list["Scenario"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    environments: Mapped[list["Environment"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    source_connectors: Mapped[list["SourceConnector"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    knowledge_bases: Mapped[list["KnowledgeBase"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Environment(Base):
    """A reusable, secret-reference-only test environment."""

    __tablename__ = "environments"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="test")
    base_url: Mapped[str] = mapped_column(String(500), default="")
    auth_type: Mapped[str] = mapped_column(String(32), default="none")
    auth_header: Mapped[str] = mapped_column(String(120), default="Authorization")
    secret_ref: Mapped[str] = mapped_column(String(160), default="")
    allow_hosts_json: Mapped[str] = mapped_column(Text, default="[]")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped[Project] = relationship(back_populates="environments")


class Document(Base):
    """A versioned requirement or API source document."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="parsed")
    content: Mapped[str] = mapped_column(Text, default="")
    issues_json: Mapped[str] = mapped_column(Text, default="[]")
    source_type: Mapped[str] = mapped_column(String(48), default="local_file")
    source_uri: Mapped[str] = mapped_column(String(1000), default="")
    knowledge_base_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_bases.id"), index=True
    )
    local_path: Mapped[str] = mapped_column(String(1000), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped[Project] = relationship(back_populates="documents")
    knowledge_base: Mapped["KnowledgeBase | None"] = relationship(back_populates="documents")


class SourceConnector(Base):
    """A requirement source whose credential lives in local-only storage."""

    __tablename__ = "source_connectors"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_type: Mapped[str] = mapped_column(String(48), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(160), default="")
    auth_type: Mapped[str] = mapped_column(String(32), default="bearer")
    auth_header: Mapped[str] = mapped_column(String(120), default="Authorization")
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="configured")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped[Project] = relationship(back_populates="source_connectors")


class KnowledgeBase(Base):
    """A project-scoped private file knowledge base."""

    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped[Project] = relationship(back_populates="knowledge_bases")
    documents: Mapped[list[Document]] = relationship(
        back_populates="knowledge_base", cascade="all, delete-orphan"
    )


class LlmConfiguration(Base):
    """Global non-secret LLM settings; the API key stays in local storage."""

    __tablename__ = "llm_configurations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    provider: Mapped[str] = mapped_column(String(48), default="openai")
    model: Mapped[str] = mapped_column(String(160), default="")
    base_url: Mapped[str] = mapped_column(String(1000), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Requirement(Base):
    """An atomic, traceable business requirement."""

    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    requirement_id: Mapped[str] = mapped_column(String(80), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(320), default="")
    priority: Mapped[str] = mapped_column(String(16), default="P0")
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    business_rules_json: Mapped[str] = mapped_column(Text, default="[]")
    ambiguities_json: Mapped[str] = mapped_column(Text, default="[]")
    mapped_operations_json: Mapped[str] = mapped_column(Text, default="[]")

    project: Mapped[Project] = relationship(back_populates="requirements")


class ApiOperation(Base):
    """A normalized OpenAPI operation."""

    __tablename__ = "api_operations"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(160), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), default="")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    request_schema_json: Mapped[str] = mapped_column(Text, default="{}")
    response_schema_json: Mapped[str] = mapped_column(Text, default="{}")
    auth_required: Mapped[bool] = mapped_column(Boolean, default=False)
    readiness: Mapped[int] = mapped_column(Integer, default=80)

    project: Mapped[Project] = relationship(back_populates="operations")


class Scenario(Base):
    """A versioned Test IR scenario."""

    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    risk_level: Mapped[str] = mapped_column(String(16), default="medium")
    confidence: Mapped[float] = mapped_column(Float, default=0.82)
    version: Mapped[int] = mapped_column(Integer, default=1)
    ir_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    project: Mapped[Project] = relationship(back_populates="scenarios")
    runs: Mapped[list["TestRun"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )


class TestRun(Base):
    """A scenario execution and its reproducible evidence."""

    __tablename__ = "test_runs"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id"), index=True)
    environment: Mapped[str] = mapped_column(String(32), default="test")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    trigger: Mapped[str] = mapped_column(String(80), default="manual")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    pass_rate: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    scenario: Mapped[Scenario] = relationship(back_populates="runs")


JsonDict = dict[str, Any]
