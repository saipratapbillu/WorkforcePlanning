# Implementation Status

## Milestone 1.1 - SQL Server RLS and Runtime Isolation

**Status: NO-GO.** No production deployment is permitted. Application-level reviewer
and worker controls exist, but the corresponding SQL Server RLS isolation and
least-privilege reaper access have not been implemented or verified.

### Verified repository facts (2026-11-03)

- `sql/12_agent_runtime.sql` defines runtime queue, execution, output, event,
  escalation, and defect tables.
- `sql/16_sql_server_rls_migration.sql` explicitly aborts with error 51206 when
  runtime and assignment tables exist. It does not provide predicates for them.
- `sql/23_single_organization_rbac.sql` establishes canonical roles
  `BUSINESS_USER`, `APPROVER`, `EXECUTIVE`, `WORKFORCE_MANAGER`, and
  `PLATFORM_OWNER`. The owner predicate in migration 16 instead checks legacy
  codes such as `USER`, `MANAGER`, `OWNER`, and `SUPER_ADMIN`; this role mismatch
  must be resolved before native RLS can work correctly.
- `sql/27_review_lease_and_reviewer.sql` adds `RUNTIME_REVIEWER` and
  `RUNTIME_REAPER`, but no runtime-table security predicates. Its owner predicate
  grants `RUNTIME_REAPER` owner-row access across the existing ownership-scoped
  tables; this is broader than an expired-lease-only permission.
- `app/db/session.py` sets and clears only `SESSION_CONTEXT('UserID')`. It does
  not initialize worker or review context. Cleanup errors are swallowed, so a
  failed context clear can return a connection with uncertain context to the
  pool.
- `/runtime/worker/*` bypasses web-session middleware. `app/api/runtime.py`
  validates the worker token and returns its AgentID, but does not propagate an
  agent-scoped SQL identity. Reviewer access is currently enforced at the HTTP
  layer, not by a narrowly scoped database policy.
- `tools/runtime_reaper.py` sets the reaper AppUser as `UserID`; it relies on the
  broad owner-policy exception in migration 27 when that policy is installed.
- The route matrix describes HTTP authorization only; it is not evidence of
  database row isolation.

These are static repository findings. The live database's current migration
ledger, schema, security policies, and applied migration state were not queried
for this milestone.

### SQL Server environment inspection (2026-11-03)

- Instance: local default instance `MSSQLSERVER`, SQL Server 2022 Developer
  Edition, version `16.0.1000.6` (RTM). Service runs as
  `NT Service\MSSQLSERVER`.
- Authentication configuration: mixed mode is enabled (`LoginMode=2`,
  `IsIntegratedSecurityOnly=0`). No dedicated non-production integration SQL
  login or its permission scope was identified or provisioned.
- ODBC Driver 17 is installed; the repository venv has `pyodbc 5.1.0` and
  `SQLAlchemy 2.0.35`.
- A read-only catalog query to `master` found online databases `AICompany` and
  `SharePoint`, plus system databases. Neither user database is confirmed
  disposable; both are treated as potentially live. No `AICompany_M1_IT` test
  database exists. No user database was opened.
- C: has approximately 319 GB free. SQL Server's configured default data/log
  directory is under its local `MSSQL16.MSSQLSERVER` data directory. Capacity
  alone does not establish authorization or safe isolation.
- No `.bak` or `.bacpac` was found in the repository or project parent.
  `msdb` backup history returned no rows. The instance's configured backup
  directory could not be enumerated because access was denied. Consequently
  no backup whose origin/compatibility can be verified or safely restored was
  available to this inspection.
- `RUNTIME_IT_DATABASE_URL` and `RUNTIME_IT_FIXTURE_JSON` are unset. A
  read-only connection to `master` using local Windows integrated
  authentication succeeded; this was not a test-database connectivity test.
- A schema-only synthetic database is not a suitable substitute for the
  requested restored-copy validation: the current tests expect the migrated
  review schema and referentially complete, runnable execution fixtures, and
  the target compatibility question is specifically whether those migrations
  work against the existing AICompany schema. A synthetic database could
  support limited isolated functional tests after separate authorization and
  setup, but cannot prove that compatibility. No database was created.
