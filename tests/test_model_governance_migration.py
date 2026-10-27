import unittest
from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[1] / "sql" / "20_ai_model_registry_and_evaluation_templates.sql"


class ModelGovernanceMigrationTests(unittest.TestCase):
    def test_model_tables_are_create_if_missing_and_do_not_seed_approved_models(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        for table in ("AIModelProvider", "AIModelCatalog", "AIModelApproval", "EvaluationTemplate", "EvaluationTemplateCriterion"):
            with self.subTest(table=table):
                self.assertIn(f"OBJECT_ID('dbo.{table}','U') IS NULL", sql)
        self.assertIn("ApprovalRequired bit NOT NULL", sql)
        self.assertIn("DEFAULT 'Pending'", sql)
        self.assertNotIn("INSERT dbo.AIModelCatalog", sql)
        self.assertIn("No model is inserted as Approved", sql)

    def test_all_requested_template_criteria_are_seeded(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        for name in (
            "Prompt Quality", "Task Completion", "Accuracy", "Reasoning",
            "Prompt Injection", "Data Leakage", "PII Exposure", "Authorization",
            "Secrets Handling", "API Usage", "Auditability", "Traceability", "Policy Compliance",
        ):
            with self.subTest(criterion=name):
                self.assertIn(name, sql)


if __name__ == "__main__":
    unittest.main()