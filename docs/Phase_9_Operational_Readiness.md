# Phase 9 Operational Workforce Activation Readiness

## Scope and safety

Phase 9 adds read-only readiness reporting, a historical ownership review package, real authenticated provider probes, model/workforce/certification analytics, runtime blockers, and CEO/COO/CIO scorecards. It does not activate agents, approve models, change ownership, modify runtime history, or enable SQL Server RLS.

Every dashboard value is sourced from current database rows or an executed HTTP probe. A missing denominator is shown as unavailable; a zero record count is not converted into a readiness success. Readiness percentages are computed as passed explicit gates divided by total explicit gates. The dashboard's Go/No-Go is advisory and is not deployment authorization.

## Deployment prerequisites

1. Review and apply `sql/24_intelligent_workforce_reuse.sql` through the approved database change process before using Phase 7/9 workforce-reuse analytics.
2. Apply existing workforce, model-governance, adapter-governance, and runtime migrations in their documented order. The API checks for missing Phase 7 tables and reports blockers; it does not apply migrations.
3. Base dependencies are in `requirements.txt`. Optional production integrations are in `requirements-operations.txt`; install them in the service environment when using Azure Key Vault or Google Vertex authentication.
4. Configure `AI_WORKFORCE_SECRET_PROVIDER=azure-key-vault` and `AZURE_KEY_VAULT_URL` for managed Azure Key Vault, or use `AI_WORKFORCE_SECRET_PROVIDER=local` only for development with `env://VARIABLE_NAME` secret references. Azure authentication uses `DefaultAzureCredential`; provision a least-privilege identity that can read only the named secrets.
5. Never put secret values in adapter configuration, SQL, audit records, error messages, or browser requests. Store only the secret reference in `ExecutionAdapterConfig`.
6. Configure `AZURE_OPENAI_API_VERSION` only after validating the API version supported by the deployed Azure resource.

Google Vertex probes resolve a service-account credential document from the configured secret provider and require permission to read the specified Vertex model resource. A missing or malformed credential is `ConfigurationIncomplete`; credential refresh failures are `Error`. All network probes have bounded timeouts, do not follow redirects, restrict provider hostnames, and suppress response bodies.

## Ownership remediation package

`GET /operations/ownership-remediation` reports the current null-owner candidates, exact legacy GUID matches, unresolved records, and generated remediation/rollback SQL. `GET /operations/ownership-remediation/approval-package` returns the report, review checklist, coverage, risk score, and scripts in a JSON exportable package.

The expected count of nine is a validation assertion, not a hard-coded claim that nine records currently exist. An exact match means `TRY_CONVERT(uniqueidentifier, legacy_owner)` equals an existing `AppUser.UserID`. All other rows remain unresolved. Neither endpoint executes generated SQL. The rollback artifact only reverses a reviewed update when the GUID still matches the expected candidate.

## Execution adapters

Supported provider codes are `AZURE_OPENAI`, `OPENAI`, `GOOGLE_VERTEX`, and `ANTHROPIC`. `POST /operations/execution-adapters/{provider_code}/health-check` resolves the configured secret and makes an authenticated, read-only provider API request. `ConfigurationIncomplete` is recorded when fields or the referenced secret are unavailable. `Healthy` is returned only after an actual successful provider response. Authentication failures, non-success responses, timeouts, and transport errors are recorded as `Unhealthy` or `Error` without logging secrets or response bodies.

A successful health probe verifies only the configured API endpoint and credential at that time. It does not enable the execution runtime or certify an agent. Adapter configuration changes and probes are retained in `AuditLog` and `ExecutionAdapterHealthCheck`.

## Model and certification analytics

`GET /operations/model-governance` reports lifecycle counts, elapsed pending-review hours, pending reviews, approved-model usage, and retirement impact. No approval SLA has been approved/configured, so the API returns `approval_sla.configured=false` and does not label a proposal overdue. Retirement is blocked while active agents, unreleased active assignments, or executing runs reference the model.

`GET /operations/certification-dashboard` uses the latest evaluation by agent and evaluation type. It returns evaluation pass rates, active workforce certification/skill coverage, and historical monthly evaluation counts. The schema has no expiry field; the response explicitly says `Expiry Not Tracked`.

## Runtime and RLS readiness

`GET /operations/phase9-readiness` returns explicit gates, blockers, assignment/queue/execution/deliverable counts, ownership lineage, adapter/model/certification readiness, workforce reuse metrics, and domain scorecards. CEO, COO, and CIO summaries are available through `GET /operations/executive-readiness/{view}` for `CEO`, `COO`, or `CIO`.

`GET /operations/rls-readiness/package` exports the ownership/runtime/predicate report, risk assessment, deployment checklist, and rollback checklist. It is a review artifact only and contains no executable migration or RLS enablement action.

RLS reporting reads `sys.security_policies` and `sys.security_predicates` only. The endpoint does not issue DDL or enable policies. Do not deploy legacy scripts 16-18 for the current single-organization authorization model; use the current RLS deployment guide and a separately reviewed policy design. `will_be_enabled` and `rls_will_be_enabled` remain false.

## API inventory

- `GET /operations/ownership-remediation`
- `GET /operations/ownership-remediation/approval-package`
- `GET /operations/phase8-readiness`
- `GET /operations/phase9-readiness`
- `GET /operations/rls-readiness/package`
- `GET /operations/executive-readiness/CEO|COO|CIO`
- `GET /operations/model-governance`
- `GET /operations/certification-dashboard`
- `GET /operations/execution-adapters`
- `POST /operations/execution-adapters/{provider_code}/health-check`
- `GET /operations/execution-adapters/audit-history`

All operational reads and checks require an authorized Executive or Platform Owner. Mutating adapter configuration/model retirement routes retain their existing human rationale/evidence and audit gates.

## Verification

Run `python -m pytest -q`. Before using a readiness report for a release decision, review the current database migration state, candidate rows and SQL, approved identity evidence, model/agent references, live probe timestamp, and RLS coverage output. A dashboard report does not replace change approval, backup, operator review, or deployment validation.
