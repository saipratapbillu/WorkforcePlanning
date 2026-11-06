import json
import unittest
from uuid import uuid4
from unittest.mock import MagicMock, patch

from sqlalchemy.engine import URL

from tests.integration.sqlserver_safety import (
    IntegrationSafetyError,
    REQUIRED_FIXTURES,
    IntegrationTarget,
    DboStateSnapshot,
    SnapshotBudget,
    load_integration_target,
    validate_connected_identity,
)


class SqlServerIntegrationSafetyTests(unittest.TestCase):
    def _environment(self):
        test_run_id = str(uuid4())
        fixture_payload = {
            "test_run_id": test_run_id,
            "data_classification": "synthetic-only",
            "fixtures": {
                "concurrent_claims": {
                    "execution_ids": [str(uuid4()), str(uuid4())],
                    "reviewer_ids": [str(uuid4()), str(uuid4())],
                },
                "lease_expiration": {"execution_id": str(uuid4()), "reviewer_id": str(uuid4())},
                "reviewer_crash_recovery": {
                    "execution_id": str(uuid4()), "reviewer_id": str(uuid4()), "next_reviewer_id": str(uuid4()),
                },
                "duplicate_decision": {
                    "execution_id": str(uuid4()), "reviewer_id": str(uuid4()), "review_key": "decision-key-1",
                },
                "concurrent_reviews": {
                    "execution_id": str(uuid4()), "reviewer_id": str(uuid4()), "review_key": "concurrent-key-1",
                },
                "duplicate_deliverable": {
                    "execution_id": str(uuid4()), "reviewer_id": str(uuid4()),
                    "first_review_key": "deliverable-key-1", "second_review_key": "deliverable-key-2",
                },
                "hash_verification": {
                    "execution_id": str(uuid4()), "reviewer_id": str(uuid4()),
                    "output_id": str(uuid4()), "review_key": "hash-review-key",
                },
                "transaction_rollback": {
                    "execution_id": str(uuid4()), "reviewer_id": str(uuid4()),
                    "output_id": str(uuid4()), "task_id": str(uuid4()), "review_key": "rollback-review-key",
                },
                "defect_lifecycle": {
                    "execution_id": str(uuid4()), "reviewer_id": str(uuid4()),
                    "agent_id": str(uuid4()), "task_id": str(uuid4()),
                    "required_role_code": "TEST_ROLE",
                    "reject_review_key": "reject-review-key",
                    "approve_review_key": "approve-review-key",
                },
            },
        }
        return {
            "RUNTIME_IT_DATABASE_URL": str(URL.create(
                "mssql+pyodbc",
                host="localhost",
                database="AICompany_M1_IT_unit",
                query={
                    "driver": "ODBC Driver 17 for SQL Server",
                    "trusted_connection": "yes",
                },
            )),
            "RUNTIME_IT_EXPECTED_DATABASE": "AICompany_M1_IT_unit",
            "RUNTIME_IT_EXPECTED_SERVER_NAME": "LOCALSQL",
            "RUNTIME_IT_EXPECTED_LOGIN": r"LOCAL\AICompany_M1_IT",
            "RUNTIME_IT_DATABASE_MARKER_ID": str(uuid4()),
            "RUNTIME_IT_TEST_RUN_ID": test_run_id,
            "RUNTIME_IT_FIXTURE_JSON": json.dumps(fixture_payload),
            "RUNTIME_IT_SYNTHETIC_AUTHORIZED": "1",
            "RUNTIME_IT_CLEANUP_ENABLED": "1",
        }

    def _target(self):
        return load_integration_target(self._environment())

    def test_complete_local_synthetic_configuration_is_accepted_offline(self):
        target = self._target()

        self.assertEqual(target.expected_database, "AICompany_M1_IT_unit")
        self.assertEqual(set(target.fixtures), REQUIRED_FIXTURES)

    def test_missing_database_url_is_rejected(self):
        environment = self._environment()
        environment["RUNTIME_IT_DATABASE_URL"] = ""

        with self.assertRaises(IntegrationSafetyError):
            load_integration_target(environment)

    def test_production_database_name_is_rejected(self):
        environment = self._environment()
        environment["RUNTIME_IT_EXPECTED_DATABASE"] = "AICompany"

        with self.assertRaises(IntegrationSafetyError):
            load_integration_target(environment)

    def test_nonlocal_server_is_rejected(self):
        environment = self._environment()
        environment["RUNTIME_IT_DATABASE_URL"] = str(URL.create(
            "mssql+pyodbc",
            host="sql.example.com",
            database=environment["RUNTIME_IT_EXPECTED_DATABASE"],
            query={"driver": "ODBC Driver 17 for SQL Server", "trusted_connection": "yes"},
        ))

        with self.assertRaises(IntegrationSafetyError):
            load_integration_target(environment)

    def test_password_in_connection_url_is_rejected(self):
        environment = self._environment()
        environment["RUNTIME_IT_DATABASE_URL"] = str(URL.create(
            "mssql+pyodbc",
            username="test",
            password="not-a-real-password",
            host="localhost",
            database=environment["RUNTIME_IT_EXPECTED_DATABASE"],
            query={"driver": "ODBC Driver 17 for SQL Server", "trusted_connection": "yes"},
        ))

        with self.assertRaises(IntegrationSafetyError):
            load_integration_target(environment)

    def test_missing_explicit_synthetic_authorization_is_rejected(self):
        environment = self._environment()
        environment["RUNTIME_IT_SYNTHETIC_AUTHORIZED"] = "0"

        with self.assertRaises(IntegrationSafetyError):
            load_integration_target(environment)

    def test_missing_cleanup_opt_in_is_rejected(self):
        environment = self._environment()
        environment["RUNTIME_IT_CLEANUP_ENABLED"] = "0"

        with self.assertRaises(IntegrationSafetyError):
            load_integration_target(environment)

    def test_snapshot_budget_rejects_row_limit_incrementally(self):
        budget = SnapshotBudget()
        with patch("tests.integration.sqlserver_safety.MAX_SNAPSHOT_ROWS", 1):
            budget.add({"id": 1})
            with self.assertRaises(IntegrationSafetyError):
                budget.add({"id": 2})

    def test_snapshot_budget_counts_utf8_bytes_incrementally(self):
        budget = SnapshotBudget()
        row = {"value": "é"}
        with patch(
            "tests.integration.sqlserver_safety.MAX_SNAPSHOT_REPR_BYTES",
            len(repr(row)),
        ):
            with self.assertRaises(IntegrationSafetyError):
                budget.add(row)

    def test_snapshot_schema_signature_detects_column_drift(self):
        inspector = MagicMock()
        inspector.get_columns.return_value = [
            {"name": "ID", "type": "int", "nullable": False},
        ]
        inspector.get_pk_constraint.return_value = {"constrained_columns": ["ID"]}
        inspector.get_foreign_keys.return_value = []
        inspector.get_unique_constraints.return_value = []
        inspector.get_check_constraints.return_value = []
        inspector.get_indexes.return_value = []
        initial = DboStateSnapshot._schema_signature(inspector, ["Example"])

        inspector.get_columns.return_value = [
            {"name": "ID", "type": "bigint", "nullable": False},
        ]
        changed = DboStateSnapshot._schema_signature(inspector, ["Example"])
        self.assertNotEqual(initial, changed)

    def test_fixture_manifest_run_id_must_match(self):
        environment = self._environment()
        payload = json.loads(environment["RUNTIME_IT_FIXTURE_JSON"])
        payload["test_run_id"] = str(uuid4())
        environment["RUNTIME_IT_FIXTURE_JSON"] = json.dumps(payload)

        with self.assertRaises(IntegrationSafetyError):
            load_integration_target(environment)

    def test_fixture_manifest_must_cover_all_cases(self):
        environment = self._environment()
        payload = json.loads(environment["RUNTIME_IT_FIXTURE_JSON"])
        payload["fixtures"].pop("hash_verification")
        environment["RUNTIME_IT_FIXTURE_JSON"] = json.dumps(payload)

        with self.assertRaises(IntegrationSafetyError):
            load_integration_target(environment)

    def test_invalid_fixture_identifier_is_rejected(self):
        environment = self._environment()
        payload = json.loads(environment["RUNTIME_IT_FIXTURE_JSON"])
        payload["fixtures"]["lease_expiration"]["execution_id"] = "not-a-uuid"
        environment["RUNTIME_IT_FIXTURE_JSON"] = json.dumps(payload)

        with self.assertRaises(IntegrationSafetyError):
            load_integration_target(environment)

    def test_connected_target_requires_exact_test_identity_and_marker(self):
        target = self._target()
        server = {
            "server_name": "LOCALSQL",
            "database_name": target.expected_database,
            "login_name": target.expected_login,
            "database_status": "ONLINE",
            "database_owner": "LOCAL\\DatabaseSetup",
            "is_sysadmin": 0,
            "is_db_owner": 0,
            "marker_update": 0,
            "marker_insert": 0,
            "marker_delete": 0,
            "marker_alter": 0,
        }
        marker = {
            "marker_id": target.marker_id,
            "database_name": target.expected_database,
            "purpose": "synthetic-integration-only",
            "created_by_login": "LOCAL\\DatabaseSetup",
        }

        validate_connected_identity(target, server, marker)

    def test_connected_sysadmin_is_rejected(self):
        target = self._target()
        server = self._server(target, is_sysadmin=1)

        with self.assertRaises(IntegrationSafetyError):
            validate_connected_identity(target, server, self._marker(target))

    def test_connected_db_owner_is_rejected(self):
        target = self._target()
        server = self._server(target, is_db_owner=1)

        with self.assertRaises(IntegrationSafetyError):
            validate_connected_identity(target, server, self._marker(target))

    def test_connected_server_database_and_login_must_match_exactly(self):
        target = self._target()
        for field, value in (
            ("server_name", "OTHER"),
            ("database_name", "AICompany"),
            ("login_name", "LOCAL\\Administrator"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(IntegrationSafetyError):
                    validate_connected_identity(
                        target, self._server(target, **{field: value}), self._marker(target)
                    )

    def test_test_principal_cannot_modify_ownership_marker(self):
        target = self._target()

        with self.assertRaises(IntegrationSafetyError):
            validate_connected_identity(
                target, self._server(target, marker_update=1), self._marker(target)
            )

    def test_missing_or_mismatched_marker_is_rejected(self):
        target = self._target()

        with self.assertRaises(IntegrationSafetyError):
            validate_connected_identity(target, self._server(target), None)

        marker = self._marker(target)
        marker["database_name"] = "AICompany"
        with self.assertRaises(IntegrationSafetyError):
            validate_connected_identity(target, self._server(target), marker)

    def _server(self, target: IntegrationTarget, **overrides):
        server = {
            "server_name": "LOCALSQL",
            "database_name": target.expected_database,
            "login_name": target.expected_login,
            "database_status": "ONLINE",
            "database_owner": "LOCAL\\DatabaseSetup",
            "is_sysadmin": 0,
            "is_db_owner": 0,
            "marker_update": 0,
            "marker_insert": 0,
            "marker_delete": 0,
            "marker_alter": 0,
        }
        server.update(overrides)
        return server

    @staticmethod
    def _marker(target):
        return {
            "marker_id": target.marker_id,
            "database_name": target.expected_database,
            "purpose": "synthetic-integration-only",
            "created_by_login": "LOCAL\\DatabaseSetup",
        }


if __name__ == "__main__":
    unittest.main()
