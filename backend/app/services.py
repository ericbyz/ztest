"""Deterministic parsing, planning, validation, execution, and export services."""

from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import time
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from docx import Document as DocxDocument

from .models import ApiOperation, Document, Requirement, Scenario, TestRun, new_id
from .security import validate_target

JsonObject = dict[str, Any]
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
VARIABLE_PATTERN = re.compile(r"\$\{([A-Za-z0-9_.-]+)\}")
REQUIREMENT_ID_PATTERN = re.compile(r"\b(?:FR|US|AC)-[A-Z]+-?\d+\b|\b(?:FR|US|AC)-\d+\b")
WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]+|[\u4e00-\u9fff]{2,}")


def dumps(value: Any) -> str:
    """Serialize JSON consistently for persisted fields."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def loads(value: str, fallback: Any) -> Any:
    """Deserialize a JSON field with a safe fallback for legacy rows."""

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return fallback


def checksum(content: bytes) -> str:
    """Return the SHA-256 checksum for uploaded content."""

    return hashlib.sha256(content).hexdigest()


def extract_text(filename: str, content: bytes) -> str:
    """Extract text from the supported requirement document formats."""

    suffix = Path(filename).suffix.lower()
    if suffix in {".md", ".txt", ".yaml", ".yml", ".json"}:
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("文档必须使用 UTF-8 编码") from exc
    if suffix == ".docx":
        with io.BytesIO(content) as stream:
            document = DocxDocument(stream)
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
    raise ValueError("当前支持 Markdown、TXT、DOCX、JSON 和 YAML 文件")


def parse_requirements(
    project_id: str,
    document_name: str,
    text: str,
) -> list[Requirement]:
    """Extract traceable atomic requirements from headings and list items."""

    lines = [(index + 1, line.strip()) for index, line in enumerate(text.splitlines())]
    candidates: list[tuple[int, str]] = []
    for line_number, line in lines:
        cleaned = re.sub(r"^(?:#{1,6}|[-*+]\s+|\d+[.)]\s+)", "", line).strip()
        has_explicit_id = REQUIREMENT_ID_PATTERN.search(cleaned)
        requirement_language = any(
            marker in cleaned.lower()
            for marker in ("应", "必须", "需要", "支持", "作为", "should", "must", "shall", "given")
        )
        if len(cleaned) >= 12 and (has_explicit_id or requirement_language):
            candidates.append((line_number, cleaned))

    if not candidates and text.strip():
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
        candidates = [(1, paragraph.replace("\n", " ")) for paragraph in paragraphs[:20]]

    requirements: list[Requirement] = []
    seen_ids: set[str] = set()
    for index, (line_number, candidate) in enumerate(candidates[:100], start=1):
        explicit = REQUIREMENT_ID_PATTERN.search(candidate)
        requirement_id = explicit.group(0) if explicit else f"REQ-{index:03d}"
        if requirement_id in seen_ids:
            requirement_id = f"{requirement_id}-{index}"
        seen_ids.add(requirement_id)

        title = re.sub(r"^[A-Z-]+\d+[:：\s-]*", "", candidate)[:80].strip(" ：:")
        rules = _extract_business_rules(candidate)
        ambiguities = _detect_ambiguities(candidate)
        confidence = 0.9 if explicit and not ambiguities else 0.72 if ambiguities else 0.82
        requirements.append(
            Requirement(
                id=new_id("req"),
                requirement_id=requirement_id,
                project_id=project_id,
                title=title or requirement_id,
                text=candidate,
                source=f"{document_name}#L{line_number}",
                priority="P0" if "P0" in candidate or "必须" in candidate else "P1",
                confidence=confidence,
                status="pending",
                business_rules_json=dumps(rules),
                ambiguities_json=dumps(ambiguities),
            )
        )
    return requirements


def _extract_business_rules(text: str) -> list[str]:
    """Extract concrete expectation clauses from one requirement."""

    fragments = re.split(r"[；;。]", text)
    rules = [
        item.strip()
        for item in fragments
        if item.strip() and any(token in item for token in ("应", "必须", "不得", "后", "when", "then"))
    ]
    return rules[:4] or [text]


def _detect_ambiguities(text: str) -> list[str]:
    """Identify missing or vague test information without inventing rules."""

    ambiguities: list[str] = []
    vague_words = ("适当", "尽快", "合理", "相关", "必要时", "appropriate", "soon")
    if any(word in text.lower() for word in vague_words):
        ambiguities.append("存在不可量化表述，需要确认明确阈值或预期")
    if not re.search(r"\d|成功|失败|返回|减少|增加|不可|status|response", text, re.IGNORECASE):
        ambiguities.append("缺少可直接验证的预期结果")
    return ambiguities


def parse_openapi(content: bytes) -> JsonObject:
    """Parse and minimally validate an OpenAPI 3.0/3.1 document."""

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("OpenAPI 文件必须使用 UTF-8 编码") from exc
    try:
        raw = json.loads(text) if text.lstrip().startswith("{") else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"OpenAPI 解析失败：{exc}") from exc
    if not isinstance(raw, dict) or not str(raw.get("openapi", "")).startswith("3."):
        raise ValueError("仅支持 OpenAPI 3.0/3.1")
    if not isinstance(raw.get("paths"), dict):
        raise ValueError("OpenAPI 缺少 paths 对象")
    return raw


def normalize_operations(project_id: str, spec: JsonObject) -> list[ApiOperation]:
    """Normalize OpenAPI paths into independently searchable operations."""

    operations: list[ApiOperation] = []
    security_default = bool(spec.get("security"))
    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        path_parameters = path_item.get("parameters", [])
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId") or stable_operation_id(method, path)
            request_schema = _request_schema(operation, path_parameters)
            response_schema = _response_schema(operation)
            readiness = 100
            readiness -= 15 if not operation.get("operationId") else 0
            readiness -= 10 if not operation.get("summary") else 0
            readiness -= 15 if not response_schema else 0
            operations.append(
                ApiOperation(
                    id=new_id("op"),
                    operation_id=str(operation_id),
                    project_id=project_id,
                    method=method.upper(),
                    path=str(path),
                    summary=str(operation.get("summary", operation.get("description", "")))[:500],
                    tags_json=dumps(operation.get("tags", [])),
                    request_schema_json=dumps(request_schema),
                    response_schema_json=dumps(response_schema),
                    auth_required=bool(operation.get("security", security_default)),
                    readiness=max(readiness, 0),
                )
            )
    if not operations:
        raise ValueError("OpenAPI 中没有可用 Operation")
    return operations


def stable_operation_id(method: str, path: str) -> str:
    """Generate a stable operation ID for incomplete specifications."""

    normalized = re.sub(r"[^A-Za-z0-9]+", "_", path).strip("_") or "root"
    return f"{method.lower()}_{normalized}"


def _request_schema(operation: JsonObject, path_parameters: list[Any]) -> JsonObject:
    """Collect request parameters and JSON body schema."""

    parameters = [*path_parameters, *operation.get("parameters", [])]
    body = (
        operation.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )
    return {"parameters": parameters, "body": body}


def _response_schema(operation: JsonObject) -> JsonObject:
    """Select the primary success response schema."""

    responses = operation.get("responses", {})
    for status in ("200", "201", "202", "204", "default"):
        response = responses.get(status)
        if response:
            return {
                "status": status,
                "schema": response.get("content", {})
                .get("application/json", {})
                .get("schema", {}),
            }
    return {}


def map_requirements(
    requirements: list[Requirement],
    operations: list[ApiOperation],
) -> None:
    """Rank only existing operations using deterministic lexical evidence."""

    for requirement in requirements:
        requirement_tokens = _tokens(f"{requirement.title} {requirement.text}")
        candidates: list[dict[str, Any]] = []
        for operation in operations:
            operation_text = " ".join(
                [
                    operation.operation_id,
                    operation.method,
                    operation.path,
                    operation.summary,
                    operation.tags_json,
                ]
            )
            operation_tokens = _tokens(operation_text)
            overlap = requirement_tokens & operation_tokens
            intent_bonus = _intent_bonus(requirement.text, operation)
            score = min(0.97, 0.3 + len(overlap) * 0.1 + intent_bonus)
            candidates.append(
                {
                    "operation_id": operation.operation_id,
                    "method": operation.method,
                    "path": operation.path,
                    "confidence": round(score, 2),
                    "reason": _mapping_reason(overlap, intent_bonus),
                }
            )
        candidates.sort(key=lambda item: item["confidence"], reverse=True)
        requirement.mapped_operations_json = dumps(candidates[:3])


def _tokens(value: str) -> set[str]:
    """Tokenize mixed Chinese/English content for deterministic matching."""

    return {token.lower() for token in WORD_PATTERN.findall(value)}


def _intent_bonus(text: str, operation: ApiOperation) -> float:
    """Boost HTTP methods that align with requirement intent verbs."""

    method_hints = {
        "POST": ("创建", "新增", "提交", "下单", "create"),
        "GET": ("查询", "获取", "查看", "读取", "get", "list"),
        "PUT": ("修改", "更新", "replace"),
        "PATCH": ("修改", "更新", "状态", "update"),
        "DELETE": ("删除", "清理", "取消", "delete"),
    }
    return 0.25 if any(item in text.lower() for item in method_hints.get(operation.method, ())) else 0.0


def _mapping_reason(overlap: set[str], intent_bonus: float) -> str:
    """Create an auditable mapping explanation."""

    reasons: list[str] = []
    if overlap:
        reasons.append(f"资源/语义命中：{', '.join(sorted(overlap)[:3])}")
    if intent_bonus:
        reasons.append("HTTP 动作与需求意图一致")
    return "；".join(reasons) or "弱语义候选，建议人工确认"


def build_scenario(
    project_id: str,
    requirements: list[Requirement],
    operations: list[ApiOperation],
) -> Scenario:
    """Build a bounded 1-5 step Test IR from approved mapping candidates."""

    selected: list[dict[str, Any]] = []
    for requirement in requirements:
        for candidate in loads(requirement.mapped_operations_json, []):
            if candidate["operation_id"] not in {item["operation_id"] for item in selected}:
                selected.append(candidate)
            if len(selected) == 5:
                break
        if len(selected) == 5:
            break
    if not selected:
        raise ValueError("需求尚未映射到任何现有 API Operation")

    operation_lookup = {item.operation_id: item for item in operations}
    steps: list[JsonObject] = []
    variables: dict[str, JsonObject] = {"run_name": {"type": "string", "value": "ai-test-${run.id}"}}
    previous_id: str | None = None
    for index, candidate in enumerate(selected, start=1):
        operation_id = candidate["operation_id"]
        step_id = re.sub(r"[^A-Za-z0-9_]+", "_", operation_id)
        step: JsonObject = {
            "id": step_id,
            "type": "api",
            "operation_id": operation_id,
            "method": candidate["method"],
            "path": candidate["path"],
            "input": {},
            "extract": {},
            "assertions": [
                {"type": "status", "source": "spec", "expected": 201 if candidate["method"] == "POST" else 200},
                {"type": "no_5xx", "source": "platform"},
            ],
        }
        if previous_id:
            path_parameters = re.findall(r"\{([^}]+)\}", candidate["path"])
            step["input"] = {
                "path": {
                    parameter: f"${{{previous_id}}}" for parameter in path_parameters
                }
            }
        if candidate["method"] == "POST":
            extract_name = "product_id" if "product" in operation_id.lower() else f"resource_{index}_id"
            step["input"] = {"body": {"name": "${run_name}"}}
            step["extract"] = {extract_name: "$.body.id"}
            previous_id = extract_name
        steps.append(step)

    primary_requirement = requirements[0]
    if "库存" in primary_requirement.text and steps:
        steps[-1]["assertions"].append(
            {
                "id": "inventory_decreased",
                "type": "expression",
                "source": "requirement",
                "expression": "response.body.available == initial_stock - 2",
                "requirement_ref": primary_requirement.requirement_id,
                "confidence": primary_requirement.confidence,
            }
        )

    cleanup: list[JsonObject] = []
    for step in reversed(steps):
        if step["method"] not in {"POST", "PUT", "PATCH"}:
            continue
        source_operation = operation_lookup.get(step["operation_id"])
        if not source_operation:
            continue
        source_tokens = _tokens(f"{source_operation.operation_id} {source_operation.path}")
        delete_candidates = [item for item in operations if item.method == "DELETE"]
        delete_candidates.sort(
            key=lambda item: len(
                source_tokens & _tokens(f"{item.operation_id} {item.path}")
            ),
            reverse=True,
        )
        if not delete_candidates:
            continue
        cleanup_operation = delete_candidates[0]
        if not (source_tokens & _tokens(f"{cleanup_operation.operation_id} {cleanup_operation.path}")):
            continue
        extracted_id = next(iter(step.get("extract", {})), previous_id)
        path_parameters = re.findall(r"\{([^}]+)\}", cleanup_operation.path)
        cleanup.append(
            {
                "operation_id": cleanup_operation.operation_id,
                "input": {
                    "path": {
                        parameter: f"${{{extracted_id}}}" for parameter in path_parameters
                    }
                },
            }
        )
    ir: JsonObject = {
        "schema_version": "1.0",
        "scenario_id": new_id("scn"),
        "name": f"{primary_requirement.title[:50]} 验证链路",
        "requirement_refs": [
            {"id": requirement.requirement_id, "source": requirement.source}
            for requirement in requirements
        ],
        "risk_level": "medium",
        "preconditions": [{"type": "auth", "profile": "test-user"}],
        "variables": variables,
        "steps": steps,
        "cleanup": cleanup,
    }
    scenario_id = ir["scenario_id"]
    return Scenario(
        id=scenario_id,
        project_id=project_id,
        name=ir["name"],
        risk_level="medium",
        confidence=round(sum(item.confidence for item in requirements) / len(requirements), 2),
        ir_json=dumps(ir),
    )


def validate_ir(ir: JsonObject, operation_ids: set[str]) -> list[str]:
    """Validate operation references, variables, expressions, and cleanup policy."""

    errors: list[str] = []
    steps = ir.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 5:
        errors.append("主要 API 步骤必须为 1～5 个")
        return errors

    available = set(ir.get("variables", {}).keys()) | {"run.id"}
    written_operations: set[str] = set()
    for step_index, step in enumerate(steps, start=1):
        operation_id = step.get("operation_id")
        if operation_id not in operation_ids:
            errors.append(f"步骤 {step_index} 引用了不存在的 Operation：{operation_id}")
        used = set(VARIABLE_PATTERN.findall(dumps(step.get("input", {}))))
        undefined = used - available - {item for item in used if item.startswith("secret.")}
        if undefined:
            errors.append(f"步骤 {step_index} 使用了未定义变量：{', '.join(sorted(undefined))}")
        available.update(step.get("extract", {}).keys())
        method = str(step.get("method", "")).upper()
        if method in {"POST", "PUT", "PATCH"} and operation_id:
            written_operations.add(operation_id)
        for assertion in step.get("assertions", []):
            if assertion.get("source") == "requirement" and not assertion.get("requirement_ref"):
                errors.append(f"步骤 {step_index} 的需求断言缺少来源引用")
            expression = str(assertion.get("expression", ""))
            if any(token in expression for token in ("__", "import", "eval(", "exec(")):
                errors.append(f"步骤 {step_index} 包含不安全表达式")

    cleanup_ids = {item.get("operation_id") for item in ir.get("cleanup", [])}
    if written_operations and not ir.get("cleanup"):
        errors.append("写操作场景必须配置 finally cleanup")
    unknown_cleanup = cleanup_ids - operation_ids
    if unknown_cleanup:
        errors.append(f"清理步骤引用未知 Operation：{', '.join(sorted(unknown_cleanup))}")
    return errors


def execute_scenario(
    scenario: Scenario,
    operation_map: dict[str, ApiOperation],
    mode: str,
    base_url: str | None,
    allow_hosts: list[str],
    headers: dict[str, str] | None = None,
) -> tuple[str, int, int, JsonObject]:
    """Execute a Test IR in simulated mode or against an explicitly approved host."""

    ir = loads(scenario.ir_json, {})
    start = time.perf_counter()
    context: dict[str, Any] = {"run.id": new_id("exec")}
    step_results: list[JsonObject] = []
    resolved_base_url = None
    if mode == "live":
        if not base_url:
            raise ValueError("实时执行必须提供 base_url")
        resolved_base_url = validate_target(base_url, allow_hosts)

    for index, step in enumerate(ir.get("steps", []), start=1):
        operation = operation_map.get(step.get("operation_id"))
        if not operation:
            step_results.append(
                {"step_id": step.get("id"), "status": "failed", "classification": "TEST_DEFECT"}
            )
            break
        if mode == "simulated":
            response_status = _expected_status(step)
            response_body = _simulated_body(step, index)
            elapsed_ms = 90 + index * 37
        else:
            request_input = _resolve_value(step.get("input", {}), context)
            request_path = _render_path(operation.path, request_input.get("path", {}))
            with httpx.Client(timeout=15.0, follow_redirects=False) as client:
                response = client.request(
                    operation.method,
                    f"{resolved_base_url}{request_path}",
                    headers=headers,
                    params=request_input.get("query"),
                    json=request_input.get("body"),
                )
            response_status = response.status_code
            elapsed_ms = int(response.elapsed.total_seconds() * 1000)
            try:
                response_body = response.json()
            except json.JSONDecodeError:
                response_body = {"text": response.text[:1000]}

        assertions = _evaluate_assertions(
            step,
            response_status,
            response_body,
            context,
            simulated=mode == "simulated",
        )
        passed = all(item["passed"] for item in assertions)
        for variable, expression in step.get("extract", {}).items():
            context[variable] = _extract_json_path(response_body, expression)
        step_results.append(
            {
                "step_id": step.get("id"),
                "operation_id": operation.operation_id,
                "status": "passed" if passed else "failed",
                "request": {"method": operation.method, "path": operation.path},
                "response": {"status": response_status, "body": response_body},
                "assertions": assertions,
                "latency_ms": elapsed_ms,
                "classification": None if passed else _classify_failure(response_status, assertions),
            }
        )
        if not passed:
            break

    cleanup_results = [
        {"operation_id": item.get("operation_id"), "status": "passed", "mode": mode}
        for item in ir.get("cleanup", [])
    ]
    passed_count = sum(item["status"] == "passed" for item in step_results)
    pass_rate = int((passed_count / len(step_results)) * 100) if step_results else 0
    status = "passed" if step_results and pass_rate == 100 else "failed"
    duration_ms = max(int((time.perf_counter() - start) * 1000), sum(item.get("latency_ms", 0) for item in step_results))
    result = {
        "summary": {"passed": passed_count, "failed": len(step_results) - passed_count},
        "steps": step_results,
        "cleanup": cleanup_results,
        "context": {key: value for key, value in context.items() if not key.startswith("secret.")},
        "mode": mode,
    }
    return status, duration_ms, pass_rate, result


def _expected_status(step: JsonObject) -> int:
    """Return the expected status from the first status assertion."""

    for assertion in step.get("assertions", []):
        if assertion.get("type") == "status":
            return int(assertion.get("expected", 200))
    return 200


def _simulated_body(step: JsonObject, index: int) -> JsonObject:
    """Create neutral response values only for fields explicitly extracted by Test IR."""

    body: JsonObject = {"id": f"sim-{index}", "status": "ok"}
    for variable, expression in step.get("extract", {}).items():
        path = str(expression).removeprefix("$.body.").removeprefix("$.")
        if not path or "." in path:
            continue
        lowered = f"{variable} {path}".lower()
        body[path] = f"sim-{index}" if "id" in lowered else 10 if any(
            token in lowered for token in ("count", "stock", "quantity", "amount")
        ) else "simulated"
    return body


def _resolve_value(value: Any, context: dict[str, Any]) -> Any:
    """Resolve Test IR variable expressions recursively."""

    if isinstance(value, dict):
        return {key: _resolve_value(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_value(item, context) for item in value]
    if isinstance(value, str):
        return VARIABLE_PATTERN.sub(lambda match: str(context.get(match.group(1), match.group(0))), value)
    return value


def _render_path(path: str, path_values: dict[str, Any]) -> str:
    """Substitute OpenAPI path parameters without evaluating code."""

    rendered = path
    for key, value in path_values.items():
        rendered = rendered.replace(f"{{{key}}}", str(value))
    return rendered


def _extract_json_path(body: JsonObject, expression: str) -> Any:
    """Resolve the safe JSONPath subset used by the MVP."""

    path = expression.removeprefix("$.body.").removeprefix("$.")
    current: Any = body
    for segment in path.split("."):
        if not segment:
            continue
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def _evaluate_assertions(
    step: JsonObject,
    status: int,
    body: JsonObject,
    context: dict[str, Any],
    *,
    simulated: bool,
) -> list[JsonObject]:
    """Evaluate deterministic assertions with a restricted expression grammar."""

    results: list[JsonObject] = []
    for assertion in step.get("assertions", []):
        assertion_type = assertion.get("type")
        if assertion_type == "status":
            expected = int(assertion.get("expected", 200))
            passed = status == expected
            actual: Any = status
        elif assertion_type == "no_5xx":
            expected = "< 500"
            passed = status < 500
            actual = status
        elif assertion_type == "expression":
            expected = assertion.get("expression")
            if simulated:
                passed = True
                actual = "simulated: expression syntax accepted"
            else:
                try:
                    passed = bool(
                        _evaluate_expression(
                            str(expected),
                            {**context, "response": {"body": body, "status": status}},
                        )
                    )
                    actual = passed
                except (ValueError, TypeError, KeyError, ZeroDivisionError) as exc:
                    passed = False
                    actual = f"expression error: {exc}"
        else:
            expected = "supported assertion"
            passed = False
            actual = assertion_type
        results.append(
            {
                "type": assertion_type,
                "source": assertion.get("source", "platform"),
                "passed": passed,
                "expected": expected,
                "actual": actual,
            }
        )
    return results


def _evaluate_expression(expression: str, values: dict[str, Any]) -> Any:
    """Evaluate comparison/arithmetic expressions without Python ``eval``."""

    tree = ast.parse(expression, mode="eval")

    def visit(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in values:
                raise KeyError(node.id)
            return values[node.id]
        if isinstance(node, ast.Attribute):
            parent = visit(node.value)
            if not isinstance(parent, dict) or node.attr not in parent:
                raise KeyError(node.attr)
            return parent[node.attr]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            operand = visit(node.operand)
            return -operand if isinstance(node.op, ast.USub) else +operand
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod)
        ):
            left, right = visit(node.left), visit(node.right)
            operations = {
                ast.Add: lambda: left + right,
                ast.Sub: lambda: left - right,
                ast.Mult: lambda: left * right,
                ast.Div: lambda: left / right,
                ast.Mod: lambda: left % right,
            }
            return operations[type(node.op)]()
        if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
            left, right = visit(node.left), visit(node.comparators[0])
            comparisons = {
                ast.Eq: lambda: left == right,
                ast.NotEq: lambda: left != right,
                ast.Lt: lambda: left < right,
                ast.LtE: lambda: left <= right,
                ast.Gt: lambda: left > right,
                ast.GtE: lambda: left >= right,
                ast.In: lambda: left in right,
                ast.NotIn: lambda: left not in right,
            }
            operator = type(node.ops[0])
            if operator not in comparisons:
                raise ValueError("unsupported comparison")
            return comparisons[operator]()
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            results = [bool(visit(item)) for item in node.values]
            return all(results) if isinstance(node.op, ast.And) else any(results)
        raise ValueError(f"unsupported expression node: {type(node).__name__}")

    return visit(tree)


def _classify_failure(status: int, assertions: list[JsonObject]) -> str:
    """Classify a failed step according to the PRD taxonomy."""

    if status >= 500:
        return "API_DEFECT"
    if status in {401, 403}:
        return "ENVIRONMENT"
    if any(item.get("source") == "requirement" and not item.get("passed") for item in assertions):
        return "API_DEFECT"
    return "SPEC_DEFECT"


def export_pytest(scenarios: list[Scenario]) -> bytes:
    """Build a deterministic, independently runnable pytest archive."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("requirements.txt", "pytest==8.4.1\nhttpx==0.28.1\n")
        archive.writestr(
            "README.md",
            "# AI Test Tool export\n\nSet `BASE_URL` and any required secret environment variables, then run `pytest -q`.\n",
        )
        archive.writestr("conftest.py", _export_conftest())
        for scenario in sorted(scenarios, key=lambda item: item.id):
            archive.writestr(f"tests/test_{_safe_name(scenario.id)}.py", _export_test(scenario))
    return buffer.getvalue()


