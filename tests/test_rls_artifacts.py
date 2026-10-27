import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RlsArtifactTests(unittest.TestCase):
    def test_migration_is_gated_and_blocks_incomplete_runtime_coverage(self):
        migration = (ROOT / "sql" / "16_sql_server_rls_migration.sql").read_text(encoding="utf-8")

        self.assertIn("ApplyNativeRlsMigration", migration)
        self.assertIn("51203", migration)
        self.assertIn("51204", migration)
        self.assertIn("51206", migration)
        self.assertIn("AgentExecutionOutput", migration)

    def test_validation_reports_runtime_policy_coverage(self):
        validation = (ROOT / "sql" / "17_sql_server_rls_validation.sql").read_text(encoding="utf-8")

        for table_name in (
            "TaskAssignment", "TaskDependency", "Deliverable", "Evaluation",
            "AgentTaskQueue", "AgentExecution", "AgentExecutionOutput",
        ):
            with self.subTest(table_name=table_name):
                self.assertIn(f"('{table_name}')", validation)

    def test_rollback_is_gated_and_preserves_application_schema(self):
        rollback = (ROOT / "sql" / "18_sql_server_rls_rollback.sql").read_text(encoding="utf-8")

        self.assertIn("RollbackNativeRls", rollback)
        self.assertNotIn("DROP TABLE", rollback.upper())
        self.assertNotIn("DROP COLUMN", rollback.upper())


if __name__ == "__main__":
    unittest.main()