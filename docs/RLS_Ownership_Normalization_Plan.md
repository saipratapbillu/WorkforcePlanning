# Ownership Normalization And RLS Plan

**Status:** Schema analysis and unexecuted design draft. **No `ALTER TABLE`, backfill, constraint, or RLS DDL has been executed.**  
**Schema authority:** User-attached SQL Server column inventory, cross-checked using read-only `sys` catalog queries against local `AICompany`. This plan reuses `Company`, `Department`, `Position`, `Agent`, `AppUser`, `Role`, and current parent FKs; it does not recreate organization tables.

**Approved execution scope update:** The only approved ownership DDL gaps are `Requirement.CreatedByUserID`, `Project.CreatedByUserID`, `Task.CreatedByUserID`, and `Issue.OwnerUserID`. Use [14_approved_ownership_normalization.sql](../sql/14_approved_ownership_normalization.sql) as the sole generated SQL package for this approval. Earlier candidate fields on `AppUser`, `WorkforceRequest`, `Risk`, `KnowledgeSource`, and `Skill` remain analysis-only and are not altered by that package. `Issue.Owner` is retained during expand/backfill/rollback; dropping it requires a later contract migration after API cutover and review.

## Executive Summary

The organization backbone is already present and largely referentially sound: `Department.CompanyID → Company.CompanyID`; `Position.DepartmentID → Department.DepartmentID`; `Agent.CompanyID → Company.CompanyID`, `Agent.DepartmentID → Department.DepartmentID`, and optional `Agent.PositionID → Position.PositionID`. Agent department/company and position/department consistency checks returned zero mismatches. All sampled existing FKs were trusted/enabled. SQL Server has **zero security policies**.

The principal gap is the missing link between a signed-in `AppUser` and that hierarchy. `AppUser` has `RoleID`, `ManagerUserID`, and a free-text `Department`, but no `CompanyID`, `DepartmentID`, or `PositionID`. Its `RoleID` has no declared FK in the live database; current three-user data had no active user with a missing/orphan/inactive Role row, but future integrity is not enforced. `Approval` has GUID columns for Requirement and assigned user, but **no declared FKs** in the live database.

The five requested text ownership fields need normalization, while preserving their text columns during an expand/contract release. Direct GUID matching is only partially available. No Department text on the three existing AppUsers matched exactly one Department name, so do not infer membership from the label. Position cannot be backfilled from the attached AppUser shape because it has no position label.

## 1. Gap Analysis

| Area | Observed schema | Gap / consequence |
| --- | --- | --- |
| Principal tenant membership | `AppUser(UserID, RoleID, ManagerUserID, Department nvarchar)` | No Company/Department/Position GUID membership; cannot resolve USER/manager/department-head/executive scope from a principal row. Department text is not a safe key. |
| Organization hierarchy | Company → Department → Position; Agent contains company, department, optional position IDs | Good base path and FKs exist. Agent checks had zero cross-hierarchy mismatches. AppUser is not connected to it. |
| User-created requirements | `Requirement.CreatedBy nvarchar` | No FK or reliable user owner key. Only 1 of 5 strings directly parses/matches an AppUser GUID; 0 match email; 0 match exactly one display name. |
| User-created projects | `Project.RequirementID` FK plus `CreatedBy nvarchar` | Parent relationship is usable; 1 of 2 creator strings directly matches an AppUser GUID. Preserve creator-level scope, do not assume the linked requirement owner is always the project author. |
| User-created tasks | `Task.ProjectID` FK plus `CreatedBy nvarchar` | Parent path is usable; 7 of 14 creator strings directly match AppUser GUIDs. Others require explicit source-of-truth mapping or quarantine. |
| Issue owner | `Issue.ProjectID` FK plus nullable `Owner nvarchar` | `Issue` currently has 0 rows. `Owner` may be display text; no email/GUID matches to backfill. Add nullable user FK only after defining whether Owner means assignee or reporter. |
| Workforce requester | `WorkforceRequest.ProjectID`, optional `TaskID`, and `RequestedBy nvarchar` | All 6 current values directly match AppUser GUIDs, but there is no FK. Add a GUID requester key and preserve RequestedBy as legacy/audit label. |
| Approval | `RequirementID`, nullable `AssignedToUserID`, status/decision data | The fields are GUID-shaped but there are no declared Approval FKs. Scope should be assignee OR authorized visibility through the linked requirement; decision authority remains separate. |
| Notifications | `Notification.UserID` | Direct user GUID with an existing FK to AppUser: structurally ready for recipient-only row isolation. Manager visibility must not widen notification inbox access by default. |
| Comments / attachments | No Comment or Attachment table occurs in the attached inventory | Do not add policies for nonexistent tables. If these features are later introduced, include tenant/parent ownership at design time. |
| SQL Server RLS | `sys.security_policies` is empty | All current row filtering is application-level. No database-enforced RLS is active. |
| Existing row volume | AppUser 3; Requirement 5; Project 2; Task 14; Issue 0; WorkforceRequest 6; Approval 2; Notification 33; Company 1; Department 22; Position 64; Agent 56 | Small current volume, but migration/backfill must still be staged and auditable. Do not treat the single current company as a permanent single-tenant assumption. |