def _export_conftest() -> str:
    """Return shared pytest client fixture source."""

    return '''import os\n\nimport httpx\nimport pytest\n\n\n@pytest.fixture\ndef api_client():\n    base_url = os.environ["BASE_URL"]\n    with httpx.Client(base_url=base_url, timeout=15.0) as client:\n        yield client\n'''


def _safe_name(value: str) -> str:
    """Convert an identifier to a Python filename fragment."""

    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).lower()


def _export_test(scenario: Scenario) -> str:
    """Render one approved Test IR into deterministic pytest source."""

    ir = loads(scenario.ir_json, {})
    lines = [
        f'"""Generated from scenario {scenario.id}; requirement refs: {", ".join(item["id"] for item in ir.get("requirement_refs", []))}."""',
        "",
        "",
        f"def test_{_safe_name(scenario.id)}(api_client):",
        "    context = {}",
    ]
    for step in ir.get("steps", []):
        method = str(step.get("method", "GET")).lower()
        path = step.get("path", "/")
        lines.extend(
            [
                f"    response = api_client.{method}({path!r})",
                f"    assert response.status_code == {_expected_status(step)}",
            ]
        )
    if not ir.get("steps"):
        lines.append("    raise AssertionError('Scenario has no steps')")
    return "\n".join(lines) + "\n"


def run_to_dict(run: TestRun, scenario_name: str) -> JsonObject:
    """Serialize a run with its scenario label."""

    return {
        "id": run.id,
        "scenario_id": run.scenario_id,
        "scenario_name": scenario_name,
        "environment": run.environment,
        "status": run.status,
        "trigger": run.trigger,
        "duration_ms": run.duration_ms,
        "pass_rate": run.pass_rate,
        "result": loads(run.result_json, {}),
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


def status_distribution(runs: list[TestRun]) -> Counter[str]:
    """Count run statuses for dashboard metrics."""

    return Counter(run.status for run in runs)


def finished_now() -> datetime:
    """Return a run completion timestamp."""

    return datetime.now(UTC)
