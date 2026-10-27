# Phase 12 Operational Activation & Pilot Readiness

## Purpose and boundaries

Phase 12 adds one consolidated, evidence-backed activation-readiness export at `GET /operations/phase12-activation-readiness`, available to the existing Executive and Platform Owner roles. The Admin Control Center exposes the JSON download. It composes the existing ownership, migration, model, adapter, certification, runtime, and launch reports; it is not an activation or deployment control.

Package preparation status is distinct from an operational GO decision. A review package may be ready for independent review while the corresponding operating gate remains blocked. The eight-domain Phase 12 score evaluates actual operational gates, including whether Migration 24 is applied; static validation alone cannot pass governance readiness. Missing denominators remain `null`/unavailable and are never converted into successful readiness.

The endpoint does not:

- Apply Migration 24, ownership remediation SQL, or any other SQL DDL/DML.
- Approve/reject models, activate agents, create certifications, or assign work.
- Resolve or expose secret values, call provider endpoints, enable the runtime, or create execution/deliverable history.
- Enable or alter SQL Server RLS.

## Included workstreams

1. **Ownership remediation:** exact-GUID candidates, approval package, rollback package, and candidate review state. A review package or review decision does not execute corrections.
2. **Migration 24:** source/schema validation, required dependencies and columns, idempotency evidence, applied state, DBA deployment checklist, and non-destructive rollback guidance. Static validation is not SQL Server execution or approval.
3. **Model onboarding:** Azure OpenAI, OpenAI, Google Vertex AI, and Anthropic provider onboarding, proposal/approval evidence, and counts for Pending, Approved, Rejected, and Retired models. Missing rows remain zero counts for those explicit lifecycle states; approval is never performed by this package.
4. **Adapter activation:** provider deployment diagnostics, model/provider association blockers, secret-reference guidance, and credential-reference-only policy. The package performs no secret resolution or live provider probe.
5. **Certification campaign:** the five requested role families, profile/agent/readiness counts, blocking evidence, required Capability/Safety/Security/Governance evaluations, and an evidence checklist. No skills, evaluations, or certifications are created.
6. **Workforce activation:** verified agent totals/status, active skill/certification coverage, campaign readiness, average active utilization, workforce requests by status, and Migration-24-dependent reuse candidate classes. Candidate classes are explicitly unavailable until the migration is applied; this package does not infer candidate classifications.
7. **Pilot execution:** evidence for Requirement → Approval → Project → Assignment → Queue → Execution → Deliverable, plus runtime blockers. Planned work is not represented as staffed or executed work.
8. **Executive Go/No-Go:** the eight readiness domains, overall score, blockers, deployment/rollback checklists, and CEO/COO/CIO summaries derived from the existing executive readiness views.

## Workforce metric definitions

- `workforce_readiness_percent` is campaign-ready agents divided by campaign agents. It is unavailable when there is no campaign denominator.
- Skill and certification coverage are sourced from the existing certification dashboard; their existing denominators and `null` values are preserved.
- Utilization is the average recorded `CurrentWorkload` for Active agents. It is unavailable when there are no Active agents.
- Reuse candidate categories are counts of persisted Migration 24 assessments, not a generated prediction. If Migration 24 is absent, the classification object is `null` and its status explains why.
- Workforce request counts are grouped by their stored status. Assignment eligibility remains governed by the existing planner rules for role, active skills, latest passing evaluations, approved model, workload, and concurrent capacity.

## Deployment

No Phase 12 database migration is introduced. Deploy the application through the normal release process, then validate health, the Phase 12 endpoint as an authorized role, and package generation against a non-production environment. Apply Migration 24 only through a separately approved DBA change after backup, checksum/schema review, and rollback planning. Do not treat the package's static result as authorization to apply it.

Run `python -m pytest -q` before release. The test suite verifies package fail-closed semantics and that Phase 12 workforce reporting uses read-only queries. The endpoint's executive subviews reuse existing role-protected readiness functions.

## Current-state interpretation

An overall `NO-GO` means pilot execution remains blocked even if some preparation artifacts are ready for review. A planned project with tasks is not assignment, queue eligibility, execution, or an accepted deliverable. RLS remains unchanged and disabled unless a separate security design and approved deployment explicitly authorize otherwise.