### Existing relationship facts

- Declared: Department → Company; Position → Department; Agent → Company, Department, Position, ManagerAgent, WorkforceRoleProfile; AppUser → ManagerUser; Project → Requirement; Task → Project, ParentTask, AssignedAgent; Issue → Project; WorkforceRequest → Project, Task, agents and role profile; Notification → AppUser.
- Missing in current DB: AppUser.RoleID → Role; Approval.RequirementID → Requirement; Approval.AssignedToUserID → AppUser. Add only after orphan checks and explicit migration review.
- Existing single-column FKs do not prove cross-column consistency: Agent.CompanyID could theoretically disagree with Agent.DepartmentID's CompanyID or Agent.PositionID's DepartmentID. The present data check found zero mismatches, but future rows need composite constraints or controlled write validation.
- No CompanyID/DepartmentID should be copied to every business table. Use AppUser’s membership as the principal scope and existing parent FKs for child rows. Add direct creator GUIDs only to user-owned root records required by the policy.

## 2. Tables Requiring Ownership Normalization

### Required principal membership keys

`AppUser` needs nullable expansion columns, followed by reviewed backfill and later constraints:

- `CompanyID uniqueidentifier`: user tenant membership and executive/company scope.
- `DepartmentID uniqueidentifier`: manager and department-head scope. A separate department key is needed even where Position is absent.
- `PositionID uniqueidentifier NULL`: optional HR/organizational position assignment.

Reuse `Company`, `Department`, and `Position`; do not create duplicate organization tables. Keep the existing `Department` text field during transition, but stop using it for authorization.

### Required ownership GUIDs

- `Requirement.CreatedByUserID uniqueidentifier`: non-null after unresolved legacy rows are mapped/quarantined.
- `Project.CreatedByUserID uniqueidentifier`: retain `RequirementID` as relationship; this is creator ownership, not a duplicated CompanyID.
- `Task.CreatedByUserID uniqueidentifier`: retain `ProjectID`; creator ownership is distinct from `AssignedAgentID`.
- `Issue.OwnerUserID uniqueidentifier NULL`: initially nullable because `Owner` is nullable and currently Issue has no rows. Product owner must confirm whether `Owner` is a responsible owner, creator, or assignee before conversion.
- `WorkforceRequest.RequestedByUserID uniqueidentifier`: all 6 current strings are exact AppUser GUIDs; still add as nullable first and validate before enforcing non-null.

For each field, keep the current text column through at least one release. API writes both fields transactionally during transition; reads/authorization use GUID only after validation.

### Actor/audit strings not to convert blindly

These are not automatically ownership keys and can represent a system, agent, human, or descriptive business owner. Preserve their existing meaning unless a separately approved actor model is designed:

