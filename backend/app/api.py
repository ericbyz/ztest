"""HTTP API for the AI Test Tool MVP."""

from __future__ import annotations

import os
from base64 import b64encode
from io import BytesIO
from typing import Annotated, Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_session
from .local_store import (
    delete_secret,
    get_secret,
    has_secret,
    mask_secret,
    read_mcp_servers,
    set_secret,
    store_knowledge_file,
    write_mcp_servers,
)
from .mcp_client import (
    McpError,
    discover_local_servers,
    fetch_tapd_requirements,
    inspect_server,
    list_tapd_projects,
    validate_managed_mcp_url,
    validate_registered_mcp_url,
)
from .models import (
    ApiOperation,
    Document,
    Environment,
    KnowledgeBase,
    LlmConfiguration,
    Project,
    Requirement,
    Scenario,
    SourceConnector,
    TestRun,
    new_id,
    utc_now,
)
from .schemas import (
    ApiSpecUrlImport,
    DashboardView,
    DocumentView,
    EnvironmentCreate,
    EnvironmentView,
    KnowledgeBaseCreate,
    KnowledgeBaseView,
    KnowledgeSearchResult,
    LlmConfigurationUpdate,
    LlmConfigurationView,
    McpServerConfiguration,
    McpServerConfigurationView,
    McpServerView,
    OperationGraphEdge,
    OperationGraphView,
    OperationView,
    ProjectCreate,
    ProjectUpdate,
    ProjectView,
    RequirementUpdate,
    RequirementView,
    RunCreate,
    RunView,
    ScenarioGenerate,
    ScenarioUpdate,
    ScenarioView,
    SourceConnectorCreate,
    SourceConnectorView,
    TapdMcpConnect,
    TapdMcpDiscover,
    TapdMcpProjectsRequest,
    TapdMcpProjectsView,
)
from .security import UnsafeTargetError, validate_target
from .services import (
    build_scenario,
    checksum,
    dumps,
    derive_operation_relationships,
    execute_scenario,
    export_pytest,
    external_payload_to_text,
    extract_text,
    finished_now,
    loads,
    map_requirements,
    normalize_operations,
    parse_api_document,
    parse_openapi,
    parse_requirements,
    run_to_dict,
    search_knowledge_documents,
    validate_ir,
)

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]