- A follow-up read-only query to `master` confirmed that the local Windows
  integrated principal used for inspection is a SQL Server `sysadmin`. This
  proves administrative provisioning capability, not least-privilege test
  access: no dedicated integration-test identity was created, no user database
  was opened, and no database was created. It does not resolve the missing
  verified backup, migration restrictions, or unsafe fixture cleanup.

No database was created, restored, modified, or dropped. Migrations were not
applied. There is no safe basis for labeling an existing database disposable.

### Milestone 1.1-A/B design and harness hardening (2026-11-03)

The approved scope was architecture design and offline test-harness hardening
only. No SQL Server connection was opened in this task; no database, login,
schema, fixture, credential, or environment variable was created or changed;
no migration or SQL Server integration test was run.

- `docs/RLS_Deployment_Guide.md` now documents the threat model, role matrix,
  trusted identity/context model, pool rules, table-by-table RLS design,
  migration ordering, negative tests, deployment gates, and explicit
  multi-tenancy limitations.
- `tests/integration/sqlserver_safety.py` validates configuration and fixture
  manifests before engine creation, verifies actual server/database/login and
  a setup-owned read-only database marker, rejects sysadmin/db_owner test
  principals, serializes test runs with an application lock, streams a bounded
  snapshot of synthetic `dbo` rows, rejects triggers/temporal tables/external
  references that defeat restoration, and checks table-definition drift.
- `tests/integration/test_runtime_sqlserver.py` uses those guards and state
  restoration. Offline regression coverage is in
  `tests/integration/test_sqlserver_safety.py`.
- `README.md` was inspected and left unchanged with its pre-existing conflict
  markers.

Offline harness safety tests: **16 passed**. SQL Server concurrency, RLS,
session-context pooling, migration behavior, test-principal permissions, and
cleanup against an actual SQL Server remain **not tested**. The design is
documented, but runtime RLS is not implemented, security-reviewed, or
production-verified. Synthetic test infrastructure remains unprovisioned.

### Synthetic environment authorization review (2026-11-03)

The user explicitly authorized a new synthetic database under the
`AICompany_M1_IT_` prefix, resolving the earlier requirement to obtain approval
for a reduced-fidelity environment. A read-only query to `master` confirmed the
exact candidate `AICompany_M1_IT_20261103` does not exist. The local integrated
principal is a SQL Server `sysadmin`, and mixed authentication is enabled.

Provisioning stopped before `CREATE DATABASE`, login creation, or application
schema changes because the task's explicit stop condition requires stopping
when the RLS design is incomplete or contradictory. This condition is confirmed:

- Migration 16 refuses to run when runtime/assignment tables exist (error
  51206), and its owner predicate uses legacy role codes inconsistent with
  migration 23.
- Migration 27 adds reviewer/reaper roles but no runtime-table predicates; its
  optional owner predicate grants the reaper broad owner-scoped access.
- The worker/reviewer SQL identity and session-context/RLS contract is not
  implemented or validated.
- At that assessment, the integration harness checked only a database-name
  prefix and had no general cleanup. It was subsequently hardened in code and
  unit-tested offline, but has not been run against SQL Server.

No dedicated test login was created, no integration URL or fixture variable was
configured, and no integration tests were run in this follow-up. The candidate
name check is not a reservation; recheck it immediately before any future
creation. The approved synthetic approach cannot validate production-schema
compatibility, and neither synthetic nor production RLS validation has occurred.

### Harness suitability and validation evidence (initial baseline; superseded below)

- Full Python suite: `python -m pytest -q` - **295 passed, 10 skipped** in 2.90s.
  The command used the repository `.venv` interpreter.
- SQL Server tests: **not executed against SQL Server**. The integration suite
  requires `RUNTIME_IT_DATABASE_URL` and fixture data; neither is configured.
  Its database-name prefix check (`AICompany_M1_IT`) is not proof of isolation.
  Tests update fixture execution/queue/output rows and commit those changes;
  there is no general test teardown restoring the fixture state. Do not run
  these tests against any shared or potentially live database. `pytest` on the
  integration module (`python -m pytest -q tests\integration\test_runtime_sqlserver.py -rs`)
  reported **10 skipped** because the URL is unset; zero SQL Server cases ran.
