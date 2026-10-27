# Autonomous Operations Factory

## Scope and safety

The Operations Factory transforms hosting and delivery plans into operations, SRE, support, incident, problem, change, capacity/cost, patch, runbook, dashboard, and readiness artifacts. It is planning and simulation only.

Requirement creation includes `operations_execution_package` in its transient workforce blueprint. Workforce reviewers can request a preview using `POST /workforce/factory/operations-plan` and download it from Workforce Planning. No monitoring resource or workspace is created; no alert or ticket is created; no integration is configured; no runtime, cloud, or persistence action is performed.

Authority is `NONE`; `action_allowed` and persistence are false. Operational readiness is `NOT READY` until owners, thresholds, monitoring, recovery, capacity, and cost baselines are actually approved and configured.

## Operations package

- Monitoring strategy covers application, infrastructure, database, security, availability, health checks, and synthetic monitoring. Signals are proposed; thresholds are owner-defined and alerts remain unconfigured.
- Observability covers structured/privacy-safe logging, trace context and sampling, golden-signal/business metrics, dashboard strategy, retention, and telemetry. No collectors or dashboards are created.
- Incident management includes a four-level severity matrix, escalation matrix, major-incident process, response/recovery steps, communications ownership, and war-room roles. No ticketing or communication integration is created.
- Problem management defines RCA, known-error database fields, trend analysis, and improvement reviews. No problem record/database is created.
- Change management defines Standard/Normal/Emergency categories, approval matrix, release controls, emergency change process, and rollback governance. No change is approved or executed.
- Capacity management reuses only delivery-plan role estimates as assumptions. Current capacity, utilization, storage growth, and production trends remain unavailable; growth percentages are explicitly scenario assumptions, not forecasts.
- Cost optimization describes cost monitoring and optimization opportunities. Monthly cost and budget thresholds remain null until region/SKU, usage, currency, and owner-approved budget inputs exist.
- Patch management provides security, application, platform, dependency, and calendar processes. The calendar remains owner-defined and no patch is applied.
- Runbooks are proposed catalog entries with owners and triggers; they are not executed.

## Readiness and validation

The SRE dashboard reports monitoring, incident, capacity, cost, and overall operations readiness. No live telemetry or operational history is queried. The operations readiness score reflects currently satisfied planning prerequisites only; it is not service health.

Run `python -m pytest tests/test_operations_factory.py tests/test_requirement_creation_ownership.py -q` for package structure, unknown capacity/cost values, blocked readiness, and no-action assertions. The tests execute only deterministic planning code and never create operational resources.
