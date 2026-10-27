# SDLC Factory Planning Package

## Purpose and boundary

Requirement creation returns a deterministic technical delivery package alongside the existing workforce blueprint. This is a planning-only MVP: it uses bounded rules and the requester-provided title, description, selected priority, and explicitly declared/supported technology names. It is not a live AI CEO/architect model and must not be presented as an approved technical design.

The package is transient in the `POST /requirements` response; it is not stored separately. The requirement's existing persistence/approval behavior is unchanged. No source code, database schema, API implementation, cloud resource, deployment, runtime activity, approval, or agent assignment is created.

## Workflow

1. Requirement: accept and persist the existing authenticated requirement under the existing create flow.
2. AI CEO Analysis: provide a deterministic draft of business domain, solution type, complexity, requester priority, dependencies, and risks. The selected priority is preserved; inferred domain and complexity are heuristics requiring review.
3. Architecture: propose style, components, services, interfaces, integration points, and backend service boundaries.
4. Database Design: propose entities, relationships, table names, key/index guidance, and retention rules. These are not claims about the existing schema.
5. Backend Design: describe service boundaries, authorization/validation responsibilities, transaction boundaries, audit, and failure handling.
6. Frontend Design: propose screens, forms, navigation, journeys, and accessibility requirements.
7. API Design: propose versioned endpoints plus request/response model outlines, validation, errors, idempotency, and pagination requirements.
8. Security Design: propose authentication/authorization, audit, data classification, and threat-review requirements.
9. Testing Design: propose unit, integration, UAT, security, and performance coverage and acceptance gates.
10. Deployment Design: propose hosting, database, storage, monitoring, and backup strategy without creating infrastructure.
11. Workforce Alignment: map proposed architect, developer, QA, security, and DevOps contributions to Agent Factory roles where the requirement rules select them. Headcount is a planning estimate; live availability and capacity require the workforce dashboard.

## Package contract

`technical_delivery_package.artifacts` includes `executive_assessment`, `architecture_blueprint`, `database_blueprint`, `api_catalog`, `ui_blueprint`, `security_blueprint`, `testing_blueprint`, `deployment_blueprint`, and `workforce_plan`. Every design artifact is marked `proposed` where applicable. Open questions highlight scope, data classification/tenancy/retention, technology, integration, hosting, and availability decisions requiring accountable review.

The analysis mode is `DETERMINISTIC_HEURISTIC_DRAFT_REQUIRES_HUMAN_VALIDATION`. The package status is `PLANNING_ONLY`. Control flags explicitly remain false for code generation, infrastructure creation, deployment, runtime start, schema/API implementation, agent assignment, approval authority, and persistence.

## Validation and governance

Generated table names, API paths, architecture choices, and risk classifications are starter proposals, not verified requirements. Confirm them with business owners, architecture, data/privacy, security, operations, and delivery reviewers. Do not copy proposals into production migrations or deployment pipelines without normal change control. High/Critical priority continues to trigger the existing assessment/approval workflow; the technical package neither approves nor bypasses it.

Run `python -m pytest tests/test_agent_factory.py tests/test_requirement_creation_ownership.py -q` for package and requirement-create contracts, then run the full project suite before release. Tests assert deterministic output, selected-priority preservation, all nine artifact families, and planning-only control flags.