- Migrations 23 and 27: **not applied or validated**. Rollback: **not tested**.
- No migration was created or changed in this investigation.

### Outstanding blockers

1. Synthetic database creation is authorized, but provisioning is stopped until
   the incomplete/contradictory RLS design is resolved and the test harness is
   made safe. A synthetic schema cannot validate compatibility with the live
   schema or production data shape. Never use `AICompany` or `SharePoint`.
2. Provide or provision a dedicated non-production SQL identity with only the
   permissions required for the selected integration tests. No such test
   identity was confirmed here.
3. Make the test harness disposable by design: run in a uniquely identified
   database, use synthetic fixtures, and ensure tests clean up or restore all
   committed mutations. A database-name prefix alone is inadequate.
4. Design a trusted, pooled-connection-safe identity contract for reviewers,
   workers, and the reaper; ensure failed cleanup invalidates rather than
   reuses the SQL connection.
5. Replace broad owner-role exceptions with operation- and row-scoped policies
   for review packages, agent-owned leases, and expired-lease recovery.
6. Align RLS role checks with canonical roles and prove independence checks,
   concurrent review leasing, worker isolation, and reaper least privilege
   under native SQL Server RLS.
7. Validate migration ordering, idempotency, and rollback on the disposable
   database before any production change.
8. The previously reported duplicate-backlog and multiple-active-sprint
   concurrency findings remain separate and unverified in this pass.
9. `README.md` contains pre-existing merge-conflict markers. It was not edited
   as part of this database-security task.

## Next safe milestone

Complete and authorize the RLS/session-identity design, and harden the mutating
integration harness before provisioning the now-authorized synthetic database
and dedicated non-production test identity. Then implement and validate the
database identity/predicate changes in that environment.
Do not begin model integration or deploy runtime execution before the SQL Server
release gates pass.

### Current milestone 1.1-A/B result (supersedes pre-hardening blocker wording)

The RLS architecture and offline harness safeguards are now documented and
implemented for review. The synthetic database is still not provisioned, the
test identity is not provisioned, and runtime RLS remains unimplemented and
unverified. The current task explicitly prohibited database provisioning,
migrations, and SQL Server integration tests. Nineteen offline harness safety
tests passed, and the repository offline regression suite passed 314 tests with
the SQL Server integration module excluded. No SQL Server tests ran. Next step
requires separate authorization for implementation/provisioning, an independent
security review, and a dedicated non-production identity. A synthetic schema
will not establish production compatibility. Multi-tenant isolation is not
currently supported by the schema because it lacks authoritative TenantID keys.

The snapshot cleanup path has not been exercised on SQL Server. Although it now
streams and bounds captured rows and rejects known trigger, temporal, external
foreign-key, and schema-drift cases, actual SQL Server metadata behavior,
permission requirements, cleanup and rollback remain unverified. Identity and
sequence counters and non-`dbo` state are not restored; a test database must be
treated as tainted and discarded after a run. This harness must not be treated
as an infallible recovery mechanism or run against a database containing
non-synthetic data.

Current files changed: `tests/__init__.py`,
`tests/integration/sqlserver_safety.py`,
`tests/integration/test_runtime_sqlserver.py`,
`tests/integration/test_sqlserver_safety.py`, `docs/RLS_Deployment_Guide.md`,
`docs/IMPLEMENTATION_STATUS.md`, `docs/AGENT_HANDOFF.md`,
`docs/Runtime_Reaper_Deployment.md`, and `docs/Runtime_Execution_Evidence.md`.

## Milestone 1.1-G — AICompany reset audit stopped (2026-11-04)

**Disposition: NOT READY for retention-export or cleanup approval.** This
read-only audit confirmed the local target identity, then stopped before a full
dependency inventory or cleanup script because live role-to-agent/RBAC
relationships cannot be proven from the catalog. No database state, credentials,
application configuration, or SQL objects were changed.

### Connection and backup evidence

- The connection alias was `LocalHost`; SQL Server reported machine/server
  `YOSLTVBILLU02`, matching the current Windows `COMPUTERNAME`. The instance is
  SQL Server 2022 Developer `16.0.1000.6`, integrated login
  `POM\Vemanasai.Billu`.