- `AuditLog.ActorType + ActorID`: explicitly polymorphic (`User`, `Agent`, `System`, etc.); retain the discriminator, optionally add nullable `ActorUserID` / `ActorAgentID` with consistency rules later.
- `Agent.CreatedBy` / `ModifiedBy`, `AgentRuntimeCredential.CreatedBy`, `AgentRuntimeEvent.ActorID`, `AgentRuntimeEscalation.ResolvedBy`, `RequirementAssessment.CreatedBy`, `Requirement.ModifiedBy`, `Project.ModifiedBy`, `Task.ModifiedBy`, `WorkforceRequest.DecisionBy`: audit actor fields, not row owner columns.
- `Project.BusinessOwner`, `Risk.Owner`, `KnowledgeSource.Owner`, `Skill.Owner`: semantic label/ownership may refer to a department, agent, or external party. Define semantics before creating GUID keys.
- `Requirement.RequestedBy` is presentation/requester text; use `CreatedByUserID` for identity and retain RequestedBy as a snapshot/display label.

## 3. Tables Already RLS-Ready

“RLS-ready” here means a usable key/path exists; it does **not** mean a policy is installed or that the whole access matrix is complete.

| Readiness | Tables/paths | Notes |
| --- | --- | --- |
| Tenant root | Company | `CompanyID` primary key is the root boundary. Principal-to-company mapping is absent until AppUser membership is normalized. |
| Direct hierarchy tenant key | Department | `CompanyID` FK to Company supports company filtering. |
| Parent hierarchy key | Position | `DepartmentID` FK; company derives through Department. No need for Position.CompanyID. |
| Agent tenant and org keys | Agent | CompanyID/DepartmentID and optional PositionID are GUIDs with FKs. Add composite consistency protection; no user ownership is implied. |
| Recipient-only | Notification | UserID FK to AppUser supports the recipient's personal inbox. Do not widen to department-wide by default. |
| Parent-scope only | Project, Task, Issue, WorkforceRequest | Existing requirement/project/task FKs give a parent path, but these tables are not user-owner-ready until GUID ownership is added and validated. |
| GUID columns, missing FK enforcement | Approval | AssignedToUserID and RequirementID exist but no Approval FKs are declared. Add after integrity preflight. |
| Not RLS-ready | AppUser | No tenant/department/position keys. ManagerUserID supports direct-report relation but not department/company scope by itself. |
| Not present | Comment, Attachment | No such tables in source inventory; do not create policies for them in this migration. |

Other operational child tables should use the appropriate existing parent path rather than duplicate CompanyID: RequirementAssessment/RequirementSkill/RequirementAssessmentDepartment through Requirement; ProjectAgent/Risk/Decision/Budget/Deliverable/Issue through Project; TaskAssignment/TaskDependency/AgentExecution/AgentCost through Task or Agent; AgentRuntimeExecutionOutput through Execution; agent skills/permissions/tools/credentials/performance/knowledge access through Agent. Tables with nullable multiple parent references (for example SecurityIncident, Budget, AgentRuntimeEvent, AgentCost) need a “must have at least one authorized parent” rule or a dedicated scoped owner key; null parent references must not become an implicit allow.

Global catalogs (Role, Permission, Policy definitions, Skill, Tool, WorkforceRoleProfile, GovernanceGateProfile, escalation policy definitions) are not user-owned records. Keep them global and protect administration through backend authorization; do not attach a user-data RLS policy merely because they are queried by the app.

## 4. Migration Plan (Draft Only)

No script in this plan has been executed. Use expand → map/backfill → validate → dual-read/write → RLS enable → contract. Do not drop text columns in the same release that adds GUID columns.

### Phase 0: preflight and frozen baseline

1. Snapshot database and capture schema/constraint/index inventory.
2. Export counts and stable primary keys for the five ownership tables and AppUser.
3. Record FK orphans, active users with invalid RoleID, organization hierarchy mismatches, null/duplicate ownership keys, and all backfill candidate classifications.
4. Confirm business role mapping for `USER`, `MANAGER`, `DEPARTMENT_HEAD`, `EXECUTIVE`, `OWNER`, and `SUPER_ADMIN`; current database only has three Role rows, so new roles must be approved and inserted into existing Role, not recreated.
5. Product owner resolves whether Issue.Owner means assignee or creator and how unassigned issues are visible.

### Phase 1: additive nullable expansion

Draft additions only:

