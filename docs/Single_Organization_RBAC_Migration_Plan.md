# Single-Organization RBAC Migration Plan

## Policy

The application operates as one organization. Company, Department, and Position data are optional descriptive metadata, not prerequisites for login, request/project/task access, workforce planning, agent assignment, or readiness. Existing columns, tables, foreign keys, ownership GUIDs, and organization-mapping tools remain available for compatibility and future use.

| Role | Normal access |
| --- | --- |
| Business User | Create and read own requirements, projects, and tasks; read own notifications; cannot decide another user's approval. |
| Approver | Read assigned approvals and related owner-scoped business records; decide only approvals assigned to them. |
| Executive | Organization-wide read-only business and executive dashboards. |
| Workforce Manager | Organization-wide workforce, capacity, planning, task, and agent lifecycle operations. |
| Platform Owner | Administrative oversight and controlled platform-wide override. |

Unknown or unassigned roles remain denied. Notifications remain recipient-scoped, except Platform Owner oversight. The frontend is not an authorization boundary; API dependencies enforce every role check.

## Compatibility Crosswalk

The application resolves old role codes to canonical roles at the authorization boundary. Database role IDs and assignments are not rewritten by migration 23.

| Existing role code | Effective role |
| --- | --- |
| `USER` | `BUSINESS_USER` |
| `MANAGER`, `DEPARTMENT_HEAD`, `ADMIN` | `WORKFORCE_MANAGER` |
| `EXECUTIVE` | `EXECUTIVE` |
| `OWNER`, `SUPER_ADMIN` | `PLATFORM_OWNER` |

`APPROVER` is assigned explicitly; there is no legacy approver code. Review existing Manager, Department Head, and Admin accounts before rollout because their effective scope becomes organization-wide Workforce Manager access. Do not infer an account's role from its name, department, position, or email.

## Deployment

1. Back up the target database and record current active role assignments and Agent organization-column nullability.
2. Run `sql/23_single_organization_rbac.sql` in the target environment. It idempotently creates the five canonical role rows and makes Agent CompanyID, DepartmentID, and PositionID nullable while retaining existing foreign keys. It does not reassign users or alter Requirement, Project, Task, or owner GUID data.
3. Review the role crosswalk with the business owner. Assign `APPROVER` explicitly to designated decision-makers. Reassign any legacy Manager, Department Head, or Admin whose broader Workforce Manager scope is not intended.
4. Deploy the application code and restart the service. `/ready` checks database connectivity only; missing or inconsistent user organization metadata no longer blocks startup or routine operations.
5. Validate login and API access for one account per canonical role, with CompanyID, DepartmentID, and PositionID unset. Confirm Business User ownership filters, assigned-Approver decisions, Executive read-only dashboard access, Workforce Manager staffing controls, and Platform Owner administration. Verify an unknown role is denied.
6. Validate planning against active workforce role profiles. Candidate assignment requires an Active agent, exact active workforce-role profile match, active skills at required proficiency, latest passing Capability/Safety/Security/Governance evaluations, and available workload/concurrency capacity.
7. Keep scripts `sql/16_sql_server_rls_migration.sql` through `sql/18_sql_server_rls_rollback.sql` unapplied. They encode the former company/department RLS model and are not compatible with this policy without a separately reviewed role-based predicate and complete assignment/runtime table coverage.

## Rollback

This migration is additive and does not delete or rewrite user-role assignments or business ownership. Application rollback can restore the prior application release, but the database nullability changes are intentionally not reversed because nullable Agent metadata is backward-compatible with existing non-null values and new single-organization rows. Do not delete the new role rows after any user has been assigned to them. Any return to organization-scoped access requires a separate reviewed policy and complete mapping/backfill plan.

## Preserved Invariants

- `Requirement.CreatedByUserID`, `Project.CreatedByUserID`, and `Task.CreatedByUserID` remain the human ownership keys. No historical null owner is inferred or repaired by this change.
- Active workforce role profiles, approved skills, certification evaluations, workload, and concurrent capacity remain assignment gates.
- Company/Department/Position references on existing users and agents are preserved when present; new Agent records may leave them null.
- Native SQL Server RLS remains optional and disabled. No RLS policy is created or enabled by this migration.
