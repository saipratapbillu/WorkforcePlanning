# Native SQL Server RLS Deployment Guide

## Status

Do not deploy `sql/16_sql_server_rls_migration.sql` through `sql/18_sql_server_rls_rollback.sql` to the current application. They encode the former company/department access model, while the application now uses single-organization RBAC and does not require user organization mappings.

The latest recorded database snapshot found historical null normalized ownership, zero native security policies, and assignment/runtime tables not covered by the old migration. Those scripts remain disabled. Their coverage guard must not be bypassed. See [Single_Organization_RBAC_Migration_Plan.md](Single_Organization_RBAC_Migration_Plan.md) for current role semantics and deployment steps.

## Optional Organization Metadata

`CompanyID`, `DepartmentID`, and `PositionID` may be maintained for HR or future policy needs, but they are not runtime authorization or readiness requirements. `sql/19_app_user_org_mapping.sql` is an optional operator aid only; do not populate values by inference and do not block normal workflows when fields are null. `/ready` checks database connectivity, not organization metadata.

## Ownership Repair

1. Run `sql/17_sql_server_rls_validation.sql` and review all null/orphan ownership rows. Current known nulls are 1 Requirement, 1 Project, and 7 Tasks; re-run because counts may change.
2. Resolve records only from approved identity mappings. Do not infer an owner from display name, email, a related task, or free-text fields.
3. Re-run validation. Requirement, Project, Task, and Issue ownership must have no null or orphan GUIDs.

## Predicate Coverage Gate

The current migration covers Requirement, Project, Task, Issue, Approval, and Notification only. Before enabling any policy:

- Design and review policies for all existing assignment/runtime tables listed in validation script 17.
- Include AppUser/organization access patterns and any additional tenant-owned tables used by live APIs.
- Verify authenticated API requests establish SESSION_CONTEXT UserID on every pooled connection and worker requests use a separately reviewed trusted identity context.
- Test SELECT filtering and write-block predicates against Business User, assigned Approver, Executive, Workforce Manager, Platform Owner, and unknown-role scenarios.
- Define a separately reviewed trusted session-context contract and worker identity model.
- Measure representative query plans and concurrency with RLS enabled in a disposable DEV clone.

Do not enable policies until every required table is covered and ownership/role preflight checks and negative tests pass. Organization mapping completeness is not a prerequisite for the current single-organization role policy.

## Runtime isolation release gate (2026-11-03)

The current native policy draft is not deployable for the runtime schema:
`sql/16_sql_server_rls_migration.sql` deliberately aborts when runtime tables
exist, and its ownership predicate uses legacy role codes that differ from
those established by migration 23. Migration 27 does not add runtime-table
predicates and grants `RUNTIME_REAPER` broader owner-row visibility. No
reviewer-, worker-, or reaper-scoped policy has been verified.

The application sets only `SESSION_CONTEXT('UserID')`; worker authentication
does not currently establish an agent context. Cleanup clears only `UserID`
and suppresses errors, which is not sufficient evidence that pooled
connections cannot retain stale authorization context.

No disposable SQL Server URL or fixtures were available on 2026-11-03.
Migrations 23 and 27 were not applied, SQL Server RLS was not tested, and
rollback was not tested. Keep this release **NO-GO**. Do not weaken RLS or use
the broad reaper exception to make the application appear operational.

The local default instance is SQL Server 2022 Developer `16.0.1000.6` RTM with
mixed authentication. Existing online user databases `AICompany` and
`SharePoint` are unclassified and are treated as potentially live; neither was
opened. Backup history is empty, no `.bak`/`.bacpac` was found in the
repository/project parent, and access to the configured SQL backup directory
was denied. Before the harness-hardening work below, the integration suite committed
fixture mutations without general cleanup, so its name-prefix check was not a
sufficient safety boundary.
The user explicitly authorized a reduced-fidelity synthetic database under
`AICompany_M1_IT_`; that database has not been provisioned. Harden and review the
test harness before any future SQL Server test run. A synthetic schema validates
only that schema and does not establish production compatibility.

### Synthetic environment authorization update (2026-11-03)

