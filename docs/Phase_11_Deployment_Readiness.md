# Phase 11 Deployment Readiness & Onboarding Package

## Guardrails

Phase 11 adds pre-deployment validation and evidence packages only. It does not apply migration 24 or any other migration, execute ownership SQL, approve models, activate agents, create evaluations, generate runtime history, or enable RLS. Ownership review decisions are written to the existing AuditLog only; they do not alter ownership columns or authorize SQL execution.

## Migration 24 validator

`GET /operations/migration-24/validation` reads the checked-in `sql/24_intelligent_workforce_reuse.sql`, verifies expected table/constraint fragments and idempotency guards, and checks prerequisite table existence. It does **not** submit the script to SQL Server. The “dry run” is a static source/schema inspection, not a database execution plan or transactional rollback simulation. The migration currently has no rollback SQL; the response provides a manual backup/restore and review checklist instead of inventing destructive rollback SQL.

A passing static result is not deployment authorization. A DBA should review the full migration, take a verified backup, schedule a change, execute in a controlled environment, and validate the resulting schema/data separately. Static migration readiness is separate from migration application; launch remains NO-GO until migration 24 is applied through approved deployment control.

The validator returns the script SHA-256, character and batch counts, required-contract checks, prerequisite table/column state, current migration-table presence, and a non-destructive application rollback path. It does not evaluate SQL Server execution plans or guarantee a transaction rollback. The returned overall package maps Governance, Workforce, Runtime, Security, Model, Adapter, Ownership, and RLS readiness to explicit `READY`/`BLOCKED` states and calculates the overall percentage from those eight checks.

## Ownership approval workflow

The Operations tab lists each current candidate and exact-GUID result. A reviewer can record `NeedsReview`, `ApprovedForManualChange`, or `Rejected` with rationale, evidence reference, and change ticket. This creates one immutable AuditLog event containing the current candidate-set fingerprint and explicitly records `ownership_sql_executed=false`.

The review is not permission for this application to update ownership. The remediation, rollback, approval document, and audit packages are exports for a separately authorized change process. The database records remain unchanged by the review action.

Ownership matching explicitly compares the converted legacy GUID to the matched `AppUser.UserID`. A package review is bound to a fingerprint of the current candidate set; if candidates change, the prior audit decision does not approve the new set.

Routes:

- `GET /operations/ownership-remediation/approval-package`
- `GET /operations/ownership-remediation/approval-document`
- `GET /operations/ownership-remediation/rollback-package`
- `GET /operations/ownership-remediation/audit-package`
- `POST /operations/ownership-remediation/reviews`

## Model onboarding wizard

The Phase 11 proposal form uses `POST /governance/models/proposals`, which creates only a `Pending` model proposal. Provider registry creation may happen as part of the first proposal for a provider, but the model is not approved. Review remains a separate Platform Owner action requiring a different user, reason, and evidence. The onboarding package reports provider/model status, prior decision evidence, and the review checklist.

Routes:

- `GET /operations/model-onboarding/package`
- `POST /governance/models/proposals`
- `POST /governance/models/{model_catalog_id}/decision`
- `GET /operations/model-onboarding/approval-evidence-package`

No approval control is included in the Phase 11 proposal wizard.

## Adapter setup

`GET /operations/execution-adapters/deployment-package` provides provider-by-provider setup blockers for Azure OpenAI, OpenAI, Google Vertex AI, and Anthropic. Credential verification resolves a secret reference and writes a safe audit record; it does not make an HTTP provider call. Only the separate health-check route makes a live provider request, and it requires a resolvable credential plus a currently Approved model under an Active provider.

Routes:

- `GET /operations/execution-adapters/deployment-package`
- `POST /operations/execution-adapters/{provider_code}/verify-credential`
- `POST /operations/execution-adapters/{provider_code}/health-check` (live call, never triggered by Phase 11 package generation)

## Certification campaign

`GET /operations/certification-campaign` tracks the five requested job families against active installed WorkforceRoleProfile records. No matching profile returns `NotInstalled`. Existing active/pending skill rows, skill approval evidence in AuditLog, latest evaluation by type, model catalog status, and agent lifecycle state determine blockers. No skills or evaluations are created by the campaign endpoint.

Campaign readiness also checks current workload and concurrent-task capacity. Skill evidence is matched to the exact required skill IDs; unrelated skill audit evidence does not satisfy a requirement.

## Launch and runbook exports

`GET /operations/activation-runbook` packages model, certification, activation, runtime, and rollback checklists with the current launch snapshot. `GET /operations/phase10-launch-readiness` remains the consolidated executive source for ownership, adapters, model, certification, runtime, and RLS status. `GET /operations/phase11-deployment-package` packages these reports and explicitly marks all actions as not performed.

The static Phase 11 scorecard reports current evidence and blockers; a `NO-GO` remains until actual database prerequisites and governed readiness requirements are met. There are no placeholder approvals or runtime outcomes.

`GET /operations/phase11-deployment-package` is the final executive export. It includes the eight named readiness sections, overall readiness percentage, Go/No-Go, blockers, deployment/rollback checklists, ownership review state, model evidence, adapter/certification packages, and runtime/execution blocker reports. It sets all action flags to false and leaves RLS unchanged.

## Verification

Run `python -m pytest -q`. Review each generated package and its `generated_at_utc` timestamp before attaching it to a change ticket. A static migration check is not a SQL Server dry run. Do not treat an ownership package review as an executed remediation, a credential reference as a provider health result, or an approved model as a certified/active agent.
