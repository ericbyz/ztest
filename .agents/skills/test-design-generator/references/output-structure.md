# Test design output structure

Use the smallest useful subset when `scope` is narrower than `all`. Preserve the same identifiers across Markdown, YAML, JSON, DOCX, XLSX, and TAPD representations.

## Markdown document

```markdown
# Test Design: <project/module>

## 1. Input baseline
- Requirement sources and versions
- API sources and versions
- Generation scope and exclusions

## 2. Requirement analysis
| Requirement ID | Summary | Priority | Testability | Source | Questions |

## 3. Test strategy and scope
- In scope / out of scope
- Test levels and types
- Environment, authentication and data assumptions
- Entry/exit criteria
- Risks

## 4. Requirement–API mapping
| Requirement ID | Operation | Method/Path | Mapping reason | Confidence |

## 5. Business/API test flows
### FLOW-001 <name>
- Objective
- Requirement references
- Actor/authentication
- Preconditions
- Main flow
- Alternative/error branches
- Data bindings
- Checkpoints/assertions
- Cleanup/rollback

## 6. Test scenarios
| Scenario ID | Flow | Scenario | Type | Priority | Requirement IDs |

## 7. Detailed test cases
### TC-001 <title>
- Priority
- Requirement references
- API references
- Preconditions
- Test data

| Step | Action/request | Data/binding | Expected result |

- Cleanup
- Automation suitability
- Notes

## 8. Traceability and coverage
| Requirement ID | Flows | Scenarios | Cases | API operations | Status |

## 9. Gaps and questions
- Missing API capabilities
- Documentation gaps
- Ambiguous business rules
- Unsafe or uncleanable operations
```

## Structured YAML/JSON model

```yaml
schema_version: "1.0"
metadata:
  title: ""
  generated_at: ""
  requirement_sources: []
  api_sources: []
  scope: all

requirements:
  - id: REQ-001
    summary: ""
    source: ""
    priority: P1
    testability: ready
    questions: []

api_operations:
  - id: createOrder
    method: POST
    path: /orders
    source: ""

flows:
  - id: FLOW-001
    name: ""
    requirement_refs: [REQ-001]
    actor: ""
    preconditions: []
    steps:
      - id: step-1
        operation_ref: createOrder
        input: {}
        extract: {}
        expected: []
    branches: []
    cleanup: []

scenarios:
  - id: SCN-001
    flow_ref: FLOW-001
    name: ""
    type: positive
    priority: P1
    requirement_refs: [REQ-001]

test_cases:
  - id: TC-001
    scenario_ref: SCN-001
    title: ""
    priority: P1
    requirement_refs: [REQ-001]
    api_refs: [createOrder]
    preconditions: []
    test_data: {}
    steps:
      - action: ""
        expected: ""
    cleanup: []
    automation: recommended

traceability:
  - requirement_ref: REQ-001
    flow_refs: [FLOW-001]
    scenario_refs: [SCN-001]
    case_refs: [TC-001]
    operation_refs: [createOrder]
    status: covered

gaps: []
questions: []
```

## Quality rules

- IDs must be unique and stable within a document.
- A test plan without flows is incomplete when cross-API behavior exists.
- A flow is not a detailed test case; do not repeat identical prose at every level.
- Expected results must identify an observable response, state, event, or data change.
- Generic expectations such as “works correctly” are invalid.
- Requirement-derived expectations must not be weakened to match undocumented behavior.