Explicit authorization has now been provided for a new synthetic test database
under the `AICompany_M1_IT_` prefix; this is not authorization to modify an
existing application database or to remediate/deploy RLS. The exact candidate
`AICompany_M1_IT_20261103` was absent in a read-only `master` query. It was not
created or reserved. No RLS migration or integration test was run. The current
worker/reviewer/reaper predicates and identity context remain unresolved.
Milestone 1.1 remains **NO-GO**; the current task is authorized to design RLS
and harden the harness, but implementation and database provisioning remain
separate gates.

## Milestone 1.1-A: runtime RLS architecture (design; not implemented)

### Threat model and scope

- The SQL Server catalog is a single-organization application. `CompanyID`,
  `DepartmentID`, and `PositionID` are optional descriptive/HR fields under the
  canonical RBAC plan; there is no authoritative `TenantID` on `Requirement`,
  `Project`, `Task`, `Agent`, or runtime rows. Therefore cross-tenant isolation
  cannot be claimed or validated from this schema. If multi-tenancy is required,
  add a trusted tenant ownership key to the root records and enforce matching
  composite foreign keys down the graph before introducing tenant RLS.
- The threat model includes malicious/buggy API callers, compromised worker
  tokens, stale pooled SQL connections, and accidental use of the wrong
  database. It does not claim that RLS can protect against a compromised
  `sysadmin`, `db_owner`, database owner, or application process holding a
  broadly privileged shared SQL credential.
- Request-supplied `agent_id`, `execution_id`, `task_id`, `queue_id`, user IDs,
  and tenant IDs are selectors, never proof of identity. Derive the worker from
  the presented credential; derive the reviewer from the authenticated session
  or dedicated reviewer credential; bind each requested row to that principal
  and a current lease.
- `PLATFORM_OWNER` is not an implicit runtime bypass. Configuration/role
  administration and execution/review are distinct privileges. All privileged
  actions require narrowly scoped, audited procedures or explicit app policy.

### Canonical roles and compatibility

| Stored/effective code | Canonical meaning | Runtime authority |
| --- | --- | --- |
| `BUSINESS_USER` (`USER` alias) | Business requester | Own business records; no worker/reviewer/reaper access |
| `APPROVER` | Requirement approver | Assigned approval only; not runtime review |
| `EXECUTIVE` | Executive read-only | Approved aggregate/report access; no raw runtime bypass |
| `WORKFORCE_MANAGER` (`MANAGER`, `DEPARTMENT_HEAD`, `ADMIN` aliases) | Workforce management | Planning/assignment APIs; no review or reaper authority |
| `PLATFORM_OWNER` (`OWNER`, `SUPER_ADMIN` aliases) | Platform administration | Platform administration; no automatic RLS bypass |
| `RUNTIME_REVIEWER` | Dedicated independent reviewer | One currently leased execution, its selected output, related task/project/requirement, and one decision |
| `RUNTIME_REAPER` | Dedicated recovery principal | Expired-lease recovery procedure only |
| Unknown/inactive role | None | Deny |

`app/security/roles.py` canonicalizes legacy aliases for application checks.
`sql/23_single_organization_rbac.sql` creates canonical Role rows but does not
reassign legacy users. Migration 16 uses `USER`, `MANAGER`, `DEPARTMENT_HEAD`,
`OWNER`, and `SUPER_ADMIN`; migration 27 adds the service roles at `RoleLevel=5`.
Never authorize using `RoleLevel` ordering: service role levels are not a
privilege hierarchy. Reconcile assigned roles explicitly; do not infer mappings
from names, department, or email. `ADMIN` means `WORKFORCE_MANAGER` in the
application, not `PLATFORM_OWNER`.

### Principal and session-context contract

The existing `get_db` in `app/db/session.py` writes only `SESSION_CONTEXT(UserID)`
from web middleware state. It does not write worker identity, and its cleanup
currently suppresses context-clear errors. `/runtime/worker/*` authenticates a
hashed bearer token in `app/api/runtime.py`; `AgentID` comes from
`AgentRuntimeCredential`, not the caller's URL/body. These are application
controls, not proof of SQL RLS isolation.