- `AICompany` was ONLINE, owned by that same login; the repository's local
  `.env` target is `localhost/AICompany`. This establishes a local configured
  development target, but does **not** establish the provenance/classification
  of the data stored in it. The current login is `sysadmin`; all database
  inspection performed here was SELECT-only.
- Catalog properties: FULL recovery model, compatibility 160, unencrypted.
  `msdb` contains no backup history for `AICompany`. No retention export or
  verified backup was created. Therefore no backup/restore has been validated.
- README and `.env.example` still contain pre-existing merge-conflict markers;
  neither was changed. The requested `AI_WORKFORCE_OS_MASTER_PLAN.md` and
  `ARCHITECTURE_DECISIONS.md` were not present in `docs/`.

### Partial catalog inventory

The database has 72 user tables, all in `dbo`, zero user views, and 1,135 rows
by partition metadata. Catalog totals: 120 foreign keys, 72 primary keys, 16
unique constraints, 45 check constraints, 119 indexes, 6 identity columns, no
table triggers, and no temporal tables. This is a bounded initial inventory,
not the complete per-table constraint/index/dependency audit required before
cleanup.

Nonzero row-count facts (all other user tables had zero rows at inspection):

| Table | Rows | Initial disposition |
| --- | ---: | --- |
| Agent | 56 | RETAIN; role/status/configuration still require reconciliation |
| AgentActivationBlocker | 24 | REVIEW; activation evidence and status need reassessment |
| AgentSkill | 102 | RETAIN; agent capability relationship |
| Approval | 7 | REVIEW; approval/audit retention policy required |
| AppUser | 39 | REVIEW; identity/PII, ownership and role retention unresolved |
| AppUserAvailability | 18 | REVIEW; workforce/user data |
| AppUserCertification | 6 | REVIEW; workforce/user evidence |
| AppUserSkill | 35 | REVIEW; workforce/user evidence |
| AuditLog | 257 | REVIEW/retain pending legal, security and retention policy |
| Company | 1 | RETAIN as an agent organizational reference pending tenant design |
| Department | 22 | RETAIN as an agent organizational reference pending tenant design |
| EscalationPolicyProfile | 6 | REVIEW; policy/configuration, not disposable by row count |
| EvaluationTemplate | 4 | REVIEW/retain; governance configuration |
| EvaluationTemplateCriterion | 13 | REVIEW/retain; governance configuration |
| GovernanceGateProfile | 15 | REVIEW/retain; governance configuration |
| Notification | 73 | REVIEW; recipient-linked operational/audit implications |
| OrganizationBootstrapRun | 1 | REVIEW; provisioning evidence |
| Position | 64 | RETAIN as an agent organizational reference pending tenant design |
| Project | 13 | REMOVE candidate only after dependency/audit approval |
| ProjectDeliveryTask | 12 | REMOVE candidate only after dependency/audit approval |
| ProjectEpic | 7 | REMOVE candidate only after dependency/audit approval |
| ProjectFeature | 7 | REMOVE candidate only after dependency/audit approval |
| ProjectSprint | 9 | REMOVE candidate only after dependency/audit approval |
| ProjectStory | 10 | REMOVE candidate only after dependency/audit approval |
| ProjectStoryDependency | 4 | REMOVE candidate only after dependency/audit approval |
| ProjectTaskAssignment | 2 | REMOVE candidate only after dependency/audit approval |
| Requirement | 14 | REMOVE candidate only after dependency/audit approval |
| RequirementAssessment | 8 | REVIEW; decision/evidence retention unresolved |
| RequirementAssessmentDepartment | 45 | REMOVE candidate only with parent and evidence review |
| RequirementSkill | 38 | REMOVE candidate only with parent and evidence review |
| ResourceAssignmentRecommendation | 5 | REVIEW; approval/provenance may be auditable |
| Role | 3 | RETAIN pending role reconciliation; current rows are legacy codes |
| Skill | 38 | RETAIN; shared capability reference definitions |
| Task | 49 | REMOVE candidate only after dependency/audit approval |
| TaskDependency | 36 | REMOVE candidate only after dependency/audit approval |
| WorkforceRequest | 36 | REVIEW; workforce/agent-provisioning history |
| WorkforceRoleProfile | 56 | RETAIN; agent role/responsibility reference definitions |

