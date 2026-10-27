# Phase 13 Controlled Pilot Preparation

## Purpose and access

The read-only package at `GET /operations/phase13-pilot-preparation` is available through the existing Executive and Platform Owner authorization policy. The Platform Owner Admin Control Center provides a JSON export. It composes current Phase 12 activation evidence, model lifecycle/usage evidence, and the ownership review audit archive with approval-ready templates and runbooks.

The package prepares review materials; it does not create an approval decision or sign-off record. Existing authorized governance and change workflows remain the only route to record decisions or execute changes.

## Package contents

- **Ownership:** final exact-GUID candidate evidence, rollback package, current approval evidence archive, and a sign-off workflow. The status `Ready For Approval` means the package evidence matched the configured candidate count; it does not mean approved or executed.
- **Migration 24:** DBA approval package, idempotency/dependency/schema/rollback evidence, deployment and rollback runbooks, validation and post-deployment checklists. Static inspection is not a SQL Server dry run. Migration execution remains outside the app package.
- **Provider governance:** Azure OpenAI, OpenAI, Google Vertex AI, and Anthropic proposal/security/risk/evidence/retirement templates. Provider states are `Proposed`, `Pending Review`, `Approved`, and `Retired`; where the current registry has no separate provider decision record, state is explicitly `NotRecorded` and not inferred from model state.
- **Model governance:** observed proposed/pending/approved/retired lifecycle counts, model approval evidence, usage rows, approved-model impact, and an unassessed risk template. No model decision is made.
- **Certification:** the requested five-role campaign evidence, current gaps, required Capability/Safety/Security/Governance evaluations, evidence requirements, and approval checklist. No certification is created.
- **Adapter readiness:** Azure Key Vault and development-only `env://` guides, model/provider association checks, adapter validation, and connectivity test checklists. No credential is resolved and no provider is called.
- **Pilot runbook:** Requirement → Assessment → Approval → Project → Planning → Assignment → Queue → Execution → Deliverable → Closure, plus execution, validation, rollback, and evidence-collection checklists. It does not execute the pilot.
- **Executive package:** eight domain summaries with status, evidence, blockers, and recommendation; CEO/COO/CIO views; and separate pilot and production Go/No-Go results.

## Readiness semantics

Current readiness and Go/No-Go values are sourced from Phase 12 verified operational gates. An approval-ready ownership package is not ownership approval or complete ownership coverage. A static migration pass is not migration deployment. Provider registry status is not provider approval, and model approval does not imply certified agents, healthy adapters, runtime readiness, or production authorization. Missing evidence remains unavailable or blocked.

The package does not apply Migration 24, enable RLS, execute ownership corrections, approve providers/models, activate agents, create certifications, read secret values, run live probes, or create assignments, queue entries, executions, or deliverables.

## Deployment and verification

No database migration is added for Phase 13. Deploy through the normal application release process, then verify `/operations/phase13-pilot-preparation` as an authorized role and inspect the package against the target environment's current report timestamps. Run `python -m pytest -q` before release. Keep both pilot and production NO-GO until their respective evidence gates are verified and separately authorized.