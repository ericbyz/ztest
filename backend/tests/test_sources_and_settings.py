"""Integration coverage for private sources, knowledge, and LLM settings."""

from fastapi.testclient import TestClient

from app import local_store
from app import api as api_module
from app.database import SessionLocal
from app.main import app
from app.mcp_client import McpProject
from app.models import LlmConfiguration, Project


def test_private_knowledge_and_llm_secret_are_local_only(tmp_path, monkeypatch) -> None:
    """Keep uploaded knowledge and API keys out of database responses and Git paths."""

    monkeypatch.setattr(local_store, "LOCAL_DATA_ROOT", tmp_path)
    monkeypatch.setattr(local_store, "SECRETS_PATH", tmp_path / "secrets.json")
    project_id = ""
    with TestClient(app) as client:
        project = client.post(
            "/api/projects",
            json={"name": "Private Context", "description": "local-only assets"},
        )
        assert project.status_code == 201
        project_id = project.json()["id"]
        knowledge_base = client.post(
            f"/api/projects/{project_id}/knowledge-bases",
            json={"name": "组件规范", "description": "私有组件文档"},
        )
        assert knowledge_base.status_code == 201
        knowledge_base_id = knowledge_base.json()["id"]

        upload = client.post(
            f"/api/knowledge-bases/{knowledge_base_id}/documents",
            files={
                "file": (
                    "component.md",
                    "REQ-900 用户必须能够导出组件测试报告。",
                    "text/markdown",
                )
            },
        )
        assert upload.status_code == 200
        assert upload.json()["source_type"] == "component_knowledge"
        assert upload.json()["knowledge_base_id"] == knowledge_base_id
        assert list((tmp_path / "knowledge" / project_id / knowledge_base_id).iterdir())

        extracted = client.post(
            f"/api/knowledge-bases/{knowledge_base_id}:extract-requirements"
        )
        assert extracted.status_code == 200
        assert extracted.json()["requirements"] == 1

        saved = client.put(
            "/api/settings/llm",
            json={
                "provider": "openai_compatible",
                "model": "internal-test-model",
                "base_url": "https://llm.example.com/v1",
                "enabled": True,
                "api_key": "local-only-sensitive-value",
            },
        )
        assert saved.status_code == 200
        response_text = saved.text
        assert "local-only-sensitive-value" not in response_text
        assert saved.json()["has_api_key"] is True
        assert saved.json()["storage"] == "local_only"
        assert "local-only-sensitive-value" in (tmp_path / "secrets.json").read_text(
            encoding="utf-8"
        )

    with SessionLocal() as session:
        if project_id:
            project_row = session.get(Project, project_id)
            if project_row:
                session.delete(project_row)
        configuration = session.get(LlmConfiguration, "default")
        if configuration:
            session.delete(configuration)
        session.commit()


def test_source_connector_never_returns_secret(tmp_path, monkeypatch) -> None:
    """Treat connector credentials as write-only values."""

    monkeypatch.setattr(local_store, "LOCAL_DATA_ROOT", tmp_path)
    monkeypatch.setattr(local_store, "SECRETS_PATH", tmp_path / "secrets.json")
    project_id = ""
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "Connector Project"})
        project_id = project.json()["id"]
        response = client.post(
            f"/api/projects/{project_id}/sources",
            json={
                "name": "TAPD Stories",
                "source_type": "tapd",
                "endpoint_url": "https://api.tapd.example/stories",
                "workspace_id": "10001",
                "auth_type": "bearer",
                "secret": "tapd-local-secret-value",
            },
        )
        assert response.status_code == 201
        assert response.json()["has_secret"] is True
        assert "tapd-local-secret-value" not in response.text
        listed = client.get(f"/api/projects/{project_id}/sources")
        assert "tapd-local-secret-value" not in listed.text

    with SessionLocal() as session:
        project_row = session.get(Project, project_id)
        if project_row:
            session.delete(project_row)
            session.commit()


def test_tapd_mcp_project_selection_and_sync(monkeypatch) -> None:
    """Bind a user-selected TAPD project and scope the MCP story read to its ID."""

    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        api_module,
        "discover_local_servers",
        lambda manual_url="": [
            {
                "name": "local-tapd",
                "endpoint_url": "http://127.0.0.1:3333/mcp",
                "transport": "streamable_http",
                "connectable": True,
                "tapd_capable": True,
                "tools": ["list_workspaces", "list_stories"],
                "project_tool": "list_workspaces",
                "requirement_tool": "list_stories",
                "error": "",
            }
        ],
    )
    monkeypatch.setattr(
        api_module,
        "list_tapd_projects",
        lambda endpoint_url: (
            [McpProject(id="10001", name="支付平台"), McpProject(id="10002", name="订单中心")],
            "list_workspaces",
            "list_stories",
        ),
    )

    def fake_fetch(endpoint_url: str, project_id: str, tool_name: str):
        calls.append((project_id, tool_name))
        return {"stories": [{"id": "REQ-301", "title": "结算成功后应生成账单"}]}, "list_stories"

    monkeypatch.setattr(api_module, "fetch_tapd_requirements", fake_fetch)
    project_id = ""
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "MCP TAPD Project"})
        project_id = project.json()["id"]
        discovery = client.post("/api/mcp/tapd:discover", json={})
        assert discovery.status_code == 200
        assert discovery.json()[0]["tapd_capable"] is True
        projects = client.post(
            "/api/mcp/tapd:projects",
            json={"endpoint_url": "http://127.0.0.1:3333/mcp"},
        )
        assert [item["name"] for item in projects.json()["projects"]] == ["支付平台", "订单中心"]
        connected = client.post(
            f"/api/projects/{project_id}/sources:connect-tapd-mcp",
            json={
                "endpoint_url": "http://127.0.0.1:3333/mcp",
                "tapd_project_id": "10002",
                "tapd_project_name": "订单中心",
                "name": "订单 TAPD",
            },
        )
        assert connected.status_code == 201
        connector = connected.json()
        assert connector["workspace_id"] == "10002"
        assert connector["request_params"]["transport"] == "mcp_streamable_http"
        assert connector["has_secret"] is False
        synced = client.post(f"/api/sources/{connector['id']}:sync")
        assert synced.status_code == 200
        assert synced.json()["source_uri"].startswith("mcp+http://127.0.0.1:3333/mcp#project=10002")
        assert calls == [("10002", "list_stories")]

    with SessionLocal() as session:
        project_row = session.get(Project, project_id)
        if project_row:
            session.delete(project_row)
            session.commit()
