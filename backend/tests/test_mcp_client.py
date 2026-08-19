"""Protocol and safety coverage for the loopback-only MCP client."""

from __future__ import annotations

import json

import httpx
import pytest

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
    with pytest.raises(McpError, match="回环地址"):
        validate_local_mcp_url("https://mcp.example.com/mcp")
    with pytest.raises(McpError, match="用户名或密码"):
        validate_local_mcp_url("http://user:secret@localhost:3000/mcp")


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