```sql
-- DRAFT ONLY. Do not execute until reviewed and scheduled.
ALTER TABLE dbo.AppUser ADD CompanyID uniqueidentifier NULL;
ALTER TABLE dbo.AppUser ADD DepartmentID uniqueidentifier NULL;
ALTER TABLE dbo.AppUser ADD PositionID uniqueidentifier NULL;

ALTER TABLE dbo.Requirement ADD CreatedByUserID uniqueidentifier NULL;
ALTER TABLE dbo.Project ADD CreatedByUserID uniqueidentifier NULL;
ALTER TABLE dbo.Task ADD CreatedByUserID uniqueidentifier NULL;
ALTER TABLE dbo.Issue ADD OwnerUserID uniqueidentifier NULL;
ALTER TABLE dbo.WorkforceRequest ADD RequestedByUserID uniqueidentifier NULL;
```

Add indexes after validating query plans. Do not add CompanyID to Requirement, Project, Task, Issue, or WorkforceRequest: tenant scope derives from the normalized creator's AppUser membership. Keep existing organization tables and keys.

### Phase 2: reviewed mapping table and backfill candidates

Use a durable migration-only map with `EntityType`, `EntityID`, `UserID`, `CompanyID`, `DepartmentID`, `PositionID`, `MatchBasis`, `ReviewStatus`, `ReviewedByUserID`, `ReviewedAtUtc`, and `ReviewNote`. Its primary key is `(EntityType, EntityID)`; FKs target existing AppUser/Company/Department/Position. Restrict writes to migration operators, audit every decision, and drop/archive only after sign-off.

Candidate generation rules:

1. Safe automatic candidate: `TRY_CONVERT(uniqueidentifier, LegacyText)` equals exactly one existing AppUser.UserID. Mark as `AutoCandidate`, not yet applied.
2. Email or exact display-name mapping: never auto-apply. Current read-only check found zero such matches. If future rows match, require unique match and human approval.
3. Parent-derived candidate for Project/Task: only propose when the parent owner is already validated **and** business rules confirm creator should inherit that owner. Keep separate `MatchBasis='ParentOwnerProposal'`; require approval. Do not assume a task's creator equals its requirement owner.
4. `AppUser.Department` exact-name mapping: current check found 0 unique matches across Department. Do not map labels by fuzzy matching. Use an HR-approved `AppUser → Company/Department/Position` source file/map.
5. PositionID has no source text in AppUser. Backfill only from an approved HR source or leave NULL.
6. Unmatched/ambiguous rows remain NULL in new columns and are quarantined from USER RLS until reviewed; never assign them to a default tenant/user.

Measured candidate baseline (read-only, current local DB):

| Legacy field | Rows | Existing AppUser GUID matches | Email matches | Unique display-name matches |
| --- | ---: | ---: | ---: | ---: |
| Requirement.CreatedBy | 5 | 1 | 0 | 0 |
| Project.CreatedBy | 2 | 1 | 0 | 0 |
| Task.CreatedBy | 14 | 7 | 0 | 0 |
| Issue.Owner | 0 | 0 | 0 | 0 |
| WorkforceRequest.RequestedBy | 6 | 6 | 0 | 0 |
| AppUser.Department → Department.DepartmentName | 3 users with text | 0 unique matches | n/a | n/a |

### Phase 3: integrity and FK constraints

After candidate review and backfill only:

- Add `AppUser.CompanyID → Company.CompanyID`.
- Add `AppUser.DepartmentID → Department.DepartmentID` and `AppUser.PositionID → Position.PositionID`.
- Enforce organization consistency. The cleanest normalized form is composite unique keys on existing `(DepartmentID, CompanyID)` and `(PositionID, DepartmentID)` plus composite FKs from AppUser `(DepartmentID,CompanyID)` and `(PositionID,DepartmentID)`. This does not copy company/department onto all business tables; it prevents inconsistent principal memberships.
- Add FKs from the five new owner GUID columns to `AppUser.UserID`.
- Add the missing AppUser.RoleID → Role.RoleID FK and missing Approval RequirementID/AssignedToUserID FKs only after orphan checks; current three users have no null/orphan/inactive role references, but the database currently does not enforce RoleID.
- Keep `Issue.OwnerUserID` nullable unless the business policy makes every Issue assigned.
- Add trusted constraints only after a zero-orphan validation. Avoid `WITH NOCHECK` as a way to make migration pass.