def _project_or_404(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def _scenario_or_404(session: Session, scenario_id: str) -> Scenario:
    scenario = session.get(Scenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="场景不存在")
    return scenario


def _document_view(document: Document) -> DocumentView:
    return DocumentView(
        id=document.id,
        name=document.name,
        kind=document.kind,
        version=document.version,
        checksum=document.checksum,
        status=document.status,
        issues=loads(document.issues_json, []),
        source_type=document.source_type,
        source_uri=document.source_uri,
        knowledge_base_id=document.knowledge_base_id,
        size_bytes=document.size_bytes,
        created_at=document.created_at,
    )


def _requirement_view(requirement: Requirement) -> RequirementView:
    return RequirementView(
        id=requirement.requirement_id,
        record_id=requirement.id,
        title=requirement.title,
        text=requirement.text,
        source=requirement.source,
        priority=requirement.priority,
        confidence=requirement.confidence,
        status=requirement.status,
        business_rules=loads(requirement.business_rules_json, []),
        ambiguities=loads(requirement.ambiguities_json, []),
        mapped_operations=loads(requirement.mapped_operations_json, []),
    )


def _operation_view(operation: ApiOperation) -> OperationView:
    return OperationView(
        id=operation.operation_id,
        method=operation.method,
        path=operation.path,
        summary=operation.summary,
        tags=loads(operation.tags_json, []),
        request_schema=loads(operation.request_schema_json, {}),
        response_schema=loads(operation.response_schema_json, {}),
        auth_required=operation.auth_required,
        readiness=operation.readiness,
    )


def _scenario_view(session: Session, scenario: Scenario) -> ScenarioView:
    operation_ids = set(
        session.scalars(
            select(ApiOperation.operation_id).where(
                ApiOperation.project_id == scenario.project_id
            )
        ).all()
    )
    ir = loads(scenario.ir_json, {})
    return ScenarioView(
        id=scenario.id,
        name=scenario.name,
        status=scenario.status,
        risk_level=scenario.risk_level,
        confidence=scenario.confidence,
        version=scenario.version,
        ir=ir,
        validation_errors=validate_ir(ir, operation_ids),
        updated_at=scenario.updated_at,
    )


def _environment_view(environment: Environment) -> EnvironmentView:
    """Serialize an environment without resolving its secret reference."""

    return EnvironmentView(
        id=environment.id,
        project_id=environment.project_id,
        name=environment.name,
        kind=environment.kind,
        base_url=environment.base_url,
        auth_type=environment.auth_type,
        auth_header=environment.auth_header,
        secret_ref=environment.secret_ref,
        allow_hosts=loads(environment.allow_hosts_json, []),
        is_default=environment.is_default,
        created_at=environment.created_at,
    )


def _source_secret_id(source_id: str) -> str:
    """Return the opaque local-vault key for one connector."""

    return f"source:{source_id}"


def _source_view(source: SourceConnector) -> SourceConnectorView:
    """Serialize connector metadata without its local credential."""

    return SourceConnectorView(
        id=source.id,
        project_id=source.project_id,
        name=source.name,
        source_type=source.source_type,
        endpoint_url=source.endpoint_url,
        workspace_id=source.workspace_id,
        auth_type=source.auth_type,
        auth_header=source.auth_header,
        request_params=loads(source.config_json, {}),
        status=source.status,
        has_secret=has_secret(_source_secret_id(source.id)),
        last_sync_at=source.last_sync_at,
        created_at=source.created_at,
    )


def _knowledge_base_view(session: Session, knowledge_base: KnowledgeBase) -> KnowledgeBaseView:
    """Build a knowledge summary without loading private contents into the response."""

    document_count, size_bytes = session.execute(
        select(func.count(Document.id), func.coalesce(func.sum(Document.size_bytes), 0)).where(
            Document.knowledge_base_id == knowledge_base.id
        )
    ).one()
    return KnowledgeBaseView(
        id=knowledge_base.id,
        project_id=knowledge_base.project_id,
        name=knowledge_base.name,
        description=knowledge_base.description,
        document_count=int(document_count),
        size_bytes=int(size_bytes),
        created_at=knowledge_base.created_at,
    )


LLM_SECRET_ID = "llm:default:api_key"


def _llm_view(config: LlmConfiguration | None) -> LlmConfigurationView:
    """Return global model settings and only a masked key indicator."""

    return LlmConfigurationView(
        provider=config.provider if config else "openai",
        model=config.model if config else "",
        base_url=config.base_url if config else "",
        enabled=config.enabled if config else False,
        has_api_key=has_secret(LLM_SECRET_ID),
        api_key_masked=mask_secret(LLM_SECRET_ID),
        updated_at=config.updated_at if config else None,
    )


@router.get("/health")
def health() -> dict[str, str]:
    """Return service readiness."""

    return {"status": "ok"}


@router.get("/projects", response_model=list[ProjectView])
def list_projects(session: SessionDep) -> list[Project]:
    """List active projects."""

    return list(session.scalars(select(Project).where(Project.archived.is_(False))).all())


@router.post("/projects", response_model=ProjectView, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, session: SessionDep) -> Project:
    """Create a uniquely identified project."""

    project = Project(id=new_id("proj"), **payload.model_dump())
    session.add(project)
    session.add(
        Environment(
            id=new_id("env"),
            project_id=project.id,
            name=f"{payload.default_environment.title()} 环境",
            kind=payload.default_environment,
            is_default=True,
        )
    )
    session.commit()
    return project


@router.patch("/projects/{project_id}", response_model=ProjectView)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    session: SessionDep,
) -> Project:
    """Edit or archive a project without overwriting its historical assets."""

    project = _project_or_404(session, project_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(project, field, value)
    session.commit()
    return project


@router.get("/projects/{project_id}/environments", response_model=list[EnvironmentView])
def list_environments(project_id: str, session: SessionDep) -> list[EnvironmentView]:
    """List reusable execution environments for a project."""

    _project_or_404(session, project_id)
    rows = session.scalars(
        select(Environment)
        .where(Environment.project_id == project_id)
        .order_by(Environment.is_default.desc(), Environment.created_at)
    ).all()
    return [_environment_view(row) for row in rows]


@router.post(
    "/projects/{project_id}/environments",
    response_model=EnvironmentView,
    status_code=status.HTTP_201_CREATED,
)
def create_environment(
    project_id: str,
    payload: EnvironmentCreate,
    session: SessionDep,
) -> EnvironmentView:
    """Create an environment that stores only an OS secret reference."""

    _project_or_404(session, project_id)
    if payload.kind == "production" and payload.is_default:
        raise HTTPException(status_code=422, detail="production 不能设为默认环境")
    if payload.is_default:
        for current in session.scalars(
            select(Environment).where(Environment.project_id == project_id)
        ):
            current.is_default = False
    environment = Environment(
        id=new_id("env"),
        project_id=project_id,
        name=payload.name,
        kind=payload.kind,
        base_url=payload.base_url.rstrip("/"),
        auth_type=payload.auth_type,
        auth_header=payload.auth_header,
        secret_ref=payload.secret_ref,
        allow_hosts_json=dumps(payload.allow_hosts),
        is_default=payload.is_default,
    )
    session.add(environment)
    session.commit()
    return _environment_view(environment)


@router.get(
    "/projects/{project_id}/sources",
    response_model=list[SourceConnectorView],
)
def list_sources(project_id: str, session: SessionDep) -> list[SourceConnectorView]:
    """List configured TAPD and external knowledge connectors."""

    _project_or_404(session, project_id)
    rows = session.scalars(
        select(SourceConnector)
        .where(SourceConnector.project_id == project_id)
        .order_by(SourceConnector.created_at.desc())
    ).all()
    return [_source_view(row) for row in rows]


def _managed_mcp_view(item: dict[str, object]) -> dict[str, object]:
    """Return managed MCP metadata without serializing its write-only credential."""

    server_id = str(item.get("id", ""))
    return {
        **item,
        "has_secret": has_secret(f"mcp:{server_id}"),
    }


@router.get("/mcp/servers", response_model=list[McpServerConfigurationView])
def list_managed_mcp_servers() -> list[dict[str, object]]:
    """List user-managed MCP registrations stored outside the Git worktree."""

    return [_managed_mcp_view(item) for item in read_mcp_servers()]


@router.post(
    "/mcp/servers",
    response_model=McpServerConfigurationView,
    status_code=status.HTTP_201_CREATED,
)
def create_managed_mcp_server(payload: McpServerConfiguration) -> dict[str, object]:
    """Register one HTTP MCP server and optionally persist a write-only credential."""

    try:
        endpoint_url = validate_managed_mcp_url(payload.endpoint_url)
    except McpError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    now = utc_now().isoformat()
    server_id = new_id("mcp")
    item: dict[str, object] = {
        "id": server_id,
        "name": payload.name.strip(),
        "endpoint_url": endpoint_url,
        "transport": payload.transport,
        "auth_type": payload.auth_type,
        "auth_header": payload.auth_header.strip() or "Authorization",
        "enabled": payload.enabled,
        "created_at": now,
        "updated_at": now,
    }
    if payload.secret is not None and payload.auth_type != "none":
        set_secret(f"mcp:{server_id}", payload.secret.get_secret_value())
    rows = read_mcp_servers()
    rows.append(item)
    write_mcp_servers(rows)
    return _managed_mcp_view(item)


@router.put("/mcp/servers/{server_id}", response_model=McpServerConfigurationView)
def update_managed_mcp_server(
    server_id: str,
    payload: McpServerConfiguration,
) -> dict[str, object]:
    """Replace editable MCP metadata while preserving an omitted credential."""

    rows = read_mcp_servers()
    index = next((index for index, item in enumerate(rows) if item.get("id") == server_id), -1)
    if index < 0:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")
    try:
        endpoint_url = validate_managed_mcp_url(payload.endpoint_url)
    except McpError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    current = rows[index]
    updated: dict[str, object] = {
        "id": server_id,
        "name": payload.name.strip(),
        "endpoint_url": endpoint_url,
        "transport": payload.transport,
        "auth_type": payload.auth_type,
        "auth_header": payload.auth_header.strip() or "Authorization",
        "enabled": payload.enabled,
        "created_at": current.get("created_at", utc_now().isoformat()),
        "updated_at": utc_now().isoformat(),
    }
    secret_id = f"mcp:{server_id}"
    if payload.auth_type == "none":
        delete_secret(secret_id)
    elif payload.secret is not None:
        set_secret(secret_id, payload.secret.get_secret_value())
    rows[index] = updated
    write_mcp_servers(rows)
    return _managed_mcp_view(updated)


@router.delete("/mcp/servers/{server_id}")
def delete_managed_mcp_server(server_id: str) -> dict[str, bool]:
    """Delete one local MCP registration and its credential."""

    rows = read_mcp_servers()
    remaining = [item for item in rows if item.get("id") != server_id]
    if len(remaining) == len(rows):
        raise HTTPException(status_code=404, detail="MCP Server 不存在")
    write_mcp_servers(remaining)
    delete_secret(f"mcp:{server_id}")
    return {"ok": True}


@router.post("/mcp/servers/{server_id}:test", response_model=McpServerView)
def test_managed_mcp_server(server_id: str) -> dict[str, Any]:
    """Handshake with an enabled managed MCP endpoint and list sanitized capabilities."""

    item = next((row for row in read_mcp_servers() if row.get("id") == server_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")
    if item.get("enabled") is False:
        raise HTTPException(status_code=422, detail="请先启用 MCP Server 再测试连接")
    endpoint_url = str(item.get("endpoint_url", ""))
    try:
        return {"name": str(item.get("name", "MCP Server")), **inspect_server(endpoint_url, timeout=8.0)}
    except (McpError, OSError) as exc:
        return {
            "name": str(item.get("name", "MCP Server")),
            "endpoint_url": endpoint_url,
            "transport": "streamable_http",
            "connectable": False,
            "tapd_capable": False,
            "tools": [],
            "project_tool": "",
            "requirement_tool": "",
            "error": str(exc),
        }


@router.post("/mcp/tapd:discover", response_model=list[McpServerView])
def discover_tapd_mcp(payload: TapdMcpDiscover) -> list[dict[str, Any]]:
    """Discover running loopback MCP servers without reading or returning credentials."""

    try:
        return discover_local_servers(payload.endpoint_url)
    except McpError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/mcp/tapd:projects", response_model=TapdMcpProjectsView)
def tapd_mcp_projects(payload: TapdMcpProjectsRequest) -> TapdMcpProjectsView:
    """Return TAPD projects exposed by one selected local MCP server."""

    try:
        projects, project_tool, requirement_tool = list_tapd_projects(payload.endpoint_url)
    except McpError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TapdMcpProjectsView(
        projects=[{"id": project.id, "name": project.name} for project in projects],
        project_tool=project_tool,
        requirement_tool=requirement_tool,
    )


@router.post(
    "/projects/{project_id}/sources:connect-tapd-mcp",
    response_model=SourceConnectorView,
    status_code=status.HTTP_201_CREATED,
)
def connect_tapd_mcp(
    project_id: str,
    payload: TapdMcpConnect,
    session: SessionDep,
) -> SourceConnectorView:
    """Bind one selected TAPD project to this test project through local MCP."""

    _project_or_404(session, project_id)
    try:
        endpoint_url = validate_registered_mcp_url(payload.endpoint_url)
        projects, project_tool, requirement_tool = list_tapd_projects(endpoint_url)
    except McpError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    matched = next((item for item in projects if item.id == payload.tapd_project_id), None)
    if projects and matched is None:
        raise HTTPException(status_code=422, detail="所选 TAPD 项目已不存在，请重新获取项目列表")
    project_name = matched.name if matched else payload.tapd_project_name
    source = SourceConnector(
        id=new_id("src"),
        project_id=project_id,
        name=payload.name,
        source_type="tapd",
        endpoint_url=endpoint_url,
        workspace_id=payload.tapd_project_id,
        auth_type="none",
        auth_header="",
        config_json=dumps(
            {
                "transport": "mcp_streamable_http",
                "tapd_project_name": project_name,
                "project_tool": project_tool,
                "requirement_tool": requirement_tool,
            }
        ),
        status="connected",
    )
    session.add(source)
    session.commit()
    return _source_view(source)


@router.post(
    "/projects/{project_id}/sources",
    response_model=SourceConnectorView,
    status_code=status.HTTP_201_CREATED,
)
def create_source(
    project_id: str,
    payload: SourceConnectorCreate,
    session: SessionDep,
) -> SourceConnectorView:
    """Create a connector and write its credential to ignored local storage."""

    _project_or_404(session, project_id)
    sensitive_names = {"token", "key", "secret", "password", "authorization"}
    if any(
        any(marker in key.lower() for marker in sensitive_names)
        for key in payload.request_params
    ):
        raise HTTPException(status_code=422, detail="敏感参数必须填写在 Secret 字段，不能写入请求参数")
    source = SourceConnector(
        id=new_id("src"),
        project_id=project_id,
        name=payload.name,
        source_type=payload.source_type,
        endpoint_url=str(payload.endpoint_url),
        workspace_id=payload.workspace_id,
        auth_type=payload.auth_type,
        auth_header=payload.auth_header,
        config_json=dumps(payload.request_params),
    )
    session.add(source)
    if payload.secret:
        try:
            set_secret(_source_secret_id(source.id), payload.secret.get_secret_value())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return _source_view(source)


@router.post("/sources/{source_id}:sync", response_model=DocumentView)
def sync_source(source_id: str, session: SessionDep) -> DocumentView:
    """Fetch a configured source, atomize it, and persist traceable provenance."""

    source = session.get(SourceConnector, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="来源连接器不存在")
    params = loads(source.config_json, {})
    if source.source_type == "tapd" and params.get("transport") == "mcp_streamable_http":
        try:
            payload, selected_tool = fetch_tapd_requirements(
                source.endpoint_url,
                source.workspace_id,
                str(params.get("requirement_tool", "")),
            )
        except McpError as exc:
            source.status = "error"
            session.commit()
            raise HTTPException(status_code=422, detail=f"TAPD MCP 同步失败：{exc}") from exc
        params["requirement_tool"] = selected_tool
        source.config_json = dumps(params)
        text = external_payload_to_text(payload)
        raw_content = (
            dumps(payload).encode("utf-8")
            if not isinstance(payload, str)
            else payload.encode("utf-8")
        )
        source_uri = f"mcp+{source.endpoint_url}#project={source.workspace_id}&tool={selected_tool}"
        return _persist_synced_source(session, source, text, raw_content, source_uri)

    host = urlparse(source.endpoint_url).hostname
    try:
        validate_target(source.endpoint_url, [host] if host else [])
    except UnsafeTargetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    secret = get_secret(_source_secret_id(source.id))
    if source.auth_type != "none" and not secret:
        raise HTTPException(status_code=409, detail="该来源尚未配置本地 Secret")
    headers: dict[str, str] = {"Accept": "application/json, text/plain"}
    if source.auth_type == "bearer" and secret:
        headers[source.auth_header] = f"Bearer {secret}"
    elif source.auth_type == "api_key" and secret:
        headers[source.auth_header] = secret
    elif source.auth_type == "basic" and secret:
        encoded = b64encode(secret.encode("utf-8")).decode("ascii")
        headers[source.auth_header] = f"Basic {encoded}"

    if source.workspace_id and "workspace_id" not in params:
        params["workspace_id"] = source.workspace_id
    try:
        response = httpx.get(
            source.endpoint_url,
            headers=headers,
            params=params,
            timeout=20.0,
            follow_redirects=False,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        source.status = "error"
        session.commit()
        raise HTTPException(status_code=422, detail=f"来源同步失败：{exc}") from exc

    try:
        payload: Any = response.json()
    except ValueError:
        payload = response.text
    text = external_payload_to_text(payload)
    return _persist_synced_source(
        session,
        source,
        text,
        response.content,
        source.endpoint_url,
    )


def _persist_synced_source(
    session: Session,
    source: SourceConnector,
    text: str,
    raw_content: bytes,
    source_uri: str,
) -> DocumentView:
    """Persist one connector result with project-scoped traceability."""

    document_name = f"{source.name}-{utc_now().strftime('%Y%m%d-%H%M%S')}.txt"
    requirements = parse_requirements(source.project_id, document_name, text)
    for requirement in requirements:
        requirement.source = f"{source.source_type}://{source.id}/{requirement.source}"
    document = Document(
        id=new_id("doc"),
        project_id=source.project_id,
        name=document_name,
        kind="requirement",
        version=1,
        checksum=checksum(raw_content),
        content=text,
        issues_json=dumps([] if requirements else ["同步成功，但未识别出可测试需求"]),
        source_type=source.source_type,
        source_uri=source_uri,
        size_bytes=len(raw_content),
    )
    source.status = "synced"
    source.last_sync_at = utc_now()
    session.add(document)
    session.add_all(requirements)
    session.commit()
    return _document_view(document)


@router.get(
    "/projects/{project_id}/knowledge-bases",
    response_model=list[KnowledgeBaseView],
)
def list_knowledge_bases(project_id: str, session: SessionDep) -> list[KnowledgeBaseView]:
    """List project-private component knowledge bases."""

    _project_or_404(session, project_id)
    rows = session.scalars(
        select(KnowledgeBase)
        .where(KnowledgeBase.project_id == project_id)
        .order_by(KnowledgeBase.created_at.desc())
    ).all()
    return [_knowledge_base_view(session, row) for row in rows]


@router.post(
    "/projects/{project_id}/knowledge-bases",
    response_model=KnowledgeBaseView,
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge_base(
    project_id: str,
    payload: KnowledgeBaseCreate,
    session: SessionDep,
) -> KnowledgeBaseView:
    """Create an isolated local file knowledge base."""

    _project_or_404(session, project_id)
    knowledge_base = KnowledgeBase(
        id=new_id("kb"),
        project_id=project_id,
        name=payload.name,
        description=payload.description,
    )
    session.add(knowledge_base)
    session.commit()
    return _knowledge_base_view(session, knowledge_base)


@router.post("/knowledge-bases/{knowledge_base_id}/documents", response_model=DocumentView)
async def upload_knowledge_document(
    knowledge_base_id: str,
    session: SessionDep,
    file: UploadFile = File(...),
) -> DocumentView:
    """Store a component knowledge file outside the Git working tree."""

    knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
    if not knowledge_base:
        raise HTTPException(status_code=404, detail="知识库不存在")
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="知识文件超过 20 MB 默认上限")
    filename = file.filename or "knowledge.txt"
    try:
        text = extract_text(filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    document_id = new_id("kbdoc")
    local_path = store_knowledge_file(
        knowledge_base.project_id,
        knowledge_base.id,
        document_id,
        filename,
        content,
    )
    document = Document(
        id=document_id,
        project_id=knowledge_base.project_id,
        name=filename,
        kind="knowledge",
        version=1,
        checksum=checksum(content),
        content=text,
        source_type="component_knowledge",
        source_uri=f"knowledge://{knowledge_base.id}/{filename}",
        knowledge_base_id=knowledge_base.id,
        local_path=local_path,
        size_bytes=len(content),
    )
    session.add(document)
    session.commit()
    return _document_view(document)


@router.post("/knowledge-bases/{knowledge_base_id}:extract-requirements")
def extract_knowledge_requirements(
    knowledge_base_id: str,
    session: SessionDep,
) -> dict[str, int]:
    """Promote selected private knowledge content into traceable requirements."""

    knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
    if not knowledge_base:
        raise HTTPException(status_code=404, detail="知识库不存在")
    documents = list(
        session.scalars(
            select(Document).where(Document.knowledge_base_id == knowledge_base_id)
        ).all()
    )
    if not documents:
        raise HTTPException(status_code=409, detail="请先上传知识文件")
    requirements: list[Requirement] = []
    for document in documents:
        parsed = parse_requirements(knowledge_base.project_id, document.name, document.content)
        for requirement in parsed:
            requirement.source = f"knowledge://{knowledge_base.id}/{requirement.source}"
        requirements.extend(parsed)
    session.add_all(requirements)
    session.commit()
    return {"documents": len(documents), "requirements": len(requirements)}


@router.get(
    "/knowledge-bases/{knowledge_base_id}/search",
    response_model=list[KnowledgeSearchResult],
)
def search_knowledge_base(
    knowledge_base_id: str,
    q: str,
    session: SessionDep,
) -> list[dict[str, Any]]:
    """Search only local parsed content for one component knowledge base."""

    if not session.get(KnowledgeBase, knowledge_base_id):
        raise HTTPException(status_code=404, detail="知识库不存在")
    if not q.strip():
        raise HTTPException(status_code=422, detail="搜索词不能为空")
    documents = list(
        session.scalars(select(Document).where(Document.knowledge_base_id == knowledge_base_id)).all()
    )
    return search_knowledge_documents(documents, q)


@router.get("/settings/llm", response_model=LlmConfigurationView)
def get_llm_configuration(session: SessionDep) -> LlmConfigurationView:
    """Return global LLM configuration without exposing the API key."""

    return _llm_view(session.get(LlmConfiguration, "default"))


@router.put("/settings/llm", response_model=LlmConfigurationView)
def update_llm_configuration(
    payload: LlmConfigurationUpdate,
    session: SessionDep,
) -> LlmConfigurationView:
    """Save model settings and keep the write-only API key in local storage."""

    config = session.get(LlmConfiguration, "default")
    if not config:
        config = LlmConfiguration(id="default")
        session.add(config)
    config.provider = payload.provider
    config.model = payload.model
    config.base_url = payload.base_url.rstrip("/")
    config.enabled = payload.enabled
    if payload.clear_api_key:
        delete_secret(LLM_SECRET_ID)
    if payload.api_key:
        try:
            set_secret(LLM_SECRET_ID, payload.api_key.get_secret_value())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return _llm_view(config)


@router.post("/settings/llm:test")
def test_llm_configuration(session: SessionDep) -> dict[str, Any]:
    """Verify the stored credential against a provider's model endpoint."""

    config = session.get(LlmConfiguration, "default")
    secret = get_secret(LLM_SECRET_ID)
    if not config or not config.enabled or not secret:
        raise HTTPException(status_code=409, detail="请先启用 LLM 并保存 API Key")
    defaults = {
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
    }
    base_url = config.base_url or defaults.get(config.provider, "")
    if not base_url:
        raise HTTPException(status_code=422, detail="当前 Provider 必须配置 Base URL")
    host = urlparse(base_url).hostname
    try:
        safe_base_url = validate_target(base_url, [host] if host else [])
    except UnsafeTargetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    headers = {"Authorization": f"Bearer {secret}"}
    if config.provider == "anthropic":
        headers = {"x-api-key": secret, "anthropic-version": "2023-06-01"}
    try:
        response = httpx.get(
            f"{safe_base_url}/models",
            headers=headers,
            timeout=15.0,
            follow_redirects=False,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=422, detail=f"LLM 连接测试失败：{exc}") from exc
    return {"ok": True, "provider": config.provider, "model": config.model}


@router.get("/projects/{project_id}/dashboard", response_model=DashboardView)
def project_dashboard(project_id: str, session: SessionDep) -> dict[str, Any]:
    """Return the aggregated primary work surface."""

    project = _project_or_404(session, project_id)
    requirements = list(
        session.scalars(select(Requirement).where(Requirement.project_id == project_id)).all()
    )
    operations = list(
        session.scalars(select(ApiOperation).where(ApiOperation.project_id == project_id)).all()
    )
    scenarios = list(
        session.scalars(
            select(Scenario)
            .where(Scenario.project_id == project_id)
            .order_by(Scenario.updated_at.desc())
        ).all()
    )
    runs = list(
        session.scalars(
            select(TestRun)
            .join(Scenario)
            .where(Scenario.project_id == project_id)
            .order_by(TestRun.started_at.desc())
            .limit(8)
        ).all()
    )
    covered_requirement_ids = {
        reference.get("id")
        for scenario in scenarios
        for reference in loads(scenario.ir_json, {}).get("requirement_refs", [])
    }
    passed_runs = sum(item.status == "passed" for item in runs)
    used_operation_ids = {
        step.get("operation_id")
        for scenario in scenarios
        for step in loads(scenario.ir_json, {}).get("steps", [])
    }
    requirement_coverage = (
        round(len(covered_requirement_ids) / len(requirements) * 100) if requirements else 0
    )
    api_coverage = (
        round(len(used_operation_ids) / len(operations) * 100) if operations else 0
    )
    scenario_pass_rate = round(passed_runs / len(runs) * 100) if runs else 0
    tag_operations: dict[str, set[str]] = {}
    for operation in operations:
        tags = loads(operation.tags_json, []) or ["未分类"]
        for tag in tags:
            tag_operations.setdefault(str(tag), set()).add(operation.operation_id)
    coverage: list[dict[str, Any]] = []
    for tag, operation_ids in sorted(tag_operations.items())[:8]:
        mapped_requirement_ids = {
            requirement.requirement_id
            for requirement in requirements
            if any(
                candidate.get("operation_id") in operation_ids
                for candidate in loads(requirement.mapped_operations_json, [])
            )
        }
        coverage.append(
            {
                "module": tag,
                "requirements": round(
                    len(mapped_requirement_ids & covered_requirement_ids)
                    / len(mapped_requirement_ids)
                    * 100
                )
                if mapped_requirement_ids
                else 0,
                "api": round(len(operation_ids & used_operation_ids) / len(operation_ids) * 100),
            }
        )
    scenario_names = {scenario.id: scenario.name for scenario in scenarios}
    run_views = []
    for run in runs:
        data = run_to_dict(run, scenario_names.get(run.scenario_id, run.scenario_id))
        display_name = data["result"].get("display_name")
        if display_name:
            data["scenario_name"] = display_name
        run_views.append(data)
    featured = scenarios[0] if scenarios else None
    pending_requirement_count = sum(item.status == "pending" for item in requirements)
    pending_scenario_count = sum(item.status == "draft" for item in scenarios)
    metrics = {
        "requirement_coverage": requirement_coverage,
        "api_coverage": api_coverage,
        "scenario_pass_rate": scenario_pass_rate,
        "pending_reviews": pending_requirement_count + pending_scenario_count,
    }
    low_readiness_count = sum(item.readiness < 80 for item in operations)
    ambiguity_count = sum(bool(loads(item.ambiguities_json, [])) for item in requirements)
    validation_issue_count = sum(
        bool(
            validate_ir(
                loads(item.ir_json, {}),
                {operation.operation_id for operation in operations},
            )
        )
        for item in scenarios
    )
    warnings = []
    if low_readiness_count:
        warnings.append(
            {
                "severity": "high",
                "title": "API 就绪度预警",
                "message": f"{low_readiness_count} 个 Operation 就绪度低于 80，请补充 operationId、示例或响应 Schema。",
            }
        )
    if validation_issue_count:
        warnings.append(
            {
                "severity": "high",
                "title": "场景静态校验失败",
                "message": f"{validation_issue_count} 个场景存在引用、变量或清理策略问题。",
            }
        )
    return {
        "project": project,
        "metrics": metrics,
        "coverage": coverage,
        "recent_runs": run_views,
        "pending_reviews": [
            {"label": "待确认的原子需求", "count": pending_requirement_count},
            {"label": "包含歧义的需求", "count": ambiguity_count},
            {"label": "草稿场景待评审", "count": pending_scenario_count},
        ],
        "warnings": warnings,
        "featured_scenario": _scenario_view(session, featured) if featured else None,
    }


@router.get("/projects/{project_id}/documents", response_model=list[DocumentView])
def list_documents(project_id: str, session: SessionDep) -> list[DocumentView]:
    _project_or_404(session, project_id)
    rows = session.scalars(
        select(Document).where(Document.project_id == project_id).order_by(Document.created_at.desc())
    ).all()
    return [_document_view(row) for row in rows]


@router.post("/projects/{project_id}/documents", response_model=DocumentView)
async def upload_requirement_document(
    project_id: str,
    session: SessionDep,
    file: UploadFile = File(...),
) -> DocumentView:
    """Upload and atomize a requirement document."""

    _project_or_404(session, project_id)
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文档超过 20 MB 默认上限")
    try:
        text = extract_text(file.filename or "requirements.txt", content)
        requirements = parse_requirements(project_id, file.filename or "requirements.txt", text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    version = (
        session.scalar(
            select(func.max(Document.version)).where(
                Document.project_id == project_id,
                Document.name == (file.filename or "requirements.txt"),
            )
        )
        or 0
    ) + 1
    document = Document(
        id=new_id("doc"),
        project_id=project_id,
        name=file.filename or "requirements.txt",
        kind="requirement",
        version=version,
        checksum=checksum(content),
        content=text,
        issues_json=dumps([] if requirements else ["未识别出可测试需求"]),
        source_type="local_file",
        size_bytes=len(content),
    )
    session.add(document)
    session.add_all(requirements)
    session.commit()
    return _document_view(document)


@router.post("/projects/{project_id}/api-specs", response_model=DocumentView)
async def upload_openapi(
    project_id: str,
    session: SessionDep,
    file: UploadFile = File(...),
    spec_type: str = Form("auto"),
) -> DocumentView:
    """Upload OpenAPI, Swagger, Postman, or HAR and normalize operations."""

    _project_or_404(session, project_id)
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="API 文档超过 20 MB 默认上限")
    try:
        detected_type, operations = parse_api_document(
            project_id,
            file.filename or "api-spec.json",
            content,
            spec_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    version = (
        session.scalar(
            select(func.max(Document.version)).where(
                Document.project_id == project_id,
                Document.name == (file.filename or "api-spec.json"),
            )
        )
        or 0
    ) + 1
    low_readiness = sum(item.readiness < 80 for item in operations)
    issues = [f"{low_readiness} 个 Operation 就绪度低于 80"] if low_readiness else []
    document = Document(
        id=new_id("spec"),
        project_id=project_id,
        name=file.filename or "api-spec.json",
        kind=detected_type,
        version=version,
        checksum=checksum(content),
        content=content.decode("utf-8-sig"),
        issues_json=dumps(issues),
        source_type="local_file",
        size_bytes=len(content),
    )
    session.add(document)
    existing_ids = set(
        session.scalars(
            select(ApiOperation.operation_id).where(ApiOperation.project_id == project_id)
        ).all()
    )
    session.add_all([item for item in operations if item.operation_id not in existing_ids])
    session.commit()
    return _document_view(document)


@router.post("/projects/{project_id}/api-specs:url", response_model=DocumentView)
async def import_openapi_url(
    project_id: str,
    payload: ApiSpecUrlImport,
    session: SessionDep,
) -> DocumentView:
    """Import a supported API document from a public HTTPS URL."""

    if payload.url.scheme != "https":
        raise HTTPException(status_code=422, detail="URL 导入仅允许 HTTPS")
    host = urlparse(str(payload.url)).hostname
    try:
        validate_target(str(payload.url), [host] if host else [])
    except UnsafeTargetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        response = httpx.get(str(payload.url), timeout=10.0, follow_redirects=False)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=422, detail=f"URL 导入失败：{exc}") from exc
    upload = UploadFile(filename=str(payload.url).rsplit("/", maxsplit=1)[-1], file=BytesIO(response.content))
    view = await upload_openapi(project_id, session, upload, payload.spec_type)
    document = session.get(Document, view.id)
    if document:
        document.source_type = "api_url"
        document.source_uri = str(payload.url)
        session.commit()
        return _document_view(document)
    return view


@router.post("/projects/{project_id}/analysis")
def analyze_project(project_id: str, session: SessionDep) -> dict[str, int]:
    """Map project requirements only to normalized existing operations."""

    _project_or_404(session, project_id)
    requirements = list(session.scalars(select(Requirement).where(Requirement.project_id == project_id)).all())
    operations = list(session.scalars(select(ApiOperation).where(ApiOperation.project_id == project_id)).all())
    if not requirements or not operations:
        raise HTTPException(status_code=409, detail="请先导入需求文档和 OpenAPI")
    map_requirements(requirements, operations)
    session.commit()
    return {"requirements": len(requirements), "operations": len(operations)}


@router.get("/projects/{project_id}/requirements", response_model=list[RequirementView])
def list_requirements(project_id: str, session: SessionDep) -> list[RequirementView]:
    _project_or_404(session, project_id)
    rows = session.scalars(select(Requirement).where(Requirement.project_id == project_id)).all()
    return [_requirement_view(row) for row in rows]


@router.patch("/requirements/{requirement_id}", response_model=RequirementView)
def update_requirement(
    requirement_id: str,
    payload: RequirementUpdate,
    session: SessionDep,
) -> RequirementView:
    requirement = session.get(Requirement, requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="需求不存在")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(requirement, field, value)
    session.commit()
    return _requirement_view(requirement)


@router.get("/projects/{project_id}/operations", response_model=list[OperationView])
def list_operations(project_id: str, session: SessionDep) -> list[OperationView]:
    _project_or_404(session, project_id)
    rows = session.scalars(select(ApiOperation).where(ApiOperation.project_id == project_id)).all()
    return [_operation_view(row) for row in rows]


@router.get("/projects/{project_id}/operation-graph", response_model=OperationGraphView)
def operation_graph(project_id: str, session: SessionDep) -> OperationGraphView:
    """Return operations and evidence-backed relationships for graph exploration."""

    _project_or_404(session, project_id)
    operations = list(
        session.scalars(select(ApiOperation).where(ApiOperation.project_id == project_id)).all()
    )
    scenarios = list(
        session.scalars(select(Scenario).where(Scenario.project_id == project_id)).all()
    )
    edges = derive_operation_relationships(operations, scenarios)
    groups = sorted({
        str(tag)
        for operation in operations
        for tag in loads(operation.tags_json, [])
        if str(tag).strip()
    })
    return OperationGraphView(
        nodes=[_operation_view(operation) for operation in operations],
        edges=[OperationGraphEdge(**edge) for edge in edges],
        groups=groups,
    )


@router.post("/projects/{project_id}/scenarios:generate", response_model=ScenarioView)
def generate_scenario(
    project_id: str,
    payload: ScenarioGenerate,
    session: SessionDep,
) -> ScenarioView:
    _project_or_404(session, project_id)
    requirements = list(
        session.scalars(
            select(Requirement).where(
                Requirement.project_id == project_id,
                Requirement.id.in_(payload.requirement_ids),
            )
        ).all()
    )
    if len(requirements) != len(set(payload.requirement_ids)):
        raise HTTPException(status_code=422, detail="包含不存在或跨项目的需求")
    operations = list(
        session.scalars(
            select(ApiOperation).where(ApiOperation.project_id == project_id)
        ).all()
    )
    try:
        scenario = build_scenario(project_id, requirements, operations)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.add(scenario)
    session.commit()
    return _scenario_view(session, scenario)


@router.get("/projects/{project_id}/scenarios", response_model=list[ScenarioView])
def list_scenarios(project_id: str, session: SessionDep) -> list[ScenarioView]:
    _project_or_404(session, project_id)
    rows = session.scalars(select(Scenario).where(Scenario.project_id == project_id)).all()
    return [_scenario_view(session, row) for row in rows]


@router.patch("/scenarios/{scenario_id}", response_model=ScenarioView)
def update_scenario(
    scenario_id: str,
    payload: ScenarioUpdate,
    session: SessionDep,
) -> ScenarioView:
    scenario = _scenario_or_404(session, scenario_id)
    operation_ids = set(
        session.scalars(
            select(ApiOperation.operation_id).where(
                ApiOperation.project_id == scenario.project_id
            )
        ).all()
    )
    if payload.ir is not None:
        errors = validate_ir(payload.ir, operation_ids)
        if errors:
            raise HTTPException(status_code=422, detail={"validation_errors": errors})
        scenario.ir_json = dumps(payload.ir)
    if payload.name is not None:
        scenario.name = payload.name
    scenario.version += 1
    scenario.status = "draft"
    session.commit()
    return _scenario_view(session, scenario)


@router.post("/scenarios/{scenario_id}:approve", response_model=ScenarioView)
def approve_scenario(scenario_id: str, session: SessionDep) -> ScenarioView:
    scenario = _scenario_or_404(session, scenario_id)
    view = _scenario_view(session, scenario)
    if view.validation_errors:
        raise HTTPException(status_code=422, detail={"validation_errors": view.validation_errors})
    scenario.status = "approved"
    session.commit()
    return _scenario_view(session, scenario)


@router.post("/runs", response_model=RunView)
def create_run(payload: RunCreate, session: SessionDep) -> dict[str, Any]:
    scenario = _scenario_or_404(session, payload.scenario_id)
    environment_name = payload.environment
    base_url = payload.base_url
    allow_hosts = payload.allow_hosts
    headers: dict[str, str] = {}
    if payload.environment_id:
        environment = session.get(Environment, payload.environment_id)
        if not environment or environment.project_id != scenario.project_id:
            raise HTTPException(status_code=422, detail="环境不存在或不属于当前项目")
        environment_name = environment.kind
        base_url = environment.base_url
        allow_hosts = loads(environment.allow_hosts_json, [])
        if environment.auth_type != "none":
            secret = os.environ.get(environment.secret_ref) if environment.secret_ref else None
            if not secret:
                raise HTTPException(
                    status_code=422,
                    detail=f"环境变量 {environment.secret_ref or '(未配置)'} 未设置",
                )
            if environment.auth_type == "bearer":
                headers[environment.auth_header] = f"Bearer {secret}"
            else:
                headers[environment.auth_header] = secret
    if environment_name == "production":
        raise HTTPException(status_code=403, detail="production 默认禁止自动生成和写操作执行")
    operation_rows = session.scalars(
        select(ApiOperation).where(ApiOperation.project_id == scenario.project_id)
    ).all()
    operation_map = {item.operation_id: item for item in operation_rows}
    try:
        run_status, duration_ms, pass_rate, result = execute_scenario(
            scenario,
            operation_map,
            payload.mode,
            base_url,
            allow_hosts,
            headers,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    run = TestRun(
        id=new_id("run"),
        scenario_id=scenario.id,
        environment=environment_name,
        status=run_status,
        trigger="manual",
        duration_ms=duration_ms,
        pass_rate=pass_rate,
        result_json=dumps(result),
        finished_at=finished_now(),
    )
    session.add(run)
    session.commit()
    return run_to_dict(run, scenario.name)


@router.get("/runs/{run_id}", response_model=RunView)
def get_run(run_id: str, session: SessionDep) -> dict[str, Any]:
    run = session.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    scenario = _scenario_or_404(session, run.scenario_id)
    return run_to_dict(run, scenario.name)


@router.post("/projects/{project_id}/exports")
def export_project(project_id: str, session: SessionDep) -> StreamingResponse:
    _project_or_404(session, project_id)
    scenarios = list(
        session.scalars(
            select(Scenario).where(
                Scenario.project_id == project_id,
                Scenario.status == "approved",
            )
        ).all()
    )
    if not scenarios:
        raise HTTPException(status_code=409, detail="没有已审核场景可导出")
    archive = export_pytest(scenarios)
    headers = {"Content-Disposition": f'attachment; filename="{project_id}-pytest.zip"'}
    return StreamingResponse(BytesIO(archive), media_type="application/zip", headers=headers)
