# Agent Handoff

## Current state

### Milestone 1.1-G4 — independent retention-plan verification (2026-11-04)

**CONDITIONAL PASS.** Live `AICompany` verification matched all 72 table counts,
the 120-FK graph, and all eight retained-table column lists and SQL types.
G4 corrected the G3 Agent-column nullability statement and the project
child-first cleanup sequence in
[Database_Retention_Export_Plan.md](./Database_Retention_Export_Plan.md).
The G3 graph and candidate dependency map were accurate; owner decisions and
separate export authorization remain open.

Verification used Windows Integrated Authentication and SELECT-only SQL.
`AICompany` was ONLINE on `YOSLTVBILLU02`; `POM\Vemanasai.Billu` was database
owner and current/original login and was a sysadmin. No mutation was performed.
An initial SELECT-only identity probe used `master` for server/database
metadata, outside the requested AICompany-only scope; no other user database
was accessed. Identity was reverified directly in AICompany before completion.
The source still has 56 Agents/profiles, 102 pending AgentSkill rows, 24 open
activation blockers, and the AI CEO/profile content discrepancy. Only legacy
`USER`, `MANAGER`, and `SUPER_ADMIN` roles are present; no persisted
RolePermission mapping or SQL RLS policy exists. Data provenance and migration
history remain unproven, and multi-tenant/production readiness is **NO-GO**.
The RLS guide/source state that `get_db` sets only UserID context, worker
requests do not establish SQL Agent context, context-clear failures are
suppressed, migrations 16-18 retain the old organization/department model, and
migration 27's optional RLS path has broad reaper owner visibility. Dedicated
least-privilege SQL runtime identities and scopes remain unverified.

No export, backup, restore, migration, cleanup, or SQL write occurred. Keep the
database reset unapproved. Resolve owner/privacy/legal/security dispositions,
approve a least-privilege export identity and encrypted destination, and obtain
separate authorization for any export or backup. Require an isolated restore
and data-integrity validation before any cleanup authorization.

### Milestone 1.1-G3 — retention export design (2026-11-04)

**Design complete for independent review; export and cleanup remain unauthorized.**
The G2 read-only audit mapped the 56 Agent rows to 56
WorkforceRoleProfile rows, the 102 pending AgentSkill assignments, legacy RBAC,
the complete 72-table inventory, and the 120-FK table dependency graph. The
proposed allowlist, row-level exclusions, owner-decision register, restore
verification, and future child-first cleanup phases are in
[Database_Retention_Export_Plan.md](./Database_Retention_Export_Plan.md).

No export, backup, restore, migration, SQL write, cleanup script, or cleanup
execution occurred. The AI CEO Agent/profile job-description and
responsibility fields differ; preserve both pending owner decision. Audit,
approval, bootstrap, workforce-request, requirement/assessment, identity/PII,
and other review records also require explicit disposition. The source login
was sysadmin; it must not be used for future export or cleanup. Keep the
database reset unapproved until the plan and all owner decisions are approved,
a separate full backup is restored and validated in isolation, and a
least-privilege identity/destination are approved.

### Milestone 1.1-G — database reset audit (2026-11-04)

At G1, the read-only `AICompany` audit stopped before a complete retention
mapping, and was **NOT READY** for export or cleanup approval. G2 completed the
read-only mapping without inventing role relationships; G3 records a design,
not an export/cleanup approval. Only legacy `USER`, `MANAGER`, and
`SUPER_ADMIN` codes are present; agent security/approval-role columns have no
catalog foreign keys; no role-permission mapping was found. No destructive
operation or migration ran. See the latest dated sections in
[IMPLEMENTATION_STATUS.md](./IMPLEMENTATION_STATUS.md) and
[Database_Retention_Export_Plan.md](./Database_Retention_Export_Plan.md).

Milestone 1.1 (SQL Server RLS and runtime isolation) is **partially complete /
blocked / NO-GO**. A detailed RLS design and offline harness safeguards are
documented and implemented, but no SQL Server integration evidence exists.
No production deployment is permitted. The repository has application-layer
reviewer and worker authentication, but no verified SQL Server RLS isolation
for those identities. Migration 27 still grants the reaper broad owner-scoped
visibility when the legacy ownership policy is enabled.

Read [IMPLEMENTATION_STATUS.md](./IMPLEMENTATION_STATUS.md) for verified source
findings, test results, and remaining risks.

## Next authorized work

1. Independently security-review the architecture and harness in
   `RLS_Deployment_Guide.md`; design and offline tests are not implementation
   or proof.
2. Review and approve the corrected G4-verified retention plan and resolve the
   AI CEO field/hierarchy discrepancy, data provenance, audit/approval/request
   retention, identity/PII treatment, and all other REVIEW classifications.
   Do not infer missing RBAC mappings.
3. Approve a secured isolated export destination and least-privilege identity,
   then separately authorize export implementation. Require a full backup and
   isolated restore test before any cleanup authorization. Do not export,
   create a backup, or clean the database under the G3 design-only approval.
4. Obtain separate authorization for database provisioning and RLS
   implementation. This task explicitly stopped before either.
5. After authorization, create a unique `AICompany_M1_IT_` database only after
   rechecking the exact name. The prior candidate `AICompany_M1_IT_20261103`
   was absent at inspection time but was not reserved. Never use `AICompany`,
   `SharePoint`, or any other unclassified database.
6. Provision a dedicated non-production test identity with database-only
   minimum permissions; do not use the local `sysadmin` principal.
7. Configure all required `RUNTIME_IT_*` settings in protected local
   configuration. Never log or commit URLs, credentials, or fixture secrets.
8. Implement a new reviewed migration for principal mapping, trusted
   procedures, canonical roles, and complete runtime predicates. Do not bypass
   migration 16's guard or use migration 27's broad reaper exception.
9. Execute SQL Server tests only after the actual target identity/marker and
   fixture restore path are verified. Test every table/operation, concurrency,
   rollback, pooled context, and principal permissions.
10. Update implementation status with exact commands and results. Keep
   production and RLS release status NO-GO until every gate passes.

Do not start OpenAI integration, a model gateway, new agent development, or
unrelated feature work.

## Separate unverified backlog

- Investigate duplicate backlog creation under concurrent requests.
- Investigate concurrent creation of multiple active sprints.

These were reported previously and are not confirmed or changed in this
milestone.
