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

## Regression and Release

Run the Python test suite and RLS artifact checks before migration. Apply only in DEV after backup, maintenance approval, and a reviewed session-context gate. Re-run script 17 from a new authenticated session, run cross-company negative tests, and verify the application is ready before promoting the exact reviewed artifact.
