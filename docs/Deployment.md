# Deployment Notes: UAT Reliability Fixes

## Milestone 1.1 SQL Server security gate

**NO-GO for production runtime execution.** Reviewer RLS, worker agent-scoped
SQL identity, and least-privilege reaper access are not implemented and
verified against a disposable SQL Server database. Migration 27 currently
contains a broad reaper owner-policy exception; do not apply or enable it in
production as a workaround. See [Runtime_Execution_Evidence.md](./Runtime_Execution_Evidence.md)
and [Runtime_Reaper_Deployment.md](./Runtime_Reaper_Deployment.md).

The local instance is SQL Server 2022 Developer `16.0.1000.6` (RTM), with
mixed authentication and ODBC Driver 17 available. `AICompany` and
`SharePoint` are existing online user databases of unknown classification and
were not opened. No disposable test database exists. No backup file was found
in the repository/project parent and `msdb` backup history is empty; access to
the configured SQL backup directory was denied. The integration URL and
fixtures are unset; no test SQL identity was confirmed. Migrations 23
and 27 were not applied or tested for this gate. The live databases were not
modified.
Production deployment remains blocked until scoped policies, pooled session
context behavior, migrations, rollback, and SQL Server integration tests pass
on an approved isolated restored copy. The existing integration tests commit
fixture changes and have no general cleanup, so they must not be pointed at a
shared database even if its name matches the suite's test prefix.

## Scope

This release fixes SQL Server dashboard cursor handling, aligns dashboard notification rows with the notification count, includes approval decisions in requirement history, and permits approved project planning when the optional workforce reuse-assessment table is not installed. The human approval check, approval audit record, project creation, and transaction boundary remain in the existing approval workflow.

## Database and Migration

- No data backfill or manual database update is required for these application changes.
- Migration 24 (`sql/24_intelligent_workforce_reuse.sql`) remains required to enable persisted workforce reuse assessments and the related reuse-review APIs. This code detects when that table is absent and skips only reuse-assessment reads/writes; planning may continue with unassigned tasks. It does not assign uncertified agents or enqueue tasks that fail runtime gates.
- Apply Migration 24 only through the approved DBA change process after backup, review, and rollback preparation. Do not run it as an application startup side effect.
- Do not treat a successful planned project as workforce or runtime readiness. Confirm qualified staffing, estimates, required gates, queue eligibility, and adapter configuration separately before execution.
- Migration 25 (`sql/25_people_workforce_planning.sql`) is required for the new user skill/certification/availability records, project backlog hierarchy, assignment recommendations, and manager-approved task assignments. It verifies the existing identity, organization, audit, skill, project, and task tables before creating its objects.
- Apply Migration 25 through the approved DBA change process after backup, review, and rollback preparation; it is not applied automatically at application startup. Until applied, the new workforce and backlog APIs are not operational against SQL Server.
- Assignment recommendations do not assign resources. An assignment is created only after the candidate's active, assigned manager approves the pending recommendation; candidates without an assigned manager remain blocked.

## Release Procedure

1. Run the complete test suite with the deployment Python environment: `python -m pytest -q`.
2. Deploy the application build using the normal release pipeline and restart all application workers so no stale process continues serving the previous code.
3. Verify `/health` and `/ready`, then verify authenticated `/dashboard/api`, `/dashboard/api/me`, `/notifications`, and `/approvals` responses.
4. In a controlled environment, submit a test requirement through intake and complete its decision through the Approval Center as an authorized approver. Confirm the requirement and approval decision persist, the approval audit event appears in requirement tracking, and a Planned project and seven tasks are created.
5. Compare the dashboard notification count and rows with `/notifications` for the same principal and visibility scope.
6. Confirm the project remains unassigned and the runtime queue remains empty unless qualified agents and every required execution gate are independently satisfied.
7. Review Migration 24 status through the read-only readiness endpoint. If absent, record reuse-review APIs and persisted reuse assessments as unavailable until the approved database deployment is complete.

## Rollback

Rollback the application build using the normal deployment pipeline if health checks, approval workflow, dashboard APIs, or audit verification fail. The application changes do not require a data rollback. Preserve any workflow records created during verification; do not delete or manually alter them. If Migration 24 was separately applied, use its approved DBA rollback/compensating procedure rather than coupling that database change to an application rollback.

## Verification Evidence

The UAT regression suite passed 104 tests. A controlled live UI approval completed successfully: the request advanced to `Approved`, the requirement timeline included `ApprovalApprove`, and the workflow created a `Planned` project with seven unassigned tasks. Authenticated `/dashboard/api/me` returned 200. Dashboard notification rows and count matched `/notifications` at 65 total, 65 unread. Runtime remained empty and the execution adapter was not configured, so this evidence confirms planning only, not execution readiness.

## Migration 26 - Development Execution Management

Apply `sql/26_development_execution_management.sql` after migration 25. It adds epic owner/priority/close columns, story priority/backlog rank/completion stamps, sprint start/complete stamps and `ProjectStoryDependency`. Not yet applied to a live SQL Server in this workspace.


## Migration 25 table naming
Migration 25 creates dbo.ProjectDeliveryTask (not ProjectTask). Older databases already contain a legacy dbo.ProjectTask with a different schema; reusing that name made the idempotent guard skip creation and broke the foreign keys.

## Migration 27 - Reviewer Governance (NOT yet applied)
- Order: migration 23, then 27. Test both on a restored copy first; do not run on live without a backup and maintenance window.
- Adds AgentExecution review lease columns (owner, expiry, attempt, key, decision), AppUser.CreatedByUserID provenance, RUNTIME_REVIEWER and RUNTIME_REAPER roles, and a defect index. Its optional native ownership RLS change is broader than per-lease reaper access and is not approved for production.
- Reviewer assignment is fail-closed when the target account's creator is unknown or is the assigning owner. Provision the reviewer account through an independently controlled process, then assign it through PUT /admin/users/{id}/role; it must not be a creator of the work it reviews (NULL work creators fail closed).
- Review API: POST /runtime/reviews/claim, GET /runtime/reviews/{id}, POST /runtime/reviews/{id}/decision (requires review_key). The old ADMIN review route is removed.
- Worker: GET /runtime/worker/executions/{id}/context.
- The reaper (POST /runtime/reap-expired-leases, owner only) is NOT scheduled by the app. See [Runtime_Reaper_Deployment.md](./Runtime_Reaper_Deployment.md) for the standalone Windows and production deployment instructions.
- The reviewer role is confined to review APIs at the HTTP layer; SQL Server RLS isolation for reviewers and workers is not implemented or verified. The standalone reaper identity is denied all HTTP application routes. See [Route_Authorization_Matrix.md](./Route_Authorization_Matrix.md) for the HTTP authorization matrix and tests.
