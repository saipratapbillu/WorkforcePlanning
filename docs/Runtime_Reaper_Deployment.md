# Runtime Lease Reaper Deployment

The standalone process invokes `app.services.agent_runtime.reap_expired_leases`;
it does not implement a second reaper or maintain separate execution state.
`sp_getapplock` with transaction ownership provides a database-wide exclusive
lock for each pass; commit or rollback releases it on the same connection.

## Windows development and single-host deployment

Use Task Scheduler to run one pass every minute:

1. Create a task under a dedicated Windows service account that can read the
   deployment files and connect to the target SQL Server.
2. Set the working directory to the deployed repository root.
3. Configure `DATABASE_URL` and `RUNTIME_REAPER_USER_ID` in the task's protected
   environment, not in command arguments. `RUNTIME_REAPER_USER_ID` must refer to
   an active, dedicated `AppUser` assigned the `RUNTIME_REAPER` role.
4. Do not deploy the reaper against production yet. Migration 27's RLS exception
   grants broader owner-scoped visibility than expired-lease recovery requires,
   and native runtime-table predicates have not been validated. A disposable
   database is required for migration and RLS testing; the current local
   environment has no configured integration URL or fixtures. Provisioning a
   service AppUser does not resolve this blocker.
5. Action:
   - Program: `C:\path\to\deployment\.venv\Scripts\python.exe`
   - Arguments: `-m tools.runtime_reaper --once`
   - Start in: `C:\path\to\deployment`
6. Trigger: repeat every 1 minute indefinitely. Set "If the task is already
   running" to "Do not start a new instance"; configure retries and failure
   notifications.
7. Confirm the task's last result is `0`, inspect its process logs, and verify
   expired leases are recovered in a disposable environment before production.

Alternatively, run one continuous process at startup with
`python -m tools.runtime_reaper --interval-seconds 60`. The process exits with
status 1 after five consecutive database failures by default. Override with
`RUNTIME_REAPER_INTERVAL_SECONDS` and `RUNTIME_REAPER_MAX_FAILURES`. `--once`
returns status 1 on a database error and 0 after a completed or lock-skipped
pass.

The global `AuthorizationMiddleware` does not start or schedule this process.
The worker and reviewer API authorization paths are separate from reaper
execution; only the SQL Server service identity runs the scheduled process.

## Production deployment

- Run as a dedicated service identity with SQL rights for the existing reaper's
  reads and state/event updates, plus SQL Server application lock access. Do not
  use a developer or interactive administrator account.
- **Release blocker:** migration 27 grants `RUNTIME_REAPER` cross-owner access
  to owner-filtered requirement/project/task/issue rows. Do not enable that
  exception in production. Replace it with reviewed operation- and
  lease-scoped permissions and validate them against native RLS first.
- Supply `DATABASE_URL` through a protected service configuration and use
  encrypted SQL Server transport with certificate validation.
- Deploy exactly one managed service per database where practical; the SQL
  application lock protects against duplicate instances across hosts, but
  duplicate scheduling still creates unnecessary connections and log noise.
- Monitor process exit status, consecutive connection errors, and lease/review
  timeout escalation counts. Alert on nonzero exit and on lack of successful
  passes. Retain logs according to the operational audit policy.
- Configure restart/backoff and shutdown grace periods in the process manager.
  Do not disable the runtime's existing escalation and retry limits.

The reaper is not started by FastAPI application startup. Until this process is
deployed and monitored, expired execution and review leases are not recovered
automatically.

## SQL Server integration suite

Never point the suite at `AICompany`, `SharePoint`, or any shared database.
`tests/integration/test_runtime_sqlserver.py` uses
`tests/integration/sqlserver_safety.py`. Before opening a connection, it
requires explicit settings for the exact `AICompany_M1_IT_<suffix>` database,
the expected local `@@SERVERNAME`, the dedicated trusted Windows test login, a
setup-owned marker UUID, a per-run UUID, the complete fixture JSON, and
`RUNTIME_IT_SYNTHETIC_AUTHORIZED=1` plus
`RUNTIME_IT_CLEANUP_ENABLED=1`. The URL must explicitly select
`mssql+pyodbc`, `localhost`, and the same exact database; embedded credentials
or unapproved ODBC options are rejected.

After connecting, the harness checks actual server/database/login, ONLINE
status, database owner, sysadmin/db_owner membership, marker purpose and
identity, and that the test principal cannot modify the marker. It holds a
database-wide application lock, snapshots `dbo` rows, and restores committed
row changes during teardown. Snapshot/cleanup failures are test failures. Do
not run application traffic against this database: the application lock only
serializes integration harnesses. It does not restore identity/sequence counters
or non-`dbo` state; discard the test database after a run. The setup identity
and test identity must be separate; the test identity must not be sysadmin,
db_owner, production app identity, or shared human administrator. Marker and
URL checks do not prove that the database contains only synthetic data;
provisioning provenance must be verified separately.

`RUNTIME_IT_FIXTURE_JSON` uses
`{"test_run_id":"<UUID>","data_classification":"synthetic-only","fixtures":{...}}`.
It requires all nine test cases and validates UUIDs, distinct concurrent claim
identities, and review keys before connecting. The fixtures must refer only to
records created for this synthetic test database. Exact fields are listed
below. This schema does not make production data safe; no production rows may
be copied into the test database.

As of 2026-11-03, the integration URL and fixture manifest remain unset, no
test database or test identity exists, and no SQL Server integration test has
run. Offline safety unit tests passed (16); that is not SQL Server or
concurrency evidence. See [RLS_Deployment_Guide.md](RLS_Deployment_Guide.md)
for the design and remaining gates.

### Provisioning decision update (2026-11-03)

Explicit authorization for a newly created synthetic `AICompany_M1_IT_`
database has been received. This design/harness task separately prohibited
database provisioning, SQL identity creation, migrations, and SQL Server test
execution; none occurred. The exact candidate `AICompany_M1_IT_20261103` was
absent in a read-only `master` query during the earlier provisioning review, but
was not reserved. Obtain separate implementation/provisioning authorization
and complete independent security review before a future database operation.

Fixture JSON keys:

- `concurrent_claims`: `execution_ids` (two UUIDs), `reviewer_ids` (two UUIDs).
- `lease_expiration`: `execution_id`, `reviewer_id`.
- `reviewer_crash_recovery`: `execution_id`, `reviewer_id`, `next_reviewer_id`.
- `duplicate_decision`, `concurrent_reviews`: `execution_id`, `reviewer_id`,
  `review_key`.
- `duplicate_deliverable`: `execution_id`, `reviewer_id`, `first_review_key`,
  `second_review_key`.
- `hash_verification`: `execution_id`, `reviewer_id`, `output_id`, `review_key`.
- `transaction_rollback`: `execution_id`, `reviewer_id`, `output_id`, `task_id`,
  `review_key`.
- `defect_lifecycle`: `execution_id`, `reviewer_id`, `agent_id`, `task_id`,
  `required_role_code`, `reject_review_key`, `approve_review_key`.
