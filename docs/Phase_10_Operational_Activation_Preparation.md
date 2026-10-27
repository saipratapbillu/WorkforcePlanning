# Phase 10 Operational Activation Preparation

## Safety and scope

Phase 10 produces review packages, certification-campaign status, adapter deployment diagnostics, activation checklists, and a consolidated launch recommendation. It is preparation only. These routes do not activate agents, approve models, apply migrations, apply remediation SQL, enable RLS, or create runtime history.

All campaign readiness is derived from active WorkforceRoleProfile rows, Agent/AgentSkill records, the latest Evaluation per type, approved-model catalog rows, and AuditLog skill evidence. Missing role profiles and missing evidence are blockers; the system does not infer role requirements or create templates.

## Ownership approval package

- `GET /operations/ownership-remediation` gives current candidate rows and exact-GUID verification.
- `GET /operations/ownership-remediation/approval-package` returns a machine-readable review package.
- `GET /operations/ownership-remediation/approval-document` returns Markdown suitable for an approval record.

Both package forms include remediation and rollback SQL, but neither executes it. Candidate-set validation (expected nine) is distinct from exact GUID resolution and from database-wide ownership coverage. A matching legacy GUID does not itself authorize a data change.

The Markdown document includes a candidate verification table, ownership coverage/risk summary, independent review checklist, and both SQL artifacts. Exporting it is not an approval or a data change.

## Adapter deployment and credential verification

- `GET /operations/execution-adapters/deployment-package` builds the provider-by-provider deployment wizard without resolving credentials or calling a provider.
- `POST /operations/execution-adapters/{provider_code}/verify-credential` resolves the configured secret reference and records an audit event. It does not send the credential to the provider.
- `POST /operations/execution-adapters/{provider_code}/health-check` remains a separate explicit live provider API request. Do not use it until approved credentials and endpoint configuration are present.
- The credential verification button in the Operations tab makes no provider request. Live health probing remains a separate explicit action and only proceeds after the server resolves the configured secret reference.

Secret references must use `azure-kv://secret-name[/version]` or development-only `env://VARIABLE_NAME`. Raw credentials are rejected by the API. Azure Key Vault uses `DefaultAzureCredential`; local environment resolution should not be used in production. Provider references and status are not proof of health. The live health check records `Healthy` only after a real successful response and never retains the provider response body or secret value.

See [Phase 9 Operational Readiness](Phase_9_Operational_Readiness.md) for optional packages, provider host restrictions, timeouts, and secret-provider configuration.

The deployment package reports endpoint/model/reference configuration separately from credential verification and provider health. It never marks a provider healthy from configuration alone.

## Certification campaign

`GET /operations/certification-campaign` reports five requested campaign roles: AI Business Analyst, AI Solution Architect, AI Data Analyst, Software Developer, and AI QA Engineer. It binds only to active installed role profiles. If no matching profile exists, the role is returned as `NotInstalled` and blocked; no skill list is fabricated.

For each matching agent it reports required/current proficiency, AgentSkill status, latest Capability/Safety/Security/Governance outcomes, skill evidence found in the audit trail, model approval/configuration, readiness, and blocking evidence. The endpoint is read-only. Actual skill approval and certification recording remain in the governed Workforce Manager processes.

If an active role profile is not installed, the campaign returns `NotInstalled` rather than inventing a profile or skill list. The current role catalog does not contain every requested title; those require separately approved profile onboarding.

## Operational activation runbook

`GET /operations/activation-runbook` returns model onboarding, certification, activation, runtime validation, and rollback checklists, together with the current launch snapshot. It is a generated review artifact. It does not execute checklist items or change the reported NO-GO state.

## Executive Go/No-Go

- `GET /operations/phase10-launch-readiness` provides ownership, adapter, model, campaign, runtime, and RLS status with blockers and a final recommendation.
- `GET /operations/activation-runbook` exports the model, certification, activation, runtime, and rollback checklists with the current launch snapshot.
- The Operations tab in the Admin Control Center shows these measures and the certification campaign.
- CEO/COO/CIO views remain in the Executive Command Center and use verified readiness scores.

No financial savings are estimated. Workforce savings remains “Not Priced.” Keep RLS disabled until its separate policy design, ownership and runtime lineage validation, negative authorization testing, and deployment approval are complete.

## Migration and validation

Phase 10 introduces no database migration. It expects the existing Phase 7/9 schema, including migration 24. If required tables are absent, use the readiness blocker output and apply reviewed migrations separately; this application never auto-applies them.

Additional Phase 10 endpoints are `GET /operations/ownership-remediation/approval-document`, `GET /operations/execution-adapters/deployment-package`, `POST /operations/execution-adapters/{provider_code}/verify-credential`, and `GET /operations/certification-campaign`.

Run `python -m pytest -q` before release. Validate the admin and executive dashboards against a non-production database. Do not test live provider connectivity without approved credentials, and do not use real ownership or runtime records as test fixtures that mutate the connected database.
