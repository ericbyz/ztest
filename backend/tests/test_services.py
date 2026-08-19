"""Unit tests for deterministic core services and security policy."""

import pytest

from app.security import UnsafeTargetError, validate_target
from app.services import normalize_operations, parse_openapi, validate_ir


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