### Phase 4: API dual-write and authorization transition

- Auth middleware derives UserID from validated session, loads active AppUser + Role, and reads CompanyID/DepartmentID/PositionID from SQL; never accepts them from request JSON/JWT claims as authoritative membership.
- Requirement create: set CreatedByUserID from current AppUser.UserID; retain CreatedBy as a legacy snapshot during transition.
- Project/task/workforce-request creates: persist GUID owner/requester from authenticated actor; keep text columns synchronized for old readers during a bounded compatibility period.
- Issue API: accept an owner user ID only after checking caller permission and valid assignee scope; do not accept arbitrary Owner text as authorization.
- Create/list/detail/update/delete predicates use stable GUID keys and parent links. Approval decision authorization remains assigned approver or governed Owner/Super Admin as current policy permits.
- Expand tests and verify old and new reader results reconcile before switching reads to GUID fields.

### Phase 5: table-specific RLS enablement

Establish one trusted DB session principal per request/transaction using `SESSION_CONTEXT('UserID')`, set only after API JWT/session validation, and clear it in a `finally` block before pooled connection return. Role and org memberships are re-read from AppUser/Role in SQL; do not trust client-supplied `RoleCode`, `CompanyID`, or `DepartmentID`. Missing/invalid context fails closed. The application DB credential must not be exposed to browsers or workers.

Policy matrix (not a generic blanket policy):

| Table family | Predicate input/path | Scope rule |
| --- | --- | --- |
| AppUser | UserID; actor's org in AppUser | USER own; MANAGER/DEPARTMENT_HEAD same department and company; EXECUTIVE/OWNER same company; SUPER_ADMIN all. |
| Company | CompanyID | Current principal's CompanyID; SUPER_ADMIN all. |
| Department | CompanyID | Same-company hierarchy; department roles restricted to own DepartmentID where the row permits. |
| Position | DepartmentID → Department.CompanyID | Same company; MANAGER/DEPARTMENT_HEAD same department; EXECUTIVE/OWNER same company; SUPER_ADMIN all. |
| Agent | Existing CompanyID/DepartmentID/PositionID | Same company for executive/Owner; same department for department roles; SUPER_ADMIN all. Verify org IDs are consistent. |
| Requirement | CreatedByUserID | USER own; manager/department head by creator's DepartmentID; executive/Owner by creator's CompanyID; SUPER_ADMIN all. |
| Project | CreatedByUserID plus RequirementID integrity | Same owner hierarchy; require project creator and linked requirement ownership to be consistent by policy. Do not authorize via text CreatedBy. |
| Task | CreatedByUserID plus ProjectID integrity | Same owner hierarchy; linked Project and Requirement must be accessible; AssignedAgentID does not grant a human user access. |
| Issue | OwnerUserID and ProjectID | Owner may see assigned issue; project access is also required. Null owner does not imply public visibility. |
| WorkforceRequest | RequestedByUserID, ProjectID, optional TaskID | Requester hierarchy plus authorized project/task path; recruiting decisions remain governed. |
| Approval | AssignedToUserID OR RequirementID → Requirement.CreatedByUserID | Assignee may see their approval; requirement owner may view its approval; decision permission remains separately enforced. |
| Notification | UserID | Recipient only; SUPER_ADMIN access only when explicitly approved for audit. Manager/executive do not inherit inbox visibility. |
| Requirement assessments/skills/departments | RequirementID → Requirement | Inherit requirement scope. |
| Project children (ProjectAgent, Risk, Decision, Budget, Deliverable, Issue) | ProjectID → Project | Inherit project scope; Budget with DepartmentID must satisfy both scopes if both are populated. |
| Task children (Assignment, Dependency, Execution, Cost, output) | TaskID/ProjectID → Task → Project | Inherit task/project scope; Agent access is a separate worker authorization path. |
| Agent/runtime records | AgentID or TaskID/QueueID/ExecutionID parent path | Tenant/department scope from Agent or task parent; records with all nullable parent IDs must fail closed or get a normalized owner key before RLS. |
| Global catalogs | no tenant owner | Not row-filtered as user content; write APIs restricted to governance roles. |

