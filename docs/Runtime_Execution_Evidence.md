# Runtime Execution Evidence

Milestone 1 evidence trail: AgentRuntimeEvent rows (TaskClaimed, OutputSubmitted, ReviewLeaseClaimed, ReviewLeaseExpired, IndependentQAReview), Evaluation (IndependentQA), AgentRuntimeDefect lifecycle Open->InProgress->Retest->Closed/Escalated, Deliverable hash = AgentExecutionOutput.Sha256 recomputed at approval.

No model calls, ledger or OpenAI integration exist in this milestone; all execution is worker-supplied output.

## SQL Server release gate

The review and worker paths have not been verified with native ownership RLS
enabled. `RUNTIME_REVIEWER` has no scoped RLS predicate for its currently leased
execution and associated requirement; the current ownership policy can therefore
hide review work and fail closed. Worker-token requests also do not yet establish
an agent-scoped SQL RLS identity. Do not treat either path as production-ready
when `Security.WorkforceOwnershipPolicy` is enabled until narrow predicates are
implemented and the integration suite passes on a disposable restored copy.

Migration 27's `RUNTIME_REAPER` RLS grant is broader than a per-task grant: it
allows the dedicated reaper identity to see owner-filtered rows for requirements,
projects, tasks, and issues. Keep that identity inaccessible through the
application and require a security review before production deployment.

## Milestone 1.1 static verification (2026-11-03)

The current source confirms that the native ownership migration in
`sql/16_sql_server_rls_migration.sql` refuses to proceed when runtime tables
exist (error 51206). It contains no runtime-table predicates. Migration 27 adds
the reviewer and reaper role rows but still adds no runtime predicates; it
modifies the owner predicate to grant the reaper broad owner-row visibility.
The RLS role codes also do not match the canonical role codes established by
migration 23.

The application currently propagates only `UserID` through the SQL session
context. Worker-token validation does not set an agent SQL identity, and
connection cleanup clears only `UserID` while suppressing cleanup errors.
Consequently, the route authorization matrix is HTTP-layer evidence only; it
does not establish database isolation.

Validation on 2026-11-03: `python -m pytest -q` completed with 295 passed and
10 skipped. No disposable SQL Server URL or integration fixtures were
configured, so no migration, RLS, pooling, or SQL Server concurrency test was
executed. The live database was not queried or changed. Decision remains
**NO-GO**.

## SQL integration environment investigation (2026-11-03)

The local default instance is SQL Server 2022 Developer, `16.0.1000.6` RTM;
mixed authentication is enabled. ODBC Driver 17, `pyodbc 5.1.0`, and
`SQLAlchemy 2.0.35` are available. A read-only catalog/backup-history check
against `master` found online user databases `AICompany` and `SharePoint`, but
neither is confirmed disposable; neither was opened. The system backup history
is empty, and no `.bak`/`.bacpac` was found in the repository/project parent.
The configured SQL backup directory could not be enumerated because access was
denied. C: had about 319 GB free.

The only connectivity verified was a read-only Windows-integrated connection
to `master`; no test database connection was attempted. There is no dedicated
test SQL identity, and test account permissions are therefore unverified.
`RUNTIME_IT_DATABASE_URL` and `RUNTIME_IT_FIXTURE_JSON` are unset.

At the time of this earlier assessment, the integration suite committed state
changes to supplied fixtures (review claims/decisions, queue and execution
states, output contents, and defect lifecycle) without general teardown, and
its `AICompany_M1_IT` name-prefix check was not sufficient proof that a database
was disposable. The harness was subsequently hardened as recorded below. No
database was created, restored, or changed; no migrations or tests against SQL
Server were run. Milestone 1.1 remains **NO-GO** pending an approved isolated
environment and SQL Server validation.

### Synthetic environment authorization review (2026-11-03)

The user explicitly authorized a new synthetic database, but the provisioning
task's stop condition requires halting while RLS is incomplete. A read-only
query to `master` confirmed that the exact candidate
`AICompany_M1_IT_20261103` was absent; no database, SQL login, fixture, or
environment variable was created. No user database was opened, no migration
was applied, and no test was run. The test environment is not provisioned,
RLS is not validated, and production compatibility remains unverified.

## Milestone 1.1-A/B design and harness update (2026-11-03)

The RLS guide now contains the proposed role/identity matrix, runtime
table-by-table policy design, SQL session-context/pooling rules, migration
ordering, and explicit gaps. The design is not implemented or independently
security-reviewed. Cross-tenant isolation cannot be guaranteed from the current
schema because authoritative tenant keys are absent.

The integration harness now validates local target configuration and connected
database identity, requires a setup-owned immutable marker and dedicated
non-admin test identity, serializes harness runs, and restores committed `dbo`
row changes. The harness streams a bounded snapshot and rejects known
trigger/temporal/external-FK cases and schema drift. Nineteen offline harness
unit tests passed; the offline repository regression suite passed 314 tests
with the SQL Server integration module excluded. No SQL Server connection or
integration test was made in this task. Database provisioning, migration,
actual cleanup behavior, RLS policy enforcement, worker/reviewer/reaper
isolation, and production compatibility remain unverified.