Proposed future contract:

1. Use distinct SQL principals for the API, worker gateway, reviewer service,
   reaper, and migration/setup. None is `sysadmin`, `securityadmin`, `db_owner`,
   or the database owner. The migration principal is not used by the app/tests.
2. Runtime SQL principals receive `EXECUTE` on narrowly scoped signed
   procedures, not direct DML on runtime tables. The API runtime gateway verifies
   the bearer token; the SQL procedure independently maps a worker credential
   hash to its active AgentID and checks the task/queue/assignment/lease chain.
   The caller cannot choose the principal identity by supplying an AgentID.
3. Reviewer procedures map an authenticated reviewer principal to an active
   `AppUser` with exactly `RUNTIME_REVIEWER`, validate `ReviewOwnerUserID`,
   unexpired lease, and creator independence, then read the output and commit
   the decision atomically. Reject callers cannot supply a different reviewer
   ID.
4. The reaper connects as a separate principal and can execute only a procedure
   that selects/reclaims expired execution or review leases. It cannot read
   general owner-scoped business rows or manage credentials/configuration.
5. Session context may carry `PrincipalKind`, `UserID`, `AgentID`,
   `ExecutionID`, and (only after the schema has a real tenant key) `TenantID`.
   Context is established only after principal authentication and server-side
   relationship checks. Missing, malformed, inactive, contradictory, or stale
   context denies access.
6. Do not treat caller-settable `SESSION_CONTEXT` as an authentication
   boundary. Use `ORIGINAL_LOGIN()`/database-principal mapping or signed
   procedures to establish the principal; direct table DML must not be granted
   to an identity that can choose arbitrary context values.
7. `@read_only=1` is safe only for a physical connection permanently bound to
   one identity and context. It cannot be used on a pooled connection that
   changes user/agent/execution. For the existing dynamic pool, initialize and
   verify context on every checkout, clear it on every return, and invalidate
   (never return to the pool) a connection if clearing or verification fails.
   Prefer principal-partitioned pools and procedure-side lease checks.

The current shared API DB credential and code-set `UserID` do not independently
prove caller identity to SQL Server. This is a material gap: before claiming
protection against a compromised API/worker process, choose and test the
principal mapping/procedure-signing mechanism. Do not deploy a policy that
trusts arbitrary request parameters as context.

### Table-by-table policy design

For the table policies below, “select” is an RLS filter plus API/procedure
authorization; “insert/update block” means SQL Server block predicates and
procedure validation. No runtime principal receives direct `DELETE`. Audit
retention, if needed, is a separate approved operation. Platform Owner and
Workforce Manager receive no blanket runtime-table predicate.

