"""Integration coverage for private sources, knowledge, and LLM settings."""

from fastapi.testclient import TestClient

from app import local_store
from app.database import SessionLocal
from app.main import app
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