Zero-row tables were not classified as removable. They include operational,
runtime, model/provider, credential, policy, workflow, and delivery objects and
must remain part of the full schema/dependency review.

### Stop condition: role relationships are ambiguous

The live `Role` table contains only `USER`, `MANAGER`, and `SUPER_ADMIN`; none
of migration 23's canonical role codes were present. The database has only
`Role` and `WorkforceRoleProfile` role-named tables; no role-permission mapping
table was found. `Permission` had zero rows.

The live `Agent` table has `SecurityRoleID`, `ApprovalAuthorityID`, and
`WorkforceRoleCode`. The catalog exposed a foreign key only for
`Agent.WorkforceRoleCode -> WorkforceRoleProfile.RoleCode`; no corresponding
foreign key was found for the security-role/approval-authority fields, nor for
an AppUser-to-Role relationship. Whether AppUser has a role-ID column was not
separately verified before stopping. Agent permissions are represented
separately by `AgentPermission -> Permission`. These are distinct concepts and
must not be silently merged or inferred from role names. This is an explicit
stop condition under the requested retention policy.

Agent references are also interdependent with `Company`, `Department`,
`Position`, `AgentSkill`, `AgentPermission`, `AgentTool`,
`AgentKnowledgeAccess`, activation blockers, task/workforce records and runtime
records. The full 120-FK graph, cycles, per-table indexes/constraints and
audit-log references were not enumerated after the ambiguity was established.
Consequently, no safe deletion order or retained-row guard has been proven.

### Deliverables intentionally not produced

- No retention export: its relationship set is not established, sensitive user
  and credential columns require explicit exclusion, and there is no verified
  backup/export destination or restore validation.
- No cleanup SQL script: an executable plan would risk deleting or orphaning
  retained roles, agent responsibility mappings, provisioning evidence, or
  audit-referenced records. No script is prepared for execution.
- No reset migration: changes to tenant ownership, composite parent-child keys,
  trusted worker/reviewer identities, scoped reaper access, RLS, and execution
  cost/evidence ledgers require reviewed, versioned migrations, not ad hoc DDL.

Only read-only server/database catalog, row-count, role-definition and schema
metadata queries were performed. No business-row contents were exported, no
backup was taken or validated, no test suite was run, and no INSERT/UPDATE/
DELETE/TRUNCATE/ALTER/DROP/CREATE operation or migration was executed. Reopen
the audit only after the data owner confirms data provenance and role semantics,
and approves an export/restore destination. Keep RLS and reset readiness NO-GO.

## Milestone 1.1-G2/G3 — workforce mapping and retention export design (2026-11-04)

**G3 disposition: DESIGN COMPLETE FOR INDEPENDENT REVIEW. This does not
authorize export, backup creation, restore, migration, or cleanup.** G2
completed the read-only workforce/RBAC mapping that G1 had stopped before
completing. G3 records a specific allowlist, exclusions, owner-decision
register, dependency graph, restore validation plan, and future child-first
cleanup strategy in [Database_Retention_Export_Plan.md](./Database_Retention_Export_Plan.md).
The G1 stop and its evidence remain historical; G2/G3 do not imply owner
approval or data provenance.

### Verified target and database inventory

- At `2026-11-04 14:17:02.3288144 +04:00` (`10:17:02.3288144 UTC`), a
  SELECT-only `master` query reconfirmed server and machine
  `YOSLTVBILLU02`, target `AICompany` ONLINE, owner/original/current login
  `POM\Vemanasai.Billu`, and current login membership in `sysadmin`. The target
  matched the previously recorded local `localhost/AICompany` development
  target. This confirms endpoint identity only, not the data's classification
  or provenance. The connection was disconnected; do not use this sysadmin
  identity for export or cleanup. The detailed table/row inventory queries are
  dated 2026-11-04, but their individual execution timestamps were not retained;
  the later identity timestamp is not presented as the row-count capture time.
