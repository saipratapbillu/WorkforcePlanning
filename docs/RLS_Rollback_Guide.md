# Native SQL Server RLS Rollback Guide

## Preconditions

Rollback is an emergency operation for an approved maintenance window only. Do not run it to work around a failed preflight or incomplete policy coverage. Confirm the application version and trusted session-context behavior are compatible with the intended post-rollback state, take a verified backup, and preserve the validation/audit evidence.

## Procedure

1. Stop or place affected application traffic into the approved maintenance/deny mode.
2. Connect to the correct DEV database using a reviewed maintenance connection.
3. Confirm the active policy and predicate inventory with `sql/17_sql_server_rls_validation.sql`.
4. On that same SQL session, set the rollback gate:

```sql
EXEC sys.sp_set_session_context @key=N'RollbackNativeRls', @value=1;
GO
```

5. Execute `sql/18_sql_server_rls_rollback.sql`.
6. Verify that the expected policy and its functions are absent, and verify application authorization remains enforced at the API layer.
7. Clear the gate, capture evidence, and resume traffic only after security-owner approval:

```sql
EXEC sys.sp_set_session_context @key=N'RollbackNativeRls', @value=NULL;
GO
```

The rollback drops only `Security.WorkforceOwnershipPolicy` and its predicate functions. It must not drop ownership columns, application tables, or the Security schema. If rollback fails, keep traffic in maintenance/deny mode and restore from the approved recovery procedure rather than manually dropping objects.
