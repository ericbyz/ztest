"""Unit tests for deterministic core services and security policy."""

import pytest

from app.security import UnsafeTargetError, validate_target
from app.models import ApiOperation, Scenario
from app.services import (
    derive_operation_relationships,
    dumps,
    normalize_operations,
    parse_api_document,
    parse_openapi,
    validate_ir,
)


def valid_ir() -> dict:
    """Return a business-neutral valid Test IR fixture."""

    return {
        "schema_version": "1.0",
        "scenario_id": "SCN-001",
        "requirement_refs": [{"id": "REQ-001", "source": "requirements.md#L1"}],
        "variables": {},
        "steps": [
            {
                "id": "createResource",
                "operation_id": "createResource",
                "method": "POST",
                "input": {"body": {"name": "test"}},
                "extract": {"resource_id": "$.body.id"},
                "assertions": [
                    {"type": "status", "source": "spec", "expected": 201},
                    {
                        "type": "expression",
                        "source": "requirement",
                        "requirement_ref": "REQ-001",
                        "expression": "response.body.id == resource_id",
                    },
                ],
            }
        ],
        "cleanup": [
            {
                "operation_id": "deleteResource",
                "input": {"path": {"resourceId": "${resource_id}"}},
            }
        ],
    }


def test_openapi_normalizes_stable_operation() -> None:
    raw = b'''openapi: 3.0.3
info:
  title: Example
  version: 1.0.0
paths:
  /users/{userId}:
    get:
      summary: Get user
      responses:
        "200":
          description: ok
          content:
            application/json:
              schema:
                type: object
'''
    spec = parse_openapi(raw)
    operations = normalize_operations("project", spec)

    assert len(operations) == 1
    assert operations[0].operation_id == "get_users_userId"
    assert operations[0].method == "GET"
    assert operations[0].readiness == 85


def test_ir_has_traceable_protected_assertion() -> None:
    ir = valid_ir()
    operation_ids = {"createResource", "deleteResource"}

    assert validate_ir(ir, operation_ids) == []
    assertion = ir["steps"][-1]["assertions"][-1]
    assert assertion["source"] == "requirement"
    assert assertion["requirement_ref"] == "REQ-001"


def test_ir_rejects_unknown_operation_and_variable() -> None:
    ir = valid_ir()
    ir["steps"][0]["operation_id"] = "inventedOperation"
    ir["steps"][0]["input"] = {"body": {"id": "${missing_id}"}}

    errors = validate_ir(ir, {"deleteResource"})

    assert any("不存在" in error for error in errors)
    assert any("未定义变量" in error for error in errors)


def test_network_policy_blocks_loopback_even_when_allowlisted() -> None:
    with pytest.raises(UnsafeTargetError, match="受保护网段"):
        validate_target("http://127.0.0.1:9000", ["127.0.0.1"])


def test_postman_and_har_are_normalized() -> None:
    """Support common non-OpenAPI API asset formats."""

    postman = b'''{
      "info": {"name": "Widgets", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
      "item": [{"name": "List widgets", "request": {"method": "GET", "url": "https://api.example.com/widgets"}}]
    }'''
    postman_kind, postman_operations = parse_api_document(
        "project", "widgets.postman_collection.json", postman
    )
    assert postman_kind == "postman"
    assert postman_operations[0].path == "/widgets"

    har = b'''{
      "log": {"version": "1.2", "entries": [
        {"request": {"method": "POST", "url": "https://api.example.com/widgets", "headers": []},
         "response": {"status": 201}}
      ]}
    }'''
    har_kind, har_operations = parse_api_document("project", "capture.har", har)
    assert har_kind == "har"
    assert har_operations[0].method == "POST"
    assert har_operations[0].response_schema_json == '{"schema": {}, "status": "201"}'


def test_operation_relationships_are_traceable_and_deterministic() -> None:
    """Only create graph edges that carry concrete scenario, schema, or resource evidence."""

    create = ApiOperation(
        id="op_create",
        operation_id="createWidget",
        project_id="project",
        method="POST",
        path="/widgets",
        tags_json=dumps(["widgets"]),
        request_schema_json=dumps({"body": {"properties": {"title": {"type": "string"}}}}),
        response_schema_json=dumps({"schema": {"properties": {"widget_id": {"type": "string"}}}}),
    )
    get = ApiOperation(
        id="op_get",
        operation_id="getWidget",
        project_id="project",
        method="GET",
        path="/widgets/{widget_id}",
        tags_json=dumps(["widgets"]),
        request_schema_json=dumps({"parameters": [{"name": "widget_id", "in": "path"}]}),
        response_schema_json=dumps({"schema": {"properties": {"widget_id": {"type": "string"}}}}),
    )
    remove = ApiOperation(
        id="op_delete",
        operation_id="deleteWidget",
        project_id="project",
        method="DELETE",
        path="/widgets/{widget_id}",
        tags_json=dumps(["widgets"]),
        request_schema_json=dumps({"parameters": [{"name": "widget_id", "in": "path"}]}),
        response_schema_json=dumps({}),
    )
    scenario = Scenario(
        id="scenario",
        project_id="project",
        name="组件生命周期",
        ir_json=dumps({"steps": [
            {"operation_id": "createWidget"},
            {"operation_id": "getWidget"},
            {"operation_id": "deleteWidget"},
        ]}),
    )

    edges = derive_operation_relationships([create, get, remove], [scenario])

    assert any(
        edge["kind"] == "scenario_flow"
        and edge["source"] == "createWidget"
        and edge["target"] == "getWidget"
        and "组件生命周期" in edge["evidence"]
        for edge in edges
    )
    assert any(edge["kind"] == "schema_flow" and "widget_id" in edge["evidence"] for edge in edges)
    assert any(edge["kind"] == "resource_relation" and edge["confidence"] == 82 for edge in edges)
    assert edges == derive_operation_relationships([create, get, remove], [scenario])