| Table | Ownership/scope source | Worker | Reviewer | Reaper | Human/API and write rules |
| --- | --- | --- | --- | --- | --- |
| `Requirement` | Root owner `CreatedByUserID`; no tenant column | Only associated requirement reached through current execution's Task→Project | Only leased execution's task/project requirement | No access | Business-user owner policy; approver only assigned approval context; manager/owner business APIs remain explicit |
| `Project` | `CreatedByUserID`, parent Requirement | Only project of current leased task | Only project of current review task | No access | Owner-scoped business policy; no platform runtime bypass |
| `Task` | `CreatedByUserID`, parent Project, `AssignedAgentID` | Only assigned task whose TaskAssignment and queue are active and owned by authenticated agent | Only task of current review lease | No general task reads; update only by recovery procedure when required | Manager planning APIs are role-scoped; INSERT/UPDATE must preserve owner and project chain |
| `TaskAssignment` | `TaskID` + `AgentID` relationship | Own active assignment only; cannot create/change/release | No direct assignment access | No access | Manager assignment APIs only; block changes that break task/agent/project scope |
| `TaskDependency` | Both endpoints resolve to Tasks and same Project/tenant | Only dependencies for current task | No direct access except task context | No access | Manager planning API; block cross-project or cross-tenant edges |
| `AgentTaskQueue` | TaskID, AgentID, task assignment, lease status/expiry | Claim only queue rows assigned to the derived AgentID; heartbeat/submit only while lease is valid | No direct queue mutation | Only expired queue lease rows through recovery procedure | No direct CRUD; state transitions are procedure-owned |
| `AgentExecution` | QueueID, TaskID, AgentID, AttemptNumber; lease/review-owner columns | Own current execution and lease; no other agents/attempt data unless task context requires prior attempt reference | Only `Status='Review'`, `ReviewOwnerUserID` equals authenticated reviewer, lease unexpired; submit once | Only expired lease state needed for release/retry | No raw access for manager/owner; updates must preserve execution↔queue↔task↔agent consistency |
| `AgentExecutionOutput` | ExecutionID→AgentExecution | Insert output only for own live execution; read own output if required for correction | Read exactly output(s) for leased execution; hash verified before decision | No access | Immutable after insert; no delete/update; do not choose ambiguous artifact |
| `Evaluation` | AgentID and optional TaskID | No direct writes; may read only allowed evaluation result needed for own task gate | Read only task evaluation evidence in review package; no certification writes | No access | Evaluation producer/API is governed; reviewer cannot alter certification state |
| `Deliverable` | TaskID/ProjectID and approved output reference/hash | No approval or direct insert | Create only on approving its leased execution; unique artifact reference and approved hash | No access | Business/manager read follows project ownership; no direct runtime decision override |
| `AgentRuntimeEvent` | ExecutionID/QueueID/TaskID/AgentID references | Append only authenticated own events; limited read of own execution trail | Append review events; read leased task review evidence only | Append recovery events and minimal target rows | Append-only to runtime principals; no update/delete; query access is scoped |
| `AgentRuntimeEscalation` | QueueID/TaskID/AgentID | Read only own execution's escalation summary | Read only escalation connected to leased review if required; no resolve | Create/update only expiry-recovery escalation via procedure | Resolve/requeue through separately authorized human workflow, not RLS owner exception |
| `AgentRuntimeDefect` | ExecutionID/TaskID/AgentID | Read open correction context for own currently leased task; cannot create/close own defects | Create rejection defect for leased execution; read linked history | No access except defect state transition explicitly coupled to expiry recovery | Resolve/close via reviewed retest workflow; provenance is immutable |
| `AgentRuntimeCredential` | AgentID, credential status/hash | Never read hash; authentication procedure compares hash internally | No access | No access | Credential rotation/revocation is owner-only API/procedure; secret hashes never enter review/task output |
| `Agent` / `AgentPermission` / `AgentTool` / `AgentSkill` | AgentID and approved configuration | Read only own public runtime identity and approved capability data; no writes | Read agent metadata necessary for review; no configuration writes | No access except active-state check if recovery procedure needs it | Configuration/permission changes retain existing owner/manager API authorization; never grant via RLS role level |

Runtime tables listed in migration 17's coverage check are not presently
covered by a complete native policy. `AgentRuntimeCredential`,
`AgentRuntimeEvent`, `AgentRuntimeEscalation`, and `AgentRuntimeDefect` also
need explicit treatment beyond the current migration's table list. Rows without
a direct tenant column must inherit scope only through validated parent joins;
add constraints preventing mismatched Task/Queue/Agent IDs. A missing parent,
orphan row, expired lease, inconsistent ownership, or absent context fails
closed.

### Human/business role-operation matrix

| Principal | Business requirement/project/task data | Runtime raw rows | Claim/execute | Review/decision | Reaper/configuration |
| --- | --- | --- | --- | --- | --- |
| Anonymous | None | None | No | No | No |
| `BUSINESS_USER` | Own records only | None | No | No | No |
| `APPROVER` | Assigned approval and permitted context | None | No | Not a runtime reviewer | No |
| `EXECUTIVE` | Approved read-only/aggregate APIs | No raw rows by default | No | No | No |
| `WORKFORCE_MANAGER` | Workforce/planning APIs | No raw rows by default | No | No | No |
| `PLATFORM_OWNER` | Platform administration | No implicit RLS bypass; explicit audited operation only | No | No | No |
| `RUNTIME_REVIEWER` | None beyond a leased review package | One leased execution/output and related requirement | No | One independent decision; no self-review | No |
| Worker credential | None beyond assigned task context | Own active execution only | Claim assigned queue; heartbeat/output during valid lease | No | No |
| `RUNTIME_REAPER` | None | Expired lease rows through one recovery procedure | No | No | Narrow recovery only |
| Migration/setup principal | Setup only, controlled maintenance window | Not a runtime identity | No | No | No production runtime use |

