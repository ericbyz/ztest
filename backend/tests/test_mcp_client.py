"""Protocol and safety coverage for the loopback-only MCP client."""

from __future__ import annotations

import json

import httpx
import pytest

from app import mcp_client
from app.mcp_client import (
    McpError,
    McpTool,
    StreamableHttpMcpClient,
    choose_project_tool,
    choose_requirement_tool,
    parse_projects,
    validate_local_mcp_url,
)


def test_mcp_url_is_restricted_to_loopback() -> None:
    assert validate_local_mcp_url("http://127.0.0.1:3333/mcp") == "http://127.0.0.1:3333/mcp"
    assert validate_local_mcp_url("http://localhost:8001/mcp/") == "http://localhost:8001/mcp"
    with pytest.raises(McpError, match="回环地址|手工"):
        validate_local_mcp_url("https://mcp.example.com/mcp")
    with pytest.raises(McpError, match="用户名或密码"):
        validate_local_mcp_url("http://user:secret@localhost:3000/mcp")


def test_codex_toml_registration_is_discovered_without_exposing_headers(
    tmp_path, monkeypatch
) -> None:
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(
        """
[mcp_servers.tapd]
type = "http"
url = "https://registered.example.com/mcp"

[mcp_servers.tapd.http_headers]
Authorization = "private-test-header"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_client.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(mcp_client, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mcp_client, "read_mcp_servers", lambda: [])
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    servers, _ = mcp_client._config_candidates()

    assert [(server.name, server.url) for server in servers] == [
        ("Codex · tapd", "https://registered.example.com/mcp")
    ]
    assert mcp_client.validate_registered_mcp_url(
        "https://registered.example.com/mcp"
    ) == "https://registered.example.com/mcp"
    assert "private-test-header" not in repr(
        {
            "name": servers[0].name,
            "endpoint_url": servers[0].url,
            "transport": "streamable_http",
        }
    )


def test_claude_code_stdio_proxy_url_is_discovered_without_executing_command(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / ".claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "tapd-local": {
                        "command": "cmd",
                        "args": [
                            "/c",
                            "npx",
                            "-y",
                            "mcp-remote",
                            "--url",
                            "http://10.0.0.8:8111/mcp",
                            "--token",
                            "private-proxy-token",
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_client.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(mcp_client, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mcp_client, "read_mcp_servers", lambda: [])
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    servers, stdio_names = mcp_client._config_candidates()

    assert [(server.name, server.url) for server in servers] == [
        ("Claude Code · tapd-local · 代理地址", "http://10.0.0.8:8111/mcp")
    ]
    assert stdio_names == []
    assert servers[0].headers["Authorization"] == "Bearer private-proxy-token"
    assert "private-proxy-token" not in repr(
        {"name": servers[0].name, "endpoint_url": servers[0].url}
    )
    assert mcp_client.validate_registered_mcp_url("http://10.0.0.8:8111/mcp") == (
        "http://10.0.0.8:8111/mcp"
    )


def test_failed_registered_server_remains_visible(monkeypatch) -> None:
    server = mcp_client.McpServerConfig(
        name="Codex · tapd",
        url="https://registered.example.com/mcp",
        headers={"Authorization": "private-test-header"},
    )
    monkeypatch.setattr(mcp_client, "_config_candidates", lambda: ([server], []))

    class OpenSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(mcp_client.socket, "create_connection", lambda *_, **__: OpenSocket())
    monkeypatch.setattr(
        mcp_client,
        "inspect_server",
        lambda *_, **__: (_ for _ in ()).throw(McpError("HTTP 500")),
    )

    results = mcp_client.discover_local_servers()

    assert results[0]["name"] == "Codex · tapd"
    assert results[0]["connectable"] is False
    assert "已发现配置" in results[0]["error"]
    assert "private-test-header" not in repr(results)


def test_streamable_http_handshake_lists_and_calls_tools() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        if payload["method"] == "initialize":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-03-26"},
                },
                headers={"Mcp-Session-Id": "session-1"},
            )
        if payload["method"] == "notifications/initialized":
            assert request.headers["Mcp-Session-Id"] == "session-1"
            return httpx.Response(202)
        if payload["method"] == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "list_tapd_stories",
                        "description": "查询 TAPD 需求",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"workspace_id": {"type": "string"}},
                        },
                    }
                ]
            }
            event = {"jsonrpc": "2.0", "id": payload["id"], "result": result}
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=f"event: message\ndata: {json.dumps(event)}\n\n",
            )
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"content": [{"type": "text", "text": "[]"}]},
            },
        )

    with StreamableHttpMcpClient(
        "http://127.0.0.1:3333/mcp",
        transport=httpx.MockTransport(handler),
    ) as client:
        tools = client.list_tools()
        result = client.call_tool(tools[0].name, {"workspace_id": "10001"})

    assert tools[0].name == "list_tapd_stories"
    assert result["content"][0]["text"] == "[]"
    assert [item["method"] for item in requests] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
    ]


def test_tapd_tools_and_projects_are_selected_semantically() -> None:
    tools = [
        McpTool("delete_story", "删除 TAPD 需求", {}),
        McpTool("workspace_catalog", "获取 TAPD 项目列表", {}),
        McpTool(
            "story_search",
            "查询 TAPD stories",
            {"properties": {"workspace_id": {"type": "string"}}},
        ),
    ]
    assert choose_project_tool(tools).name == "workspace_catalog"
    assert choose_requirement_tool(tools).name == "story_search"
    assert choose_requirement_tool([tools[0]]) is None
    projects = parse_projects(
        {"data": [{"workspace_id": 1001, "workspace_name": "支付平台"}, {"id": "1002", "name": "订单中心"}]}
    )
    assert [(project.id, project.name) for project in projects] == [
        ("1001", "支付平台"),
        ("1002", "订单中心"),
    ]


def test_requirement_tool_prefers_entity_listing_over_count_and_metadata_tools() -> None:
    tools = [
        McpTool(
            "get_story_or_task_count",
            "获取 TAPD 需求或者任务的数量",
            {"properties": {"workspace_id": {"type": "string"}}},
        ),
        McpTool(
            "get_stories_fields_info",
            "获取 TAPD 需求字段配置",
            {"properties": {"workspace_id": {"type": "string"}}},
        ),
        McpTool(
            "get_bug",
            "获取 TAPD 需求关联的缺陷",
            {"properties": {"workspace_id": {"type": "string"}}},
        ),
        McpTool(
            "get_stories_or_tasks",
            "获取 TAPD 需求或任务；示例流程：查询后可创建",
            {"properties": {"workspace_id": {"type": "string"}}},
        ),
    ]
    assert choose_requirement_tool(tools).name == "get_stories_or_tasks"


def test_tool_payload_decodes_nested_json_strings() -> None:
    inner = {"status": 1, "data": [{"Workspace": {"id": "22616271", "name": "铁威马"}}]}

    structured = {"structuredContent": {"result": json.dumps(inner, ensure_ascii=False)}}
    projects = parse_projects(mcp_client._tool_payload(structured))
    assert [(project.id, project.name) for project in projects] == [("22616271", "铁威马")]

    wrapped = json.dumps(
        {"content": [{"type": "text", "text": json.dumps({"result": json.dumps(inner, ensure_ascii=False)}, ensure_ascii=False)}]},
        ensure_ascii=False,
    )
    projects = parse_projects(mcp_client._tool_payload(json.loads(wrapped)))
    assert projects[0].id == "22616271"


def test_fetch_requirements_replaces_metadata_tool_and_paginates(monkeypatch) -> None:
    """Migrate stale count-tool bindings and retrieve normalized Story pages."""

    calls: list[tuple[str, dict]] = []
    count_tool = McpTool(
        "get_story_or_task_count",
        "获取 TAPD 需求数量",
        {"properties": {"workspace_id": {"type": "integer"}}},
    )
    story_tool = McpTool(
        "get_stories_or_tasks",
        "获取 TAPD 需求列表",
        {
            "properties": {
                "workspace_id": {"type": "integer"},
                "options": {"type": "object"},
            }
        },
    )

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def list_tools(self):
            return [count_tool, story_tool]

        def call_tool(self, name, arguments):
            calls.append((name, arguments))
            page = arguments["options"]["page"]
            rows = {
                1: [
                    {"Story": {"id": "101", "name": "需求一", "description": "<p>必须成功</p>"}},
                    {"Story": {"id": "102", "name": "需求二", "description": "应返回结果"}},
                ],
                2: [{"Story": {"id": "103", "name": "需求三", "description": "需要审核"}}],
            }.get(page, [])
            inner = {"status": 1, "data": rows}
            return {"structuredContent": {"result": json.dumps(inner, ensure_ascii=False)}}

    monkeypatch.setattr(mcp_client, "StreamableHttpMcpClient", FakeClient)
    monkeypatch.setattr(mcp_client, "TAPD_PAGE_SIZE", 2)

    payload, selected = mcp_client.fetch_tapd_requirements(
        "http://127.0.0.1:3333/mcp", "56559367", "get_story_or_task_count"
    )

    assert selected == "get_stories_or_tasks"
    assert [item["requirement_id"] for item in payload["requirements"]] == [
        "TAPD-101", "TAPD-102", "TAPD-103"
    ]
    assert [call[1]["options"]["page"] for call in calls] == [1, 2]
    assert all(call[0] == "get_stories_or_tasks" for call in calls)