Policies should use separate inline table-valued predicates for `fn_UserScope`, `fn_CompanyScope`, `fn_DepartmentScope`, and table-specific parent-scope functions for Approval, Requirement children, Project children, and Task/runtime children. Add both filter predicates and appropriate insert/update block predicates. Do not create one generic predicate with an optional NULL owner that returns allow. Resolve the exact SQL function/security-policy syntax in a scratch database and test it before production.

### Phase 6: contract/deprecation

After all application versions, jobs, reports, and integrations read GUID ownership and RLS is verified, stop dual-writing legacy values. Keep text columns for one retention window; then schedule separate archive/drop work only after owner approval. This migration does not drop any column.

## 5. Backfill Plan And Script Shape

The following is the only automatic backfill candidate rule suitable without additional business evidence. It intentionally matches **only a valid AppUser GUID already stored as text**. It is a draft; do not run it until expansion, backup, approval-map creation, and exact candidate review.

```sql
-- DRAFT ONLY. Not executed in this analysis.
-- Run only after nullable GUID columns and the approved migration map exist.
SET XACT_ABORT ON;
BEGIN TRANSACTION;

UPDATE r SET CreatedByUserID=u.UserID
FROM dbo.Requirement r
JOIN dbo.AppUser u ON u.UserID=TRY_CONVERT(uniqueidentifier,r.CreatedBy)
WHERE r.CreatedByUserID IS NULL;

UPDATE p SET CreatedByUserID=u.UserID
FROM dbo.Project p
JOIN dbo.AppUser u ON u.UserID=TRY_CONVERT(uniqueidentifier,p.CreatedBy)
WHERE p.CreatedByUserID IS NULL;

UPDATE t SET CreatedByUserID=u.UserID
FROM dbo.Task t
JOIN dbo.AppUser u ON u.UserID=TRY_CONVERT(uniqueidentifier,t.CreatedBy)
WHERE t.CreatedByUserID IS NULL;

UPDATE i SET OwnerUserID=u.UserID
FROM dbo.Issue i
JOIN dbo.AppUser u ON u.UserID=TRY_CONVERT(uniqueidentifier,i.Owner)
WHERE i.OwnerUserID IS NULL;

UPDATE w SET RequestedByUserID=u.UserID
FROM dbo.WorkforceRequest w
JOIN dbo.AppUser u ON u.UserID=TRY_CONVERT(uniqueidentifier,w.RequestedBy)
WHERE w.RequestedByUserID IS NULL;

-- Review counts and mapping exceptions before any constraint enforcement.
SELECT 'Requirement' AS Entity,COUNT(*) AS Unmapped FROM dbo.Requirement WHERE CreatedByUserID IS NULL
UNION ALL SELECT 'Project',COUNT(*) FROM dbo.Project WHERE CreatedByUserID IS NULL
UNION ALL SELECT 'Task',COUNT(*) FROM dbo.Task WHERE CreatedByUserID IS NULL
UNION ALL SELECT 'Issue',COUNT(*) FROM dbo.Issue WHERE Owner IS NOT NULL AND OwnerUserID IS NULL
UNION ALL SELECT 'WorkforceRequest',COUNT(*) FROM dbo.WorkforceRequest WHERE RequestedByUserID IS NULL;

-- COMMIT only after operator verifies the exact eligible rows and captures the map/audit.
ROLLBACK TRANSACTION; -- safety default for this review draft; replace only in an approved runbook.
```

For production backfill, replace direct commit with an approved migration runner that applies reviewed `RlsOwnershipBackfillMap` rows, records operator/evidence, emits before/after counts, and commits in batches. Preserve old text values. Do not use a broad `UPDATE ... COALESCE(...parent owner...)` or match by non-unique DisplayName. The draft ends with ROLLBACK intentionally so copying it cannot persist changes accidentally.

## 6. Rollback Plan