### Migration/deployment dependency plan (proposed; nothing executed)

1. Preserve historical scripts. Do not edit migrations 16 or 27 in place.
2. Reconcile canonical `RoleCode` mappings and role assignments from migration
   23, without relying on `RoleLevel`. Decide whether the unused legacy role
   rows remain for compatibility; do not silently rewrite account mappings.
3. Establish trusted SQL principal mapping and procedure ownership/signing.
   `SESSION_CONTEXT(UserID)` alone is not sufficient. Fix pool cleanup to
   invalidate connections when reset fails.
4. Design and test a new additive migration (next sequence number, proposed
   migration 28) for principal mapping, composite integrity constraints,
   signed runtime procedures, and table-specific policies for every runtime
   and assignment table above. It must not include a broad `RUNTIME_REAPER`
   owner exception.
5. Keep `sql/14` and `sql/15` gated; their owner normalization and
   Company/Department/Position requirements do not align automatically with
   single-organization RBAC. Do not enable them merely to satisfy migration 16.
6. Migration 16's error 51206 is an intentional coverage guard; do not bypass
   it. Migration 16's old-role predicate also conflicts with migration 23.
   Migration 27 has idempotent column/role additions, but its optional policy
   replacement still encodes broad reaper access. Neither migration is ready
   for this runtime RLS design.
7. Apply a reviewed, dependency-ordered migration only in the new synthetic
   database, verify rollback and re-application there, then obtain a separate
   production change approval. Synthetic success is not production evidence.

### Required negative tests and go-live gates

Test missing/invalid identity and context; wrong worker token; forged AgentID;
another worker's task/output; expired and stale worker lease; assignment/task/
queue/execution AgentID mismatch; reviewer without exact role; unleased,
expired, reassigned, duplicate, or self-authored review; wrong task/output
association and altered artifact hash; reviewer write to Agent, credentials,
permissions, evaluations, assignment, or model configuration; reaper on live
leases/unrelated tasks/owner data; unknown role; `ADMIN` alias not becoming
owner; cross-tenant attempt (after tenant keys exist); missing parent; pooled
connection reuse after reset failure; and every table's SELECT/INSERT/UPDATE/
DELETE boundary.

Before any live model call or production runtime release, require actual SQL
Server integration evidence for every policy and operation, concurrent lease
claims, rollback, context isolation, no table omissions, minimum SQL grants,
and security review. No such evidence exists today.

## Milestone 1.1-B: integration harness hardening

`tests/integration/sqlserver_safety.py` now performs offline URL/fixture
validation before engine creation and verifies the connected SQL Server identity
and database marker before any test case. Required settings are
`RUNTIME_IT_DATABASE_URL`, `RUNTIME_IT_EXPECTED_DATABASE`,
`RUNTIME_IT_EXPECTED_SERVER_NAME`, `RUNTIME_IT_EXPECTED_LOGIN`,
`RUNTIME_IT_DATABASE_MARKER_ID`, `RUNTIME_IT_TEST_RUN_ID`,
`RUNTIME_IT_FIXTURE_JSON`, `RUNTIME_IT_SYNTHETIC_AUTHORIZED=1`, and
`RUNTIME_IT_CLEANUP_ENABLED=1`. The URL must explicitly select
`mssql+pyodbc`, local `localhost`, the exact approved synthetic database, no
embedded credentials, and trusted local authentication. Never log the URL.

