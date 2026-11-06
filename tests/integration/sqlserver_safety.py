"""Fail-closed target validation and state restoration for SQL Server tests."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import MetaData, Table, and_, delete, inspect, insert, select, text, update
from sqlalchemy.engine import Connection, URL, make_url
from sqlalchemy.exc import ArgumentError


SYNTHETIC_DATABASE_PREFIX = "AICompany_M1_IT_"
REQUIRED_FIXTURES = frozenset({
    "concurrent_claims",
    "lease_expiration",
    "reviewer_crash_recovery",
    "duplicate_decision",
    "concurrent_reviews",
    "duplicate_deliverable",
    "hash_verification",
    "transaction_rollback",
    "defect_lifecycle",
})
FIXTURE_UUID_FIELDS = {
    "lease_expiration": ("execution_id", "reviewer_id"),
    "reviewer_crash_recovery": ("execution_id", "reviewer_id", "next_reviewer_id"),
    "duplicate_decision": ("execution_id", "reviewer_id"),
    "concurrent_reviews": ("execution_id", "reviewer_id"),
    "duplicate_deliverable": ("execution_id", "reviewer_id"),
    "hash_verification": ("execution_id", "reviewer_id", "output_id"),
    "transaction_rollback": ("execution_id", "reviewer_id", "output_id", "task_id"),
    "defect_lifecycle": ("execution_id", "reviewer_id", "agent_id", "task_id"),
}
FIXTURE_STRING_FIELDS = {
    "duplicate_decision": ("review_key",),
    "concurrent_reviews": ("review_key",),
    "duplicate_deliverable": ("first_review_key", "second_review_key"),
    "hash_verification": ("review_key",),
    "transaction_rollback": ("review_key",),
    "defect_lifecycle": (
        "required_role_code",
        "reject_review_key",
        "approve_review_key",
    ),
}
MAX_SNAPSHOT_ROWS = 50_000
MAX_SNAPSHOT_REPR_BYTES = 64 * 1024 * 1024
MARKER_TABLE = "RuntimeIntegrationDatabaseMarker"
MARKER_PURPOSE = "synthetic-integration-only"


class IntegrationSafetyError(RuntimeError):
    """Raised when an integration-test target cannot be proven safe."""


@dataclass(frozen=True)
class IntegrationTarget:
    url: URL
    expected_database: str
    expected_server_name: str
    expected_login: str
    marker_id: UUID
    test_run_id: UUID
    fixtures: Mapping[str, object]


@dataclass
class SnapshotBudget:
    row_count: int = 0
    estimated_bytes: int = 0

    def add(self, row: Mapping[str, object]) -> None:
        self.row_count += 1
        self.estimated_bytes += len(repr(row).encode("utf-8"))
        if self.row_count > MAX_SNAPSHOT_ROWS or self.estimated_bytes > MAX_SNAPSHOT_REPR_BYTES:
            raise IntegrationSafetyError("Synthetic database exceeds the safe fixture snapshot limit")


def load_integration_target(environ: Mapping[str, str]) -> IntegrationTarget:
    """Validate all operator-supplied safety controls without opening a connection."""
    required = (
        "RUNTIME_IT_DATABASE_URL",
        "RUNTIME_IT_EXPECTED_DATABASE",
        "RUNTIME_IT_EXPECTED_SERVER_NAME",
        "RUNTIME_IT_EXPECTED_LOGIN",
        "RUNTIME_IT_DATABASE_MARKER_ID",
        "RUNTIME_IT_TEST_RUN_ID",
        "RUNTIME_IT_FIXTURE_JSON",
    )
    missing = [key for key in required if not environ.get(key, "").strip()]
    if missing:
        raise IntegrationSafetyError("Required SQL Server integration settings are missing")
    if environ.get("RUNTIME_IT_SYNTHETIC_AUTHORIZED") != "1":
        raise IntegrationSafetyError("Explicit synthetic-database authorization is required")
    if environ.get("RUNTIME_IT_CLEANUP_ENABLED") != "1":
        raise IntegrationSafetyError("Fixture state restoration must be explicitly enabled")

    expected_database = environ["RUNTIME_IT_EXPECTED_DATABASE"].strip()
    if not re.fullmatch(r"AICompany_M1_IT_[A-Za-z0-9][A-Za-z0-9_]{0,40}", expected_database):
        raise IntegrationSafetyError("Expected database is not an approved synthetic test name")

    try:
        url = make_url(environ["RUNTIME_IT_DATABASE_URL"])
    except (ArgumentError, TypeError, ValueError) as exc:
        raise IntegrationSafetyError("SQL Server integration URL is invalid") from exc

    if (
        url.drivername != "mssql+pyodbc"
        or (url.host or "").casefold() != "localhost"
        or url.port is not None
        or url.username is not None
        or url.password is not None
        or url.database != expected_database
    ):
        raise IntegrationSafetyError("Integration URL must target the exact local synthetic database")

    query = {key.casefold(): value for key, value in url.query.items()}
    if set(query) != {"driver", "trusted_connection"}:
        raise IntegrationSafetyError("Integration URL contains unapproved connection options")
    if not str(query.get("driver", "")).strip() or str(query["trusted_connection"]).casefold() not in {"yes", "true", "1"}:
        raise IntegrationSafetyError("A local trusted connection and explicit ODBC driver are required")

    expected_login = environ["RUNTIME_IT_EXPECTED_LOGIN"].strip()
    expected_server_name = environ["RUNTIME_IT_EXPECTED_SERVER_NAME"].strip()
    if not expected_login or not expected_server_name:
        raise IntegrationSafetyError("Expected SQL Server identity settings cannot be empty")

    try:
        marker_id = UUID(environ["RUNTIME_IT_DATABASE_MARKER_ID"])
        test_run_id = UUID(environ["RUNTIME_IT_TEST_RUN_ID"])
        fixture_payload = json.loads(environ["RUNTIME_IT_FIXTURE_JSON"])
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise IntegrationSafetyError("Fixture, marker, or run identity is invalid") from exc

    if (
        not isinstance(fixture_payload, dict)
        or fixture_payload.get("test_run_id") != str(test_run_id)
        or fixture_payload.get("data_classification") != "synthetic-only"
    ):
        raise IntegrationSafetyError("Fixture manifest does not match the configured test run")
    fixtures = fixture_payload.get("fixtures")
    if not isinstance(fixtures, dict) or set(fixtures) != REQUIRED_FIXTURES:
        raise IntegrationSafetyError("Fixture manifest must define every SQL Server test case exactly")
    if any(not isinstance(value, dict) or not value for value in fixtures.values()):
        raise IntegrationSafetyError("Every SQL Server test case must have an explicit fixture")
    try:
        for field in ("execution_ids", "reviewer_ids"):
            values = fixtures["concurrent_claims"][field]
            if not isinstance(values, list) or len(values) != 2:
                raise IntegrationSafetyError("Concurrent-claim fixture requires two distinct principals and executions")
            for value in values:
                UUID(value)
        if len(set(fixtures["concurrent_claims"]["execution_ids"])) != 2:
            raise IntegrationSafetyError("Concurrent-claim executions must be distinct")
        if len(set(fixtures["concurrent_claims"]["reviewer_ids"])) != 2:
            raise IntegrationSafetyError("Concurrent-claim reviewers must be distinct")
        for case_name, fields in FIXTURE_UUID_FIELDS.items():
            for field in fields:
                UUID(fixtures[case_name][field])
        for case_name, fields in FIXTURE_STRING_FIELDS.items():
            for field in fields:
                value = fixtures[case_name][field]
                if not isinstance(value, str) or not value.strip():
                    raise IntegrationSafetyError("Fixture text fields cannot be empty")
        for case_name, fields in FIXTURE_STRING_FIELDS.items():
            for field in fields:
                if "review_key" in field and len(fixtures[case_name][field]) < 8:
                    raise IntegrationSafetyError("Review keys must meet the API minimum length")
    except (KeyError, TypeError, ValueError) as exc:
        raise IntegrationSafetyError("Fixture manifest contains missing or invalid IDs/fields") from exc

    return IntegrationTarget(
        url=url,
        expected_database=expected_database,
        expected_server_name=expected_server_name,
        expected_login=expected_login,
        marker_id=marker_id,
        test_run_id=test_run_id,
        fixtures=fixtures,
    )


def validate_connected_identity(
    target: IntegrationTarget,
    server: Mapping[str, object],
    marker: Mapping[str, object] | None,
) -> None:
    """Validate server/catalog/principal/marker facts returned by SQL Server."""
    if str(server.get("server_name") or "").casefold() != target.expected_server_name.casefold():
        raise IntegrationSafetyError("Connected SQL Server identity does not match the approved instance")
    if str(server.get("database_name") or "").casefold() != target.expected_database.casefold():
        raise IntegrationSafetyError("Connected database does not match the approved synthetic database")
    if str(server.get("login_name") or "").casefold() != target.expected_login.casefold():
        raise IntegrationSafetyError("Connected SQL principal does not match the dedicated test identity")
    if str(server.get("database_status") or "").casefold() != "online":
        raise IntegrationSafetyError("Synthetic test database is not ONLINE")
    if server.get("is_sysadmin") != 0 or server.get("is_db_owner") != 0:
        raise IntegrationSafetyError("SQL Server integration identity must not be sysadmin or db_owner")
    if str(server.get("database_owner") or "").casefold() == target.expected_login.casefold():
        raise IntegrationSafetyError("Test principal must not own the synthetic test database")
    if marker is None:
        raise IntegrationSafetyError("Synthetic database ownership marker is missing")
    if str(marker.get("marker_id")) != str(target.marker_id):
        raise IntegrationSafetyError("Synthetic database ownership marker does not match")
    if str(marker.get("database_name") or "").casefold() != target.expected_database.casefold():
        raise IntegrationSafetyError("Synthetic database marker names a different database")
    if marker.get("purpose") != MARKER_PURPOSE:
        raise IntegrationSafetyError("Database ownership marker has an unexpected purpose")
    if str(marker.get("created_by_login") or "").casefold() == target.expected_login.casefold():
        raise IntegrationSafetyError("Test principal cannot be the database setup principal")
    for permission in ("marker_update", "marker_insert", "marker_delete", "marker_alter"):
        if server.get(permission) != 0:
            raise IntegrationSafetyError("Test principal has write or DDL permission on the ownership marker")


def verify_connected_target(connection: Connection, target: IntegrationTarget) -> None:
    """Read the actual SQL Server target and its read-only ownership marker."""
    server = connection.execute(text("""
        SELECT CONVERT(nvarchar(128),@@SERVERNAME) AS server_name,
               DB_NAME() AS database_name,
               SUSER_SNAME() AS login_name,
               CONVERT(nvarchar(30),DATABASEPROPERTYEX(DB_NAME(),'Status')) AS database_status,
               (SELECT SUSER_SNAME(owner_sid) FROM sys.databases WHERE database_id=DB_ID()) AS database_owner,
               IS_SRVROLEMEMBER('sysadmin') AS is_sysadmin,
               IS_MEMBER('db_owner') AS is_db_owner,
               HAS_PERMS_BY_NAME('dbo.RuntimeIntegrationDatabaseMarker','OBJECT','UPDATE') AS marker_update,
               HAS_PERMS_BY_NAME('dbo.RuntimeIntegrationDatabaseMarker','OBJECT','INSERT') AS marker_insert,
               HAS_PERMS_BY_NAME('dbo.RuntimeIntegrationDatabaseMarker','OBJECT','DELETE') AS marker_delete,
               HAS_PERMS_BY_NAME('dbo.RuntimeIntegrationDatabaseMarker','OBJECT','ALTER') AS marker_alter
    """)).mappings().one()
    marker = connection.execute(text("""
        SELECT MarkerID AS marker_id,DatabaseName AS database_name,Purpose AS purpose,
               CreatedByLogin AS created_by_login
        FROM dbo.RuntimeIntegrationDatabaseMarker
        WHERE MarkerID=:marker_id
    """), {"marker_id": target.marker_id}).mappings().first()
    validate_connected_identity(target, server, marker)


class DboStateSnapshot:
    """In-memory snapshot of synthetic dbo rows, restored after committed tests."""

    def __init__(
        self,
        tables: Mapping[str, tuple[Table, dict[tuple[object, ...], dict[str, object]]]],
        schema_signature: Mapping[str, object],
    ):
        self.tables = dict(tables)
        self.schema_signature = dict(schema_signature)

    @classmethod
    def capture(cls, connection: Connection) -> DboStateSnapshot:
        inspector = inspect(connection)
        table_names = sorted(inspector.get_table_names(schema="dbo"))
        table_names = [name for name in table_names if name != MARKER_TABLE]
        cls._validate_snapshot_scope(connection)
        snapshots: dict[str, tuple[Table, dict[tuple[object, ...], dict[str, object]]]] = {}
        metadata = MetaData()
        budget = SnapshotBudget()

        for name in table_names:
            table = Table(name, metadata, schema="dbo", autoload_with=connection)
            primary_key = tuple(table.primary_key.columns)
            if not primary_key:
                raise IntegrationSafetyError(f"Cannot safely restore dbo.{name}: no primary key")
            rows = {}
            result = connection.execution_options(stream_results=True).execute(
                select(table).execution_options(yield_per=500)
            )
            for row in result.mappings():
                snapshot_row = cls._snapshot_row(table, row)
                budget.add(snapshot_row)
                rows[tuple(row[column.name] for column in primary_key)] = snapshot_row
            snapshots[name] = (table, rows)

        if not snapshots:
            raise IntegrationSafetyError("No dbo application tables were found to snapshot")
        return cls(snapshots, cls._schema_signature(inspector, table_names))

    def restore(self, connection: Connection) -> None:
        """Restore only captured dbo tables; raise on schema drift or cleanup failure."""
        inspector = inspect(connection)
        current_names = set(inspector.get_table_names(schema="dbo"))
        expected_names = set(self.tables) | {MARKER_TABLE}
        if current_names != expected_names:
            raise IntegrationSafetyError("dbo schema changed during integration tests; cleanup is unsafe")
        self._validate_snapshot_scope(connection)
        if self._schema_signature(inspector, sorted(self.tables)) != self.schema_signature:
            raise IntegrationSafetyError("dbo table definitions changed during integration tests; cleanup is unsafe")

        ordered_names = self._foreign_key_order(inspector)
        for name in reversed(ordered_names):
            table, original = self.tables[name]
            primary_key = tuple(table.primary_key.columns)
            current = {
                tuple(row[column.name] for column in primary_key): self._snapshot_row(table, row)
                for row in connection.execute(select(table)).mappings()
            }
            added_keys = current.keys() - original.keys()
            for key in added_keys:
                connection.execute(delete(table).where(self._key_predicate(primary_key, key)))

        for name in ordered_names:
            table, original = self.tables[name]
            primary_key = tuple(table.primary_key.columns)
            current = {
                tuple(row[column.name] for column in primary_key): self._snapshot_row(table, row)
                for row in connection.execute(select(table)).mappings()
            }
            missing_keys = original.keys() - current.keys()
            for key in missing_keys:
                row = original[key]
                values = {column.name: row[column.name] for column in table.columns if self._insertable(column)}
                identity_columns = [column for column in table.columns if getattr(column, "identity", None)]
                if identity_columns:
                    self._set_identity_insert(connection, name, True)
                try:
                    connection.execute(insert(table).values(values))
                finally:
                    if identity_columns:
                        self._set_identity_insert(connection, name, False)

            for key, row in original.items():
                values = {
                    column.name: row[column.name]
                    for column in table.columns
                    if column.name not in {item.name for item in primary_key} and self._updatable(column)
                }
                if values:
                    connection.execute(
                        update(table).where(self._key_predicate(primary_key, key)).values(values)
                    )

        for name, (table, original) in self.tables.items():
            primary_key = tuple(table.primary_key.columns)
            restored = {
                tuple(row[column.name] for column in primary_key): self._snapshot_row(table, row)
                for row in connection.execute(select(table)).mappings()
            }
            if restored != original:
                raise IntegrationSafetyError(f"Could not restore synthetic fixture state for dbo.{name}")

    @staticmethod
    def _validate_snapshot_scope(connection: Connection) -> None:
        unsupported_tables = connection.execute(text("""
            SELECT QUOTENAME(s.name)+N'.'+QUOTENAME(t.name)
            FROM sys.tables AS t
            JOIN sys.schemas AS s ON s.schema_id=t.schema_id
            WHERE s.name=N'dbo'
              AND (
                    t.temporal_type <> 0
                    OR EXISTS (
                        SELECT 1 FROM sys.triggers AS tr
                        WHERE tr.parent_id=t.object_id AND tr.is_disabled=0
                    )
              )
        """)).scalars().all()
        if unsupported_tables:
            raise IntegrationSafetyError("Dbo snapshot cannot safely restore temporal tables or enabled triggers")

        external_references = connection.execute(text("""
            SELECT TOP (1) ps.name,pt.name
            FROM sys.foreign_keys AS fk
            JOIN sys.tables AS pt ON pt.object_id=fk.parent_object_id
            JOIN sys.schemas AS ps ON ps.schema_id=pt.schema_id
            JOIN sys.tables AS rt ON rt.object_id=fk.referenced_object_id
            JOIN sys.schemas AS rs ON rs.schema_id=rt.schema_id
            WHERE rs.name=N'dbo' AND ps.name<>N'dbo'
        """)).first()
        if external_references:
            raise IntegrationSafetyError("Dbo snapshot cannot restore tables referenced by foreign keys outside dbo")

    @staticmethod
    def _schema_signature(inspector, table_names: list[str]) -> dict[str, object]:
        def normalized(items) -> tuple[str, ...]:
            return tuple(sorted(repr(item) for item in items))

        signature = {}
        for name in table_names:
            columns = tuple(
                (
                    column["name"],
                    str(column["type"]),
                    column.get("nullable"),
                    column.get("default"),
                    repr(column.get("computed")),
                    repr(column.get("identity")),
                )
                for column in inspector.get_columns(name, schema="dbo")
            )
            primary_key = repr(inspector.get_pk_constraint(name, schema="dbo"))
            foreign_keys = normalized(inspector.get_foreign_keys(name, schema="dbo"))
            unique_constraints = normalized(inspector.get_unique_constraints(name, schema="dbo"))
            check_constraints = normalized(inspector.get_check_constraints(name, schema="dbo"))
            indexes = normalized(inspector.get_indexes(name, schema="dbo"))
            signature[name] = (
                columns,
                primary_key,
                foreign_keys,
                unique_constraints,
                check_constraints,
                indexes,
            )
        return signature

    @staticmethod
    def _key_predicate(primary_key, key):
        return and_(*(column == value for column, value in zip(primary_key, key)))

    @classmethod
    def _snapshot_row(cls, table, row):
        return {
            column.name: row[column.name]
            for column in table.columns
            if not getattr(column, "computed", None) and not cls._is_rowversion(column)
        }

    @staticmethod
    def _insertable(column) -> bool:
        return not getattr(column, "computed", None) and not DboStateSnapshot._is_rowversion(column)

    @staticmethod
    def _updatable(column) -> bool:
        return (
            not getattr(column, "computed", None)
            and not getattr(column, "identity", None)
            and not DboStateSnapshot._is_rowversion(column)
        )

    @staticmethod
    def _is_rowversion(column) -> bool:
        return column.type.__class__.__name__.casefold() in {"timestamp", "rowversion"}

    @staticmethod
    def _set_identity_insert(connection: Connection, table_name: str, enabled: bool) -> None:
        quoted_name = table_name.replace("]", "]]")
        state = "ON" if enabled else "OFF"
        connection.exec_driver_sql(f"SET IDENTITY_INSERT [dbo].[{quoted_name}] {state}")

    def _foreign_key_order(self, inspector) -> list[str]:
        names = set(self.tables)
        dependencies: dict[str, set[str]] = {name: set() for name in names}
        for child in names:
            for foreign_key in inspector.get_foreign_keys(child, schema="dbo"):
                parent = foreign_key.get("referred_table")
                parent_schema = foreign_key.get("referred_schema") or "dbo"
                if parent_schema == "dbo" and parent in names and parent != child:
                    dependencies[child].add(parent)

        ordered: list[str] = []
        remaining = {name: set(parents) for name, parents in dependencies.items()}
        while remaining:
            ready = sorted(name for name, parents in remaining.items() if not parents)
            if not ready:
                raise IntegrationSafetyError("dbo foreign-key cycle prevents safe fixture restoration")
            for name in ready:
                ordered.append(name)
                remaining.pop(name)
            for parents in remaining.values():
                parents.difference_update(ready)
        return ordered


def acquire_test_lock(connection: Connection) -> None:
    result = connection.execute(text("""
        DECLARE @lock_result int;
        EXEC @lock_result=sys.sp_getapplock
            @Resource=:resource,
            @LockMode='Exclusive',
            @LockOwner='Session',
            @LockTimeout=0;
        SELECT @lock_result;
    """), {"resource": "AICompany.M1.SQLServerTests"}).scalar_one()
    if result < 0:
        raise IntegrationSafetyError("Could not acquire the exclusive integration-test lock")


def release_test_lock(connection: Connection) -> None:
    result = connection.execute(text("""
        DECLARE @lock_result int;
        EXEC @lock_result=sys.sp_releaseapplock
            @Resource=:resource,
            @LockOwner='Session';
        SELECT @lock_result;
    """), {"resource": "AICompany.M1.SQLServerTests"}).scalar_one()
    if result < 0:
        raise IntegrationSafetyError("Could not release the exclusive integration-test lock")
