"""Minimal MCP client for loopback and locally registered HTTP servers.

The application deliberately supports only the Streamable HTTP transport here.
TAPD credentials remain owned by the MCP registration and never enter the database.
"""

from __future__ import annotations

import json
import os
import socket
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


PROTOCOL_VERSION = "2025-03-26"
DEFAULT_DISCOVERY_URLS = (
    "http://127.0.0.1:3000/mcp",
    "http://127.0.0.1:3333/mcp",
    "http://127.0.0.1:8001/mcp",
    "http://127.0.0.1:8080/mcp",
)
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
READ_WORDS = ("list", "get", "search", "query", "read", "fetch", "查询", "获取", "列表")
WRITE_WORDS = ("create", "update", "delete", "remove", "write", "创建", "更新", "删除")
PROJECT_WORDS = ("workspace", "project", "space", "工作空间", "项目")
REQUIREMENT_WORDS = ("story", "stories", "requirement", "需求", "故事")


class McpError(ValueError):
    """Raised when a local MCP server cannot complete a safe operation."""


@dataclass(frozen=True)
class McpTool:
    """Public tool metadata needed for selection and invocation."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class McpProject:
    """A TAPD project/workspace returned by a local MCP tool."""

    id: str
    name: str


@dataclass(frozen=True)
class McpServerConfig:
    """Sanitized identity plus in-memory headers from a trusted local registration."""

    name: str
    url: str
    headers: dict[str, str]


def _validate_http_mcp_url(url: str, *, allow_remote: bool) -> str:
    """Validate URL shape, optionally allowing HTTPS targets from trusted config."""

    normalized = url.strip().rstrip("/") or url.strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise McpError("MCP 地址必须使用 http:// 或 https://")
    hostname = (parsed.hostname or "").lower()
    if hostname not in LOOPBACK_HOSTS and (not allow_remote or parsed.scheme != "https"):
        raise McpError("手工 MCP 地址仅允许本机回环地址；远程地址必须来自本机 MCP 配置")
    if parsed.username or parsed.password:
        raise McpError("MCP 地址不能包含用户名或密码")
    try:
        port = parsed.port
    except ValueError as exc:
        raise McpError("MCP 端口无效") from exc
    if port is not None and not 1 <= port <= 65535:
        raise McpError("MCP 端口无效")
    if parsed.query or parsed.fragment:
        raise McpError("MCP 地址不能包含查询参数或片段")
    return normalized


def validate_local_mcp_url(url: str) -> str:
    """Accept an explicit loopback HTTP endpoint and reject all remote targets."""

    return _validate_http_mcp_url(url, allow_remote=False)


def validate_registered_mcp_url(url: str) -> str:
    """Allow loopback URLs or an exact HTTPS URL from a local MCP registration."""

    try:
        return validate_local_mcp_url(url)
    except McpError as local_error:
        normalized = _validate_http_mcp_url(url, allow_remote=True)
        if any(server.url == normalized for server in _config_candidates()[0]):
            return normalized
        raise local_error


def _registered_headers(endpoint_url: str) -> dict[str, str]:
    """Resolve private headers at call time without serializing or persisting them."""

    reserved = {"accept", "content-type", "mcp-session-id"}
    for server in _config_candidates()[0]:
        if server.url == endpoint_url:
            return {
                key: value
                for key, value in server.headers.items()
                if key.lower() not in reserved
            }
    return {}


def _decode_response(response: httpx.Response) -> dict[str, Any]:
    if not response.content:
        return {}
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        events: list[dict[str, Any]] = []
        for line in response.text.splitlines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data and data != "[DONE]":
                parsed = json.loads(data)
                if isinstance(parsed, dict):
                    events.append(parsed)
        if not events:
            raise McpError("MCP Server 返回了空的 SSE 响应")
        return events[-1]
    parsed = response.json()
    if not isinstance(parsed, dict):
        raise McpError("MCP Server 返回格式不是 JSON-RPC 对象")
    return parsed


class StreamableHttpMcpClient:
    """Small synchronous JSON-RPC client for a trusted Streamable HTTP server."""

    def __init__(
        self,
        endpoint_url: str,
        *,
        timeout: float = 8.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.endpoint_url = validate_registered_mcp_url(endpoint_url)
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            **_registered_headers(self.endpoint_url),
        }
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            transport=transport,
            headers=headers,
        )
        self._session_id = ""
        self._request_id = 0

    def __enter__(self) -> StreamableHttpMcpClient:
        self.initialize()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _post(self, payload: dict[str, Any], *, notification: bool = False) -> dict[str, Any]:
        headers = {"Mcp-Session-Id": self._session_id} if self._session_id else {}
        try:
            response = self._client.post(self.endpoint_url, json=payload, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise McpError(f"MCP Server 返回 HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise McpError(f"无法连接 MCP Server：{exc.__class__.__name__}") from exc
        if response.headers.get("Mcp-Session-Id"):
            self._session_id = response.headers["Mcp-Session-Id"]
        if notification or response.status_code == 202:
            return {}
        try:
            message = _decode_response(response)
        except (ValueError, json.JSONDecodeError) as exc:
            raise McpError("MCP Server 返回了无法解析的响应") from exc
        if message.get("error"):
            error = message["error"]
            detail = error.get("message", str(error)) if isinstance(error, dict) else str(error)
            raise McpError(f"MCP 调用失败：{detail}")
        result = message.get("result", {})
        return result if isinstance(result, dict) else {"value": result}

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._request_id += 1
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        return self._post(payload)

    def initialize(self) -> dict[str, Any]:
        result = self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "ai-test-tool", "version": "1.0.0"},
            },
        )
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, notification=True)
        return result

    def list_tools(self) -> list[McpTool]:
        tools = self._request("tools/list").get("tools", [])
        return [
            McpTool(
                name=str(item.get("name", "")),
                description=str(item.get("description", "")),
                input_schema=(
                    item.get("inputSchema", {})
                    if isinstance(item.get("inputSchema"), dict)
                    else {}
                ),
            )
            for item in tools
            if isinstance(item, dict) and item.get("name")
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._request("tools/call", {"name": name, "arguments": arguments})


def _tool_text(tool: McpTool) -> str:
    return f"{tool.name} {tool.description}".lower()


def _read_score(text: str) -> int:
    read_score = sum(2 for word in READ_WORDS if word in text)
    write_score = sum(6 for word in WRITE_WORDS if word in text)
    return read_score - write_score


def choose_project_tool(tools: list[McpTool]) -> McpTool | None:
    """Select a read-only TAPD workspace/project listing tool by semantics."""

    candidates: list[tuple[int, McpTool]] = []
    for tool in tools:
        text = _tool_text(tool)
        if any(word in text for word in WRITE_WORDS):
            continue
        if not any(word in text for word in PROJECT_WORDS):
            continue
        if any(word in text for word in REQUIREMENT_WORDS):
            continue
        score = _read_score(text) + (4 if "tapd" in text else 0)
        candidates.append((score, tool))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def choose_requirement_tool(tools: list[McpTool]) -> McpTool | None:
    """Select a read-only TAPD story/requirement tool by description and schema."""

    candidates: list[tuple[int, McpTool]] = []
    for tool in tools:
        text = _tool_text(tool)
        if any(word in text for word in WRITE_WORDS):
            continue
        if not any(word in text for word in REQUIREMENT_WORDS):
            continue
        score = _read_score(text) + (4 if "tapd" in text else 0)
        properties = tool.input_schema.get("properties", {})
        if isinstance(properties, dict) and any(
            key in properties for key in ("workspace_id", "workspace", "project_id")
        ):
            score += 5
        candidates.append((score, tool))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _tool_arguments(tool: McpTool, project_id: str = "") -> dict[str, Any]:
    schema = tool.input_schema
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    properties = properties if isinstance(properties, dict) else {}
    arguments: dict[str, Any] = {}
    if project_id:
        project_argument = ""
        for key in (
            "workspace_id",
            "workspace",
            "project_id",
            "workspaceId",
            "projectId",
            "workspace_ids",
            "project_ids",
        ):
            if key in properties:
                project_argument = key
                property_schema = properties.get(key, {})
                is_array = (
                    isinstance(property_schema, dict) and property_schema.get("type") == "array"
                )
                arguments[key] = [project_id] if is_array else project_id
                break
        if not project_argument:
            raise McpError("TAPD 需求工具未声明项目参数，无法保证按所选项目隔离同步")
    for key in ("page_size", "pageSize", "limit", "per_page"):
        if key in properties:
            arguments[key] = 100
            break
    required = schema.get("required", []) if isinstance(schema, dict) else []
    missing = [key for key in required if key not in arguments]
    if missing:
        raise McpError(f"MCP 工具还需要参数：{', '.join(missing)}")
    return arguments


def _tool_payload(result: dict[str, Any]) -> Any:
    structured = result.get("structuredContent")
    if structured is not None:
        return structured
    content = result.get("content", [])
    blocks: list[Any] = []
    for item in content if isinstance(content, list) else []:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = str(item.get("text", ""))
        try:
            blocks.append(json.loads(text))
        except json.JSONDecodeError:
            blocks.append(text)
    if len(blocks) == 1:
        return blocks[0]
    return blocks


def _project_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        records: list[dict[str, Any]] = []
        for item in value:
            records.extend(_project_records(item))
        return records
    if not isinstance(value, dict):
        return []
    id_keys = ("workspace_id", "project_id", "workspaceId", "projectId", "id")
    name_keys = ("workspace_name", "project_name", "workspaceName", "projectName", "name", "title")
    if any(key in value for key in id_keys) and any(key in value for key in name_keys):
        return [value]
    records = []
    for child in value.values():
        if isinstance(child, (dict, list)):
            records.extend(_project_records(child))
    return records


def parse_projects(payload: Any) -> list[McpProject]:
    """Normalize common MCP/TAPD workspace response shapes."""

    projects: list[McpProject] = []
    seen: set[str] = set()
    for item in _project_records(payload):
        project_id = next(
            (
                str(item[key])
                for key in ("workspace_id", "project_id", "workspaceId", "projectId", "id")
                if item.get(key) is not None
            ),
            "",
        )
        name = next(
            (
                str(item[key])
                for key in (
                    "workspace_name",
                    "project_name",
                    "workspaceName",
                    "projectName",
                    "name",
                    "title",
                )
                if item.get(key)
            ),
            project_id,
        )
        if project_id and project_id not in seen:
            projects.append(McpProject(id=project_id, name=name))
            seen.add(project_id)
    return projects


def inspect_server(endpoint_url: str, *, timeout: float = 0.45) -> dict[str, Any]:
    """Handshake with one endpoint and report TAPD-capable read tools."""

    endpoint_url = validate_registered_mcp_url(endpoint_url)
    with StreamableHttpMcpClient(endpoint_url, timeout=timeout) as client:
        tools = client.list_tools()
    project_tool = choose_project_tool(tools)
    requirement_tool = choose_requirement_tool(tools)
    return {
        "endpoint_url": endpoint_url,
        "transport": "streamable_http",
        "connectable": True,
        "tapd_capable": requirement_tool is not None,
        "tools": [tool.name for tool in tools],
        "project_tool": project_tool.name if project_tool else "",
        "requirement_tool": requirement_tool.name if requirement_tool else "",
        "error": "" if requirement_tool else "未找到只读 TAPD 需求工具",
    }


def _config_headers(config: dict[str, Any]) -> dict[str, str]:
    """Resolve configured headers in memory; callers must never return this mapping."""

    headers: dict[str, str] = {}
    for key in ("headers", "http_headers"):
        configured = config.get(key)
        if isinstance(configured, dict):
            headers.update(
                {
                    str(name): str(value)
                    for name, value in configured.items()
                    if isinstance(value, (str, int, float))
                }
            )
    env_headers = config.get("env_http_headers")
    if isinstance(env_headers, dict):
        for name, env_name in env_headers.items():
            if isinstance(env_name, str) and os.getenv(env_name):
                headers[str(name)] = os.environ[env_name]
    bearer_env = config.get("bearer_token_env_var")
    if isinstance(bearer_env, str) and os.getenv(bearer_env):
        headers["Authorization"] = f"Bearer {os.environ[bearer_env]}"
    return headers


def _append_config_mapping(
    mapping: dict[str, Any],
    source_name: str,
    http_servers: list[McpServerConfig],
    stdio_names: list[str],
) -> None:
    """Normalize one MCP server mapping without exposing command or secret values."""

    for name, config in mapping.items():
        if not isinstance(config, dict):
            continue
        display_name = f"{source_name} · {name}"
        url = config.get("url") or config.get("endpoint_url")
        if isinstance(url, str):
            try:
                normalized = _validate_http_mcp_url(url, allow_remote=True)
            except McpError:
                continue
            http_servers.append(
                McpServerConfig(
                    name=display_name,
                    url=normalized,
                    headers=_config_headers(config),
                )
            )
        elif config.get("command"):
            stdio_names.append(display_name)


def _config_candidates() -> tuple[list[McpServerConfig], list[str]]:
    """Read trusted MCP registrations while keeping commands and secrets private."""

    repo_root = Path(__file__).resolve().parents[2]
    user_home = Path.home()
    app_data = Path(os.getenv("APPDATA", user_home / "AppData" / "Roaming"))
    json_paths = (
        (repo_root / ".mcp.json", "项目配置"),
        (repo_root / ".cursor" / "mcp.json", "项目 Cursor"),
        (user_home / ".cursor" / "mcp.json", "Cursor"),
        (app_data / "Claude" / "claude_desktop_config.json", "Claude"),
        (app_data / "Code" / "User" / "mcp.json", "VS Code"),
        (app_data / "Cursor" / "User" / "mcp.json", "Cursor"),
    )
    http_servers: list[McpServerConfig] = []
    stdio_names: list[str] = []
    for path, source_name in json_paths:
        if not path.is_file():
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        mappings = []
        if isinstance(document, dict):
            for key in ("mcpServers", "servers"):
                if isinstance(document.get(key), dict):
                    mappings.append(document[key])
        for mapping in mappings:
            _append_config_mapping(mapping, source_name, http_servers, stdio_names)

    codex_config = user_home / ".codex" / "config.toml"
    if codex_config.is_file():
        try:
            document = tomllib.loads(codex_config.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            document = {}
        mapping = document.get("mcp_servers") if isinstance(document, dict) else None
        if isinstance(mapping, dict):
            _append_config_mapping(mapping, "Codex", http_servers, stdio_names)
    return http_servers, stdio_names


def discover_local_servers(manual_url: str = "") -> list[dict[str, Any]]:
    """Probe a small allowlist of local endpoints and known URL-based MCP configs."""

    configured, stdio_names = _config_candidates()
    candidates: list[tuple[str, str, bool]] = []
    for server in configured:
        hostname = (urlparse(server.url).hostname or "").lower()
        if hostname in LOOPBACK_HOSTS or "tapd" in server.name.lower():
            candidates.append((server.name, server.url, True))
    if manual_url:
        candidates.insert(0, ("手工地址", validate_local_mcp_url(manual_url), False))
    env_urls = [
        item.strip()
        for item in os.getenv("AI_TEST_MCP_DISCOVERY_URLS", "").split(",")
        if item.strip()
    ]
    for url in (*env_urls, *DEFAULT_DISCOVERY_URLS):
        try:
            candidates.append(("自动发现", validate_local_mcp_url(url), False))
        except McpError:
            continue
    unique: dict[str, tuple[str, bool]] = {}
    for name, url, registered in candidates:
        current = unique.get(url)
        if current is None or registered:
            unique[url] = (name, registered)

    def probe(item: tuple[str, tuple[str, bool]]) -> dict[str, Any] | None:
        url, (name, registered) = item
        try:
            parsed = urlparse(url)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            is_loopback = (parsed.hostname or "").lower() in LOOPBACK_HOSTS
            socket_timeout = 0.15 if is_loopback else 1.5
            with socket.create_connection(
                (parsed.hostname or "127.0.0.1", port),
                timeout=socket_timeout,
            ):
                pass
            return {"name": name, **inspect_server(url, timeout=0.45 if is_loopback else 6.0)}
        except (McpError, OSError) as exc:
            is_manual = bool(manual_url) and url == validate_local_mcp_url(manual_url)
            if registered or is_manual:
                return {
                    "name": name,
                    "endpoint_url": url,
                    "transport": "streamable_http",
                    "connectable": False,
                    "tapd_capable": False,
                    "tools": [],
                    "project_tool": "",
                    "requirement_tool": "",
                    "error": f"已发现配置，但连接失败：{exc}" if registered else str(exc),
                }
            return None

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(unique)))) as executor:
        results = [result for result in executor.map(probe, unique.items()) if result]
    for name in (item for item in stdio_names if "tapd" in item.lower()):
        results.append(
            {
                "name": name,
                "endpoint_url": "",
                "transport": "stdio",
                "connectable": False,
                "tapd_capable": False,
                "tools": [],
                "project_tool": "",
                "requirement_tool": "",
                "error": "已发现 stdio 配置；请让该服务暴露本机 Streamable HTTP 地址",
            }
        )
    return results


def list_tapd_projects(endpoint_url: str) -> tuple[list[McpProject], str, str]:
    """Load selectable TAPD projects and return both selected tool names."""

    with StreamableHttpMcpClient(endpoint_url) as client:
        tools = client.list_tools()
        project_tool = choose_project_tool(tools)
        requirement_tool = choose_requirement_tool(tools)
        if requirement_tool is None:
            raise McpError("本地 MCP Server 没有可用的只读 TAPD 需求工具")
        if project_tool is None:
            return [], "", requirement_tool.name
        result = client.call_tool(project_tool.name, _tool_arguments(project_tool))
    return parse_projects(_tool_payload(result)), project_tool.name, requirement_tool.name


def fetch_tapd_requirements(
    endpoint_url: str,
    project_id: str,
    tool_name: str = "",
) -> tuple[Any, str]:
    """Read requirements for exactly one selected TAPD project."""

    with StreamableHttpMcpClient(endpoint_url, timeout=20.0) as client:
        tools = client.list_tools()
        tool = next((item for item in tools if item.name == tool_name), None) if tool_name else None
        tool = tool or choose_requirement_tool(tools)
        if tool is None:
            raise McpError("本地 MCP Server 没有可用的只读 TAPD 需求工具")
        result = client.call_tool(tool.name, _tool_arguments(tool, project_id))
    return _tool_payload(result), tool.name
