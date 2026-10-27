import unittest

from app.api.workforce import BuildPlanRequest, create_operations_plan
from app.services.agent_factory import build_factory_blueprint
from app.services.operations_factory import build_operations_package


class OperationsFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = build_factory_blueprint(
            title="Secure analytics portal",
            description="Create a customer analytics portal with SQL, identity, monitoring, backups, patching, and support.",
            technology_changes=["React", "Python", "Azure AI"], priority="High",
        )

    def test_operations_package_contains_sre_and_support_plans(self):
        package = build_operations_package(
            self.blueprint["hosting_execution_package"],
            self.blueprint["delivery_execution_package"],
        )

        for key in ("operations_blueprint", "operations_readiness_report", "monitoring_strategy",
                    "observability_strategy", "incident_management", "problem_management",
                    "change_management", "capacity_management", "cost_optimization",
                    "patch_management", "runbook_catalog", "sre_dashboard", "operations_package"):
            self.assertTrue(package[key], key)
        self.assertIn("synthetic_monitoring", package["monitoring_strategy"])
        self.assertIn("war_room_process", package["incident_management"])
        self.assertIn("known_error_database_plan", package["problem_management"])
        self.assertIn("emergency_change_process", package["change_management"])
        self.assertIn("storage_growth_forecast", package["capacity_management"])
        self.assertIn("patch_calendar", package["patch_management"])

    def test_no_operational_resources_or_integrations_are_created(self):
        package = build_operations_package(
            self.blueprint["hosting_execution_package"],
            self.blueprint["delivery_execution_package"],
        )

        self.assertEqual(package["authority"], "NONE")
        self.assertFalse(package["action_allowed"])
        self.assertFalse(package["persistence"])
        self.assertFalse(any(package["controls"].values()))
        self.assertEqual(package["operations_readiness_report"]["status"], "NOT READY")
        for action in ("monitoring_created", "alerts_created", "tickets_created", "integrations_created", "runtime_started"):
            self.assertFalse(package["controls"][action])

    def test_capacity_and_cost_are_not_fabricated_without_live_inputs(self):
        package = build_operations_package({}, {})

        self.assertIsNone(package["capacity_management"]["current_capacity_hours"])
        self.assertIsNone(package["capacity_management"]["storage_growth_forecast"]["estimated_gb"])
        self.assertIsNone(package["cost_optimization"]["monthly_cost_estimate"])
        self.assertEqual(package["sre_dashboard"]["capacity_dashboard"]["status"], "UNAVAILABLE")

    def test_authorized_api_composes_operations_plan_without_actions(self):
        request = BuildPlanRequest(
            title="Secure analytics portal",
            description="Create a secure portal with audited API access and support plan.",
            backend_language="python", semantic_version="0.2.0",
        )

        package = create_operations_plan(request)

        self.assertEqual(package["status"], "PLANNING_AND_SIMULATION_ONLY")
        self.assertEqual(package["authority"], "NONE")
        self.assertFalse(any(package["controls"].values()))

    def test_workforce_blueprint_includes_operations_package(self):
        package = self.blueprint.get("operations_execution_package")
        self.assertTrue(package)
        self.assertEqual(package["status"], "PLANNING_AND_SIMULATION_ONLY")
        self.assertEqual(package["operations_readiness_report"]["status"], "NOT READY")
        self.assertFalse(any(package["controls"].values()))


if __name__ == "__main__":
    unittest.main()