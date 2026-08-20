"""Integration tests for an empty-database, multi-project workflow."""

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Project


OPENAPI = '''openapi: 3.0.3
info:
  title: Widget API
  version: 1.0.0
paths:
  /widgets:
    post:
      operationId: createWidget
      summary: 创建组件
      tags: [组件]
      responses:
        "201":
          description: created
          content:
            application/json:
              schema: {type: object}
  /widgets/{widgetId}:
    get:
      operationId: getWidget
      summary: 查询组件
      tags: [组件]
      responses:
        "200":
          description: ok
          content:
            application/json:
              schema: {type: object}
    delete:
      operationId: deleteWidget
      summary: 删除组件
      tags: [组件]
      responses:
        "200":
          description: deleted
'''.encode()


def create_generic_project(client: TestClient) -> tuple[str, str, str]:
    """Create a project and progress it from raw inputs to a valid scenario."""

    project_response = client.post(
        "/api/projects",
        json={"name": "Widget Service", "description": "Generic API project"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]
    requirement_upload = client.post(
        f"/api/projects/{project_id}/documents",
        files={"file": ("requirements.md", "US-001 用户创建组件后应可以查询并删除组件。", "text/markdown")},
    )
    assert requirement_upload.status_code == 200
    spec_upload = client.post(
        f"/api/projects/{project_id}/api-specs",
        files={"file": ("openapi.yaml", OPENAPI, "application/yaml")},
    )
    assert spec_upload.status_code == 200
    analysis = client.post(f"/api/projects/{project_id}/analysis")
    assert analysis.status_code == 200
    requirement = client.get(f"/api/projects/{project_id}/requirements").json()[0]
    scenario = client.post(
        f"/api/projects/{project_id}/scenarios:generate",
        json={"requirement_ids": [requirement["record_id"]]},
    )
    assert scenario.status_code == 200
    assert scenario.json()["validation_errors"] == []
    return project_id, requirement["record_id"], scenario.json()["id"]


def remove_project(project_id: str) -> None:
    """Remove test-owned project data after each integration workflow."""

    with SessionLocal() as session:
        project = session.get(Project, project_id)
        if project:
            session.delete(project)
            session.commit()


def test_dashboard_and_simulated_run() -> None:
    with TestClient(app) as client:
        project_id, _, scenario_id = create_generic_project(client)
        try:
            dashboard = client.get(f"/api/projects/{project_id}/dashboard")
            assert dashboard.status_code == 200
            assert dashboard.json()["metrics"]["requirement_coverage"] == 100
            run = client.post(
                "/api/runs",
                json={"scenario_id": scenario_id, "environment": "test", "mode": "simulated"},
            )
            assert run.status_code == 200
            assert run.json()["status"] == "passed"
            assert len(run.json()["result"]["steps"]) == 3
            graph = client.get(f"/api/projects/{project_id}/operation-graph")
            assert graph.status_code == 200
            assert len(graph.json()["nodes"]) == 3
            assert "组件" in graph.json()["groups"]
            assert any(edge["kind"] == "scenario_flow" for edge in graph.json()["edges"])
            assert all(edge["evidence"] for edge in graph.json()["edges"])
            assert {edge["basis"] for edge in graph.json()["edges"]} <= {
                "explicit", "inferred", "structural"
            }
        finally:
            remove_project(project_id)


def test_production_execution_is_denied() -> None:
    with TestClient(app) as client:
        project_id, _, scenario_id = create_generic_project(client)
        try:
            response = client.post(
                "/api/runs",
                json={"scenario_id": scenario_id, "environment": "production", "mode": "simulated"},
            )
            assert response.status_code == 403
        finally:
            remove_project(project_id)


def test_two_projects_can_share_business_ids() -> None:
    with TestClient(app) as client:
        first_id, _, _ = create_generic_project(client)
        second_id, _, _ = create_generic_project(client)
        try:
            first_operations = client.get(f"/api/projects/{first_id}/operations").json()
            second_operations = client.get(f"/api/projects/{second_id}/operations").json()
            assert {item["id"] for item in first_operations} == {
                item["id"] for item in second_operations
            }
            assert client.get(f"/api/projects/{first_id}/requirements").json()[0]["id"] == "US-001"
            assert client.get(f"/api/projects/{second_id}/requirements").json()[0]["id"] == "US-001"
        finally:
            remove_project(first_id)
            remove_project(second_id)
