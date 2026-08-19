---
name: test-design-generator
description: Generate traceable test plans, business/API test flows, scenarios, and detailed test cases from requirement documents plus API specifications, writing them to a requested local document or optionally synchronizing with TAPD through an available MCP connection. Use when users provide requirement/API sources and want structured test design assets; do not use for executing live tests unless they explicitly request execution.
---

# Test Design Generator

Turn requirement sources and API specifications into a reviewable hierarchy:

```text
Test Plan → Test Module → Test Flow → Test Scenario → Test Case
```

Every generated asset must be traceable to source requirements. API steps must reference real operations from the supplied API documentation.

## Inputs

Resolve these inputs from the user's request. Ask only for a value that is both missing and cannot be inferred safely.

- `requirements_source` — local file/directory, URL, or TAPD workspace/story/iteration reference.
- `api_source` — local file/directory or URL containing OpenAPI/Swagger, Postman Collection, cURL examples, or API documentation.
- `output_target` — local `.md`, `.yaml`, `.yml`, `.json`, `.docx`, `.xlsx` path, or an explicitly requested TAPD destination.
- `scope` — optional: `plan`, `flows`, `scenarios`, `cases`, or `all`; default `all`.
- `focus` — optional modules, requirement IDs, risks, roles, test types, or excluded endpoints.
- `tapd` — optional workspace ID, story IDs, iteration ID, read/write mode, and destination category or test plan.

Never request or store TAPD tokens in generated documents. MCP credentials belong in the user's MCP client configuration.

## Source handling

1. Verify local paths exist and report missing paths precisely.
2. Preserve requirement IDs, headings, table rows, TAPD story IDs, and other source locations.
3. Normalize API material into an operation catalog containing method, path, operation ID, parameters, request/response schemas, examples, authentication, and documented errors.
4. For TAPD, discover available MCP tools by their descriptions rather than assuming fixed tool names. Read TAPD data only when the user identifies the workspace or relevant objects.
5. If TAPD MCP is unavailable, continue with local sources when possible and provide the configuration described in [references/tapd-mcp.md](references/tapd-mcp.md).

## Generate the design

### 1. Analyze requirements

Extract atomic requirements, actors, preconditions, business rules, inputs, expected outcomes, abnormal paths, priorities, and ambiguities. Mark uncertain or contradictory statements as questions; do not silently invent business rules.

### 2. Map requirements to APIs

Map each requirement to candidate API operations using exact identifiers, resource names, schemas, examples, descriptions, and producer-consumer relationships.

- Never cite an endpoint or field absent from the supplied API sources.
- Mark a requirement as `API capability missing` or `documentation insufficient` when no valid mapping exists.
- Treat same-named fields as candidate dependencies, not proven dependencies, unless type, semantics, or examples support the binding.

### 3. Build test flows

Describe the business flow before expanding individual cases. A flow should include:

- objective and related requirement IDs;
- actor and authentication profile;
- preconditions and initial data state;
- ordered API or manual steps;
- response-to-request data bindings;
- decision and error branches;
- checkpoints and business assertions;
- cleanup or rollback steps.

Generate flows for the meaningful business lifecycle, not merely one flow per endpoint.

### 4. Expand scenarios and cases

Use relevant categories rather than mechanically generating every category:

- happy path and alternative business paths;
- required, type, enum, format, length, range, date, collection, and boundary validation;
- authentication, authorization, role and tenant isolation;
- lifecycle and state transition;
- cross-API consistency and response-to-request propagation;
- idempotency, duplicate submission, retry, timeout and concurrency where supported by the requirement;
- cleanup failure and partial-success recovery.

Each detailed case must include a stable ID, title, priority, requirement references, preconditions, test data, steps, expected results, API references, cleanup, and automation suitability.

### 5. Validate

Before writing output, check these invariants:

- every flow/scenario/case has at least one source requirement reference;
- every API reference resolves to the supplied API documentation;
- values extracted by later steps are produced earlier;
- expected results are observable and testable;
- write operations have cleanup/rollback or an explicit risk note;
- no credential or secret appears in the output;
- unresolved ambiguities are listed separately;
- duplicate cases are consolidated;
- coverage gaps are explicit rather than hidden.

## Output

Read [references/output-structure.md](references/output-structure.md) before producing the target document.

- Infer format from `output_target`.
- For Markdown, write the complete reviewable test design document.
- For YAML/JSON, use the structured model in the reference and keep IDs stable.
- For DOCX/XLSX, use the available document/spreadsheet workflow and preserve the same logical fields.
- Update an existing output file carefully; preserve unrelated user content and use the requested insertion location when given.
- If no output path is supplied, propose a path next to the requirement source or under `docs/`, then ask only if choosing a location could overwrite or materially reorganize user files.

Finish with counts for requirements, flows, scenarios, cases, mapped API operations, coverage gaps, and unresolved questions.

## TAPD integration

Read [references/tapd-mcp.md](references/tapd-mcp.md) when TAPD is requested or a TAPD reference is supplied.

- Treat TAPD as an optional input and output adapter; the generation model remains the same.
- Read mode may retrieve requirements, attachments, relationships, existing cases, iterations, tasks, and defects when supported by connected tools.
- Before any TAPD write, show a concise write preview including workspace, target objects, create/update counts, and requirement-case links.
- Write only when the user explicitly requests synchronization or creation in TAPD.
- Prefer linking generated cases to their source stories when a supported relationship tool exists.
- If the MCP exposes no suitable write tool, write a local import-ready document and state that TAPD was not modified.
- Never delete, close, transition, or bulk-update TAPD objects unless the user specifically asks for that operation.

## Boundaries

This skill designs and writes test assets. Do not call live business APIs, mutate test environments, create defects from hypothetical failures, or claim execution coverage unless the user separately requests execution and supplies an authorized target environment.