The connected-target check compares `@@SERVERNAME`, `DB_NAME()`,
`SUSER_SNAME()`, database status/owner, `sysadmin` and `db_owner` membership,
and a setup-owned `dbo.RuntimeIntegrationDatabaseMarker`. The marker is
read-only to the test principal and binds a random marker ID to the exact
database name and purpose `synthetic-integration-only`; the marker's setup
principal must differ from the test principal. The database test principal
must have no UPDATE/INSERT/DELETE/ALTER rights on the marker. A database name
prefix alone is never accepted as proof.

Before tests, the harness acquires one database-wide SQL application lock and
snapshots all `dbo` table data (excluding the immutable marker). It streams rows
and fails closed if a table has no primary key, the snapshot exceeds 50,000
rows/64 MiB estimated UTF-8 representation size, or a foreign-key cycle prevents
safe ordering. It refuses enabled table triggers, temporal tables, and foreign
keys from another schema into `dbo`, because those can create state the snapshot
cannot restore. `tearDownClass` restores deleted and updated baseline rows,
deletes only newly added primary keys, compares all captured rows and table
definitions, and propagates cleanup errors as test failures. It does not drop a
database or alter schema. Run only on a fresh synthetic database unavailable to
application traffic. The lock serializes harness runs, not arbitrary application
SQL; external clients must not use the test database. Identity/sequence counters
and non-`dbo` state are not restored; treat the database as tainted and discard
it after the run. Cleanup is still not verified on SQL Server, so it is a gate
to validate, not evidence that recovery is infallible.

Fixture JSON now has `{"test_run_id":"<UUID>","data_classification":"synthetic-only","fixtures":{...}}` and must
provide all nine named test cases. The run ID must match the configured value.
The test user must be a dedicated trusted Windows identity, not a sysadmin,
db_owner, production application account, or shared human administrator.
Schema/setup permissions belong to a separate identity. Scope runtime grants
to the single synthetic database and provide only the SELECT/DML/schema metadata
permissions required by this test harness; do not grant server-wide roles.

The harness safety regression tests are offline unit tests. SQL Server
integration tests remain prohibited until separately authorized, provisioned,
and reviewed; none were run for this design task.

## Regression and Release

Run the Python test suite and RLS artifact checks before migration. Apply only in DEV after backup, maintenance approval, and a reviewed session-context gate. Re-run script 17 from a new authenticated session, run cross-company negative tests, and verify the application is ready before promoting the exact reviewed artifact.

## Milestone 1.1-G — AICompany reset audit gate (2026-11-04)

The local `AICompany` catalog was inspected read-only after verifying
`@@SERVERNAME`/`MachineName=YOSLTVBILLU02`, local `COMPUTERNAME` agreement,
SQL Server Developer `16.0.1000.6`, integrated current login/database owner,
and the repository's `localhost/AICompany` setting. This confirms the configured
local target, not the provenance or non-production classification of its rows.
The current login is sysadmin. The audit executed only SELECT queries.

Catalog summary: 72 user tables (all `dbo`), 1,135 rows, 120 foreign keys, 72
primary keys, 16 unique constraints, 45 check constraints, 119 indexes, 6
identity columns, no table triggers, and no temporal tables. `msdb` reported no
backup history for `AICompany`. The current `Role` rows are legacy `USER`,
`MANAGER`, and `SUPER_ADMIN`; migration 23 canonical rows were not present.
The only catalog FK among the inspected agent/RBAC role columns is
`Agent.WorkforceRoleCode -> WorkforceRoleProfile.RoleCode`. Agent
`SecurityRoleID` and `ApprovalAuthorityID` lack FKs; no Role-permission mapping
table was found, and `Permission` is empty. The Agent security/approval role
relationships and retention boundary are therefore ambiguous.

Per the required stop conditions, no full dependency-cycle audit, retention
export, cleanup SQL, or data reset was prepared. Do not treat the current
`AICompany` database as a backup source or disposable environment based only on
its local name/instance. Resolve data provenance, role semantics, user/PII and
audit retention, and agent-role references with the data owner first. Then
produce a separate verified backup/export and restore test before any reviewed
cleanup proposal. No DDL, DML, migration, or cleanup was executed. Milestone
1.1-G is **NOT READY** for human approval of a destructive cleanup plan; RLS
and tenant-isolation deployment remain **NO-GO**.