- The database inventory is 72 dbo user tables, 1,135 rows, 120 enabled and
  trusted FKs, 72 PKs, 16 unique constraints, 45 checks, 119 indexes, and 35
  empty tables. The completed G2 catalog inspection found one user-table
  identity column (`AuditLog.AuditLogID`); this supersedes G1's preliminary
  count of six. There are no user views, table triggers, temporal tables, or
  SQL Server RLS policies. No migration-history table was found.
- Workforce retention baseline: 56 Agent rows; 56 matching
  WorkforceRoleProfile rows; 38 Skill rows; 102 AgentSkill rows; Company 1,
  Department 22, Position 64, and three legacy Role rows. The G3 plan specifies
  the exact column allowlist and parent-first import order.
- One Agent (AI CEO) is Active; 55 are Provisioning. All model/version values
  are unconfigured and no provider is configured. All 102 AgentSkill
  assignments across 55 agents are Pending. Six agents have four open
  provisioning blockers each. AgentPermission, AgentTool,
  AgentKnowledgeAccess, Permission, Tool, and KnowledgeSource have no records.
- AI CEO's Agent and WorkforceRoleProfile JobDescription and
  ResponsibilitiesJson values differ. Preserve each source field exactly;
  obtain owner direction before any future reconciliation.

### RBAC and owner-decision gates

- The only active database Role codes are `USER` (31 AppUsers), `MANAGER`
  (6), and `SUPER_ADMIN` (2). Canonical roles and legacy aliases exist in
  application code, but canonical rows are absent from this database.
- No RolePermission table or Permission rows exist. Agent SecurityRoleID and
  ApprovalAuthorityID are null; no role-permission assignments may be inferred.
  AppUser.RoleID values resolve today but have no physical SQL FK. Functional
  workforce roles and application security roles remain separate.
- Owner disposition is unresolved for AgentActivationBlocker (24),
  AuditLog (257), Approval (7), OrganizationBootstrapRun (1),
  WorkforceRequest (36), Requirement/assessment chains, AppUser and related
  human-workforce records, notifications, recommendations, and governance or
  security evidence. The G3 plan records their counts, dependencies, and
  default REVIEW treatment. AppUser authentication data is excluded; never
  export password hashes or credential/secret values or references.
- No user table has authoritative TenantID/OrganizationID, existing CompanyID
  or DepartmentID is not tenant proof, and no SQL RLS policy exists.
  Migration 23 state is ambiguous without migration history. Tenant ownership,
  parent-child consistency, trusted worker/reviewer identities, and scoped
  reaper access require separately reviewed versioned migrations.

### G3 design, validation, and non-execution record

The proposed default export allowlist is Company, Department, Position, Skill,
WorkforceRoleProfile, Agent, AgentSkill, and Role, with exact columns and
original PKs specified in the G3 plan. Empty agent permission/tool/knowledge
catalogs are represented as schema/count metadata only. The plan includes the
complete table-level FK graph, per-table classification for all 72 tables,
owner approvals, secret exclusion, full backup and isolated restore
requirements, typed value/PK/FK checks, JSON preservation, and a conceptual
child-first cleanup sequence. It is not executable SQL and no cleanup script
was created.

The existing README conflict markers were inspected and left unchanged.
`AI_WORKFORCE_OS_MASTER_PLAN.md` and `ARCHITECTURE_DECISIONS.md` are not present
in `docs/`; no equivalent retention export plan existed before G3. No files
outside the requested documentation were changed for G3. No application or
SQL Server integration tests were run. Validation was read-only target
identity verification and SELECT-only schema/data inspection. No data or
schema changed; no export, backup, restore, migration, cleanup, or SQL write
was performed. Production RLS remains **NO-GO** and database cleanup remains
unapproved pending owner decisions and separate authorization.

### Milestone 1.1-G4 — independent retention-plan verification (2026-11-04)

**Outcome: CONDITIONAL PASS.** The current workforce export allowlist and full
table-level FK graph were independently compared with live `AICompany` using
Windows Integrated Authentication and SELECT-only queries. At
`2026-11-04 10:38:03.8854389Z`, a connection directly to AICompany confirmed
server/machine `YOSLTVBILLU02`, database
`AICompany` was ONLINE, owner and both original/current principal were
`POM\Vemanasai.Billu`, and `IS_SRVROLEMEMBER('sysadmin')` was `1`. The elevated
identity was not used for any mutation.

