"""HTTP API for the AI Test Tool MVP."""

from __future__ import annotations

import os
from io import BytesIO
from typing import Annotated, Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_session
from .models import ApiOperation, Document, Environment, Project, Requirement, Scenario, TestRun, new_id
from .schemas import (
    DashboardView,
    DocumentView,
    EnvironmentCreate,
    EnvironmentView,
    OpenApiUrlImport,
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
)
from .security import UnsafeTargetError, validate_target
from .services import (
    build_scenario,
    checksum,
    dumps,
    execute_scenario,
    export_pytest,
    extract_text,
    finished_now,
    loads,
    map_requirements,
    normalize_operations,
    parse_openapi,
    parse_requirements,
    run_to_dict,
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
) -> DocumentView:
    """Upload and normalize an OpenAPI 3.0/3.1 specification."""

    _project_or_404(session, project_id)
    content = await file.read()
    try:
        spec = parse_openapi(content)
        operations = normalize_operations(project_id, spec)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    version = (
        session.scalar(
            select(func.max(Document.version)).where(
                Document.project_id == project_id,
                Document.name == (file.filename or "openapi.yaml"),
            )
        )
        or 0
    ) + 1
    issues = [f"{sum(item.readiness < 80 for item in operations)} 个 Operation 就绪度低于 80"]
    document = Document(
        id=new_id("spec"),
        project_id=project_id,
        name=file.filename or "openapi.yaml",
        kind="openapi",
        version=version,
        checksum=checksum(content),
        content=content.decode("utf-8-sig"),
        issues_json=dumps(issues),
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
    payload: OpenApiUrlImport,
    session: SessionDep,
) -> DocumentView:
    """Import OpenAPI from a public HTTPS URL."""

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
    return await upload_openapi(project_id, session, upload)


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
