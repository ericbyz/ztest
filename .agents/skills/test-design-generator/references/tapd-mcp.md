# TAPD MCP adapter

Use this reference only when the user supplies TAPD references, requests TAPD configuration, or asks to synchronize output to TAPD.

## Supported workflow

1. Discover a connected MCP server whose tools describe TAPD requirements/stories, iterations, tasks, test cases, relationships, comments, attachments, or defects.
2. Confirm the workspace and requested source objects.
3. Retrieve only the data needed for the requested test scope.
4. Generate the same test-design hierarchy used for local documents.
5. If writeback is requested, inspect available tools and prepare a preview.
6. Create or update only supported targets; link test cases to source requirements when the MCP supports that relation.
7. Report created/updated/skipped items and any unsupported fields.

Tool names differ across TAPD MCP implementations. Match tools by description and input schema rather than hard-coding names.

## Recommended MCP configuration

TencentCloudCommunity publishes `mcp-server-tapd`, which supports personal access tokens and TAPD API credentials. Personal tokens are preferred.

Local stdio example:

```json
{
  "mcpServers": {
    "mcp-server-tapd": {
      "command": "uvx",
      "args": ["mcp-server-tapd"],
      "env": {
        "TAPD_ACCESS_TOKEN": "${TAPD_ACCESS_TOKEN}",
        "TAPD_API_BASE_URL": "https://api.tapd.cn",
        "TAPD_BASE_URL": "https://www.tapd.cn"
      }
    }
  }
}
```

If personal tokens are unavailable, the server also accepts `TAPD_API_USER` and `TAPD_API_PASSWORD`. Keep values in the MCP client's secret/environment configuration; never commit them to the repository.

Streamable HTTP example for an already-running server:

```json
{
  "mcpServers": {
    "tapd_mcp_http": {
      "url": "http://localhost:8000/mcp/"
    }
  }
}
```

The exact configuration file location depends on the MCP client. Do not edit a user's global MCP configuration unless they explicitly ask.

## Input selectors

Prefer explicit selectors:

```yaml
tapd:
  workspace_id: "12345678"
  story_ids: ["10001", "10002"]
  iteration_id: "20001"
  include_attachments: true
  include_existing_cases: true
  mode: read-only  # read-only | preview-write | write
```

When both `story_ids` and `iteration_id` are supplied, use story IDs as the explicit scope unless the user asks for the whole iteration.

## Read behavior

- Preserve TAPD story IDs and URLs as requirement references.
- Retrieve descriptions, acceptance criteria, attachments and related stories when useful and supported.
- Inspect existing linked test cases to avoid duplicates.
- Use defects only as historical risk evidence; do not convert every historical defect into a required regression case without relevance.

## Write behavior

Before writes, present:

- workspace and destination;
- number of test plans/modules/cases to create or update;
- story-to-case relationship count;
- fields that cannot be represented in TAPD;
- duplicate policy.

Default duplicate policy: match by stable generated ID stored in the title or a dedicated/custom field when available. Do not match solely by similar natural-language titles.

If TAPD tools support test cases but not flows, store the flow summary in the case category, preconditions, description, or a local companion document without losing traceability.

Do not create defects during design generation. Defects require actual execution evidence and a separate explicit request.

## Degraded mode

If TAPD MCP is missing, disconnected, read-only, or lacks test-case tools:

1. State the missing capability precisely.
2. Generate a local Markdown/XLSX/YAML artifact suitable for review/import.
3. Do not claim TAPD synchronization succeeded.
4. Provide the relevant configuration example without exposing credentials.

