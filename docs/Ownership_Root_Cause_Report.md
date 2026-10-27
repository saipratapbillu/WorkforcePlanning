# Ownership Propagation Root-Cause Report

**Scope:** Latest AI Workforce OS requirement → assessment → approval → Project Factory → Task decomposition flow. Historical and final row verification used read-only SQL queries against the local `AICompany` database. A controlled validation Requirement/Approval/Project/Task set was created through the application UI; no database records were directly edited.

## Finding

The affected requirement, project, and seven tasks have null normalized owner GUIDs, even though their legacy `CreatedBy` strings contain the requester's user GUID.

For requirement `3703e196-e61f-4e9e-aad4-962192ef669a`:

- Requirement `CreatedAtUtc`: `2026-10-23 12:28:41.161326`; `CreatedBy` is the requester UUID; `CreatedByUserID` is null.
- Project `e25bee0a-b22e-41db-ac6e-8fd7dce94d1e` created at `12:32:24.083550`; `CreatedBy` is the same requester UUID; `CreatedByUserID` is null.
- Seven tasks were created at `12:32:24.100547`; all seven have null `CreatedByUserID`.
- The normalized GUID columns are nullable and have no default constraint. SQL Server defaults therefore cannot populate them. No insert triggers were found in the initial schema check.

## Current Source Trace

1. **Requirement insert:** `app/api/requirements.py:create_requirement` obtains the actor from the authenticated JWT, writes the legacy `CreatedBy` string and sets `CreatedByUserID=UUID(user['sub'])`, then calls `db.commit()` and refreshes the ORM object.
2. **Approval and transaction:** `ApprovalService.decide` locks the approval/requirement, changes approval and requirement status, calls `db.flush()`, then invokes `ProjectFactory.create_project`. The approval endpoint `app/api/approvals.py:decide_approval` commits after the service returns. The Project, Tasks, planner changes, queue changes, notifications, and approval decision therefore share the endpoint's SQLAlchemy transaction. `flush()` sends SQL but does not commit.
3. **Project insert:** `ProjectFactory` resolves the normalized owner, falling back only to an exact UUID in legacy `Requirement.CreatedBy` after verifying that AppUser exists, then binds it as Project.CreatedByUserID.
4. **Task generation:** `ProjectFactory.generate_tasks` resolves and binds the same verified owner for each generated Task.CreatedByUserID.
5. **Failure semantics:** An exception before the endpoint commit causes the session dependency to roll back; a successful commit persists all flushed changes. Transaction boundaries do not silently convert populated bound parameters to NULL.

## Root Cause Assessment

**Most likely cause: historical rows were written by a code version or insert path that did not include the normalized owner columns.** The affected record timestamps are from October 23; current source explicitly supplies the owner IDs. The database schema permits nulls and does not provide a default/trigger to compensate for older writers.

The available database evidence cannot identify the exact running application build or the insert statement used at that time. Therefore “stale application process / older deployed writer” is a strongly supported hypothesis, not a proven fact. The precise historical writer can only be confirmed from deployment/build logs, request logs, or SQL Server Extended Events/audit captured at insertion time.

The separate AppUser organization blocker is confirmed: active users have null CompanyID, DepartmentID, and PositionID. It does not explain the null CreatedByUserID values, but it prevents safe company-scoped agent assignment and executive queries.

## Repair and Prevention

- Current requirement creation and Project Factory paths are covered by insert-boundary regression tests.
- Project Factory recovers only exact legacy GUID owners that resolve to AppUser; it does not guess from names or email.
- Invalid ownership now blocks project/task creation with HTTP 409.
- Application startup remains available in restricted mode when organization scope is incomplete; only health, login, and privileged mapping repair routes are permitted until mappings validate. `/ready` remains 503.
- Existing null owners should be backfilled only from an approved mapping. Do not infer ownership from display name or parent records.
- Confirm the deployed process is running the current build after deployment, then submit a new approved workflow in a controlled environment and verify normalized owner IDs immediately after each stage.

## Runtime Readiness Evidence

At validation time the database contained 55 Provisioning agents and 1 Active agent. The active-agent query, skill catalog, certification records, task assignment, queue, and execution tables were inspected read-only. The existing project had no assignment, queue, or execution records. No simulated executions were generated.

## Fresh-Process Differential Verification (2026-10-26)

The previous server at `127.0.0.1:8029` created the validation request `9565f926-806b-4f81-877b-0a7ccec34053` and its Project/7 Tasks without normalized owners. The same workspace source was started as a separate Uvicorn process at `127.0.0.1:8129`. A second controlled validation request, `df2efffa-1319-4de6-9208-d678d2e5cf8e`, was submitted and approved through the application UI on that fresh process.

The fresh-process SQL verification showed:

- Requirement `df2efffa-1319-4de6-9208-d678d2e5cf8e` has `CreatedByUserID=76c83abf-487b-444e-a39b-c6128f7ba904`.
- Project `085d77f0-cab5-40f6-8fdc-236d06f95680` has the same owner GUID.
- All seven generated Task rows have the same owner GUID.
- The project remains Planned and no TaskAssignment, AgentTaskQueue, AgentExecution, AgentExecutionOutput, Evaluation, or Deliverable rows were created by this validation.

This differential confirms the current workspace source propagates ownership correctly and strongly supports that the `8029` process was running stale code. The old process was left running and untouched; use a controlled restart/deployment of the validated source before relying on its APIs. Existing historical null-owner rows remain unrepaired and require a separately approved backfill.