- **Before RLS:** stop deployment; leave new GUID columns nullable, keep old application version and text columns; no data loss. Remove only new nullable columns/indexes/FKs if and only if they are unused and a reviewed cleanup is approved. Prefer leaving unused columns over hurried destructive rollback.
- **After backfill but before RLS:** switch application reads back to legacy text behind a feature flag; retain GUID backfill and mapping evidence. Do not overwrite or delete text values. Correct erroneous mappings from the mapping ledger, then rerun reconciliation.
- **After API dual-write:** roll back API binaries only if the old version can safely ignore new nullable columns; keep dual-written columns and constraints. Do not turn off owner checks while any endpoint can return cross-user rows.
- **After RLS enablement:** first place affected endpoints in maintenance/deny mode. Validate alternate API authorization before disabling a policy. Never disable RLS on a live path simply to restore availability. If policy defect is isolated, replace the predicate under change control; retain fail-closed behavior.
- **Constraint rollback:** drop only newly added named constraints after traffic is drained and API feature flags are rolled back. Do not drop the pre-existing Company/Department/Position/Agent or parent FKs.
- **Final contract/drop:** separate later release with backup, retention approval, consumer inventory, and point-in-time restore test. Not part of this migration.

## API Changes To Build After Schema Approval

- Authentication context object should carry only server-loaded `UserID`, `RoleCode`, `CompanyID`, `DepartmentID`, `PositionID`, and active state. Update `get_current_user` to join/validate RoleID FK and membership. Missing context denies access.
- Replace `CreatedBy` filters in requirements/project/task APIs with GUID columns. Keep output `created_by` as a display projection sourced from AppUser, not as an authorization value.
- `POST /requirements`, project/task factories, and workforce planner set new owner/requester GUIDs from authenticated context. Never accept these IDs from payloads without an authorized delegation workflow.
- Add role scopes centrally: USER self; MANAGER and DEPARTMENT_HEAD department (subject to approved reporting semantics); EXECUTIVE and OWNER company; SUPER_ADMIN all. Existing approval authorization and agent governance gates remain independent.
- Add repository predicates to list/detail/update/delete, nested relationships, search, counts, exports, and dashboard endpoints. Return 404 for inaccessible foreign record IDs where enumeration prevention is required.
- Connection middleware sets `SESSION_CONTEXT('UserID')` from validated identity in the transaction and clears it in `finally`, including exception/rollback. Add tests for pooled-connection reuse. Role is read from SQL, not copied into an authoritative context flag.

## Regression Tests To Require Before Enablement

1. Schema preflight: every new column exists nullable; each intended FK/index exists; no organizational tables were recreated; existing FKs remain trusted.
2. Backfill exactness: mapped GUID equals AppUser.UserID; string remains unchanged; email/name/unmatched values are not auto-mapped; duplicate/ambiguous membership stays quarantined.
3. Hierarchy: AppUser company/dept/position composite relationships reject cross-company department and cross-department position; Agent org consistency remains enforced.
4. Role matrix: USER sees own records only; MANAGER/DEPARTMENT_HEAD see their approved department scope only; EXECUTIVE/OWNER see same-company scope only; SUPER_ADMIN sees all. Test both allow and deny for list, detail, update, delete, joins, counts, and exports.
5. Parent inheritance: project/task/issue/workforce request and all listed child tables cannot leak via alternate endpoint or parent ID; null parent references fail closed.
6. Approval: assigned approver visibility vs requester visibility; decision authority remains assigned user/Owner/Super Admin per governance; no approval bypass from department or executive visibility.
7. Notification: only recipient sees notification; mark-read cannot change another user's notification.
8. SQL Server RLS: no context→deny; malformed/stale context→deny; pooled connection context cleared after success, exception, rollback, cancellation; direct SQL under app principal still filters.
9. RLS interaction: joins/subqueries, FK checks, `OUTPUT`, bulk operations, migration principal, system worker principal, and Super Admin route are verified under enabled policies.
10. Rollback: application rollback preserves text/GUID reconciliation and does not expose rows; RLS rollback occurs only in maintenance/deny mode.

## Execution Boundary

All database work in this analysis was catalog/read-only SELECT. The draft backfill explicitly rolls back. No `ALTER TABLE`, `CREATE SECURITY POLICY`, `UPDATE`, or `DELETE` was executed. The next approval gate is review of this plan, membership source-of-truth, Issue.Owner semantics, and role semantics before generating an executable migration package.