Process deviation: initial identity verification also used a SELECT-only
connection to `master` to read server/database catalog metadata, contrary to
the requested AICompany-only connection scope. No other user database was
accessed. Identity was subsequently reverified directly in AICompany, and all
schema/data inspection was performed there. This deviation is disclosed and
does not authorize any additional database access.

Live inventory matches all 72 G3 table names and per-table counts (1,135 rows,
35 empty tables): 120 enabled/trusted FKs, 72 PKs, 16 unique constraints,
45 checks, 119 indexes, and one identity (`AuditLog.AuditLogID`). There are no
cross-schema FKs, table triggers, user views/procedures, temporal tables, or
RLS policies. The 80 columns across the eight allowlist tables match exactly,
including names, SQL types, nullability, identity flags, and PKs; there are no
missing or undocumented columns. The six documented empty mapping/reference
tables also match their current schemas and remain empty.

G4 found and corrected two G3 documentation errors in
[Database_Retention_Export_Plan.md](./Database_Retention_Export_Plan.md):
Agent.CompanyID and DepartmentID are NOT NULL, but PositionID is nullable; and
the conceptual project cleanup text incorrectly described
ProjectDeliveryTask as depending on ResourceAssignmentRecommendation and omitted
complete child-first project ordering. The live dependency graph itself and
the 28 candidate dependency rows match. No migration ledger exists, so migration
23 application history remains unproven.

Workforce counts and integrity remain consistent: 56 Agents / profiles,
38 Skills, 102 pending AgentSkill rows, no missing descriptions or
responsibilities, no duplicate agent names, no orphaned profile/skill/manager/
director/reporting references, and 24 open activation blockers across six
agents. All Model and ModelVersion fields contain `UNCONFIGURED`; no
ModelProvider is set. The AI CEO Agent/profile job-description and
responsibility values still differ and were not reconciled.

Only active legacy roles `USER` (31 users), `MANAGER` (6), and `SUPER_ADMIN`
(2) exist; all 39 AppUser RoleID values resolve without a physical FK.
Canonical roles are absent. No RolePermission table, Permission rows, or
AgentPermission assignments exist. The 220 `sys.database_permissions` entries
are SQL-principal grants, not application role-permission mappings. Special
counts remain AuditLog 257, Approval 7, OrganizationBootstrapRun 1,
WorkforceRequest 36, Requirement 14, RequirementAssessment 8,
RequirementAssessmentDepartment 45, RequirementSkill 38, and AppUser 39.
Those and related human/operational records remain outside the default export
pending owner disposition. No credential, password-hash, token-hash, or
secret-reference values were queried or displayed.

The corrected eight-table restore order is technically feasible, and the JSON
configuration fields checked were valid. No export or backup was created, and
no isolated restore/value-hash validation was performed. Owner disposition,
data provenance, AI CEO authoring/hierarchy, an approved least-privilege
identity and encrypted destination, and separate export/backup/cleanup
authorization remain required. Cleanup and reset remain **NO-GO**; no
multi-tenant or production-readiness claim is supported.

G4 also reconfirmed the implementation/deployment limitations in the RLS
guide and relevant source: the database has no RLS policies; `get_db` sets only
`SESSION_CONTEXT(UserID)`, worker requests do not establish SQL worker/Agent
identity, and session-context clear failures are suppressed. No dedicated
least-privilege SQL API, worker, reviewer, or reaper principals/scopes have
been verified. Migrations 16-18 retain the old organization/department model
and migration 16's coverage guard; migration 27's optional RLS path retains
broad reaper owner-row visibility. Migration history is absent, so current
application status cannot be inferred from those scripts.

G4 inspected the required Markdown and relevant role/auth/migration sources.
`README.md` conflict markers remain unchanged; `AI_WORKFORCE_OS_MASTER_PLAN.md`
and `ARCHITECTURE_DECISIONS.md` are absent. No application tests were run.
All database statements were SELECT-only; no database rows or objects,
application code, configuration, migration state, backup, export, or restore
were changed or created.
