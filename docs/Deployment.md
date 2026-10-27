# Deployment Notes: UAT Reliability Fixes

## Scope

This release fixes SQL Server dashboard cursor handling, aligns dashboard notification rows with the notification count, includes approval decisions in requirement history, and permits approved project planning when the optional workforce reuse-assessment table is not installed. The human approval check, approval audit record, project creation, and transaction boundary remain in the existing approval workflow.

## Database and Migration

- No data backfill or manual database update is required for these application changes.
- Migration 24 (`sql/24_intelligent_workforce_reuse.sql`) remains required to enable persisted workforce reuse assessments and the related reuse-review APIs. This code detects when that table is absent and skips only reuse-assessment reads/writes; planning may continue with unassigned tasks. It does not assign uncertified agents or enqueue tasks that fail runtime gates.
- Apply Migration 24 only through the approved DBA change process after backup, review, and rollback preparation. Do not run it as an application startup side effect.
- Do not treat a successful planned project as workforce or runtime readiness. Confirm qualified staffing, estimates, required gates, queue eligibility, and adapter configuration separately before execution.

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
