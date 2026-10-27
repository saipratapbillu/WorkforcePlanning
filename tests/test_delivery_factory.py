import unittest
from app.api.workforce import FactoryBlueprintRequest, create_delivery_execution_plan

from app.services.project_factory_planner import build_project_delivery_package
from app.services.delivery_factory import build_delivery_execution_package


class DeliveryFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = build_project_delivery_package(
            title="Secure analytics portal",
            description="Create a customer analytics portal with a secure API, audit, testing, and release review.",
            priority="High",
        )

    def test_delivery_package_contains_all_execution_planning_views(self):
        package = build_delivery_execution_package(self.project)

        for key in ("delivery_blueprint", "capacity_forecast", "sprint_simulation",
                    "agent_execution_plan", "release_plan", "risk_register",
                    "project_health", "delivery_dashboard", "execution_simulator",
                    "executive_delivery_package"):
            self.assertTrue(package[key], key)
        self.assertTrue(package["delivery_blueprint"]["critical_path"])
        self.assertTrue(package["delivery_blueprint"]["milestones"])
        self.assertTrue(package["execution_simulator"]["sprint_completion_projection"])
        self.assertTrue(all(item["simulated_only"] for item in package["execution_simulator"]["sprint_completion_projection"]))
        self.assertEqual(package["status"], "PLANNING_AND_SIMULATION_ONLY")
        self.assertFalse(any(package["controls"].values()))

    def test_capacity_velocity_and_assignments_are_explicit_assumptions(self):
        package = build_delivery_execution_package(self.project)

        self.assertTrue(package["capacity_forecast"]["assumption_based"])
        self.assertTrue(package["sprint_simulation"]["assumption_based"])
        self.assertIsNone(package["sprint_simulation"]["historical_velocity"])
        self.assertTrue(all(item["assignment_status"] == "NOT_ASSIGNED"
                            for item in package["agent_execution_plan"]))
        self.assertTrue(all(item["capacity_source"] == "ASSUMED_NOT_LIVE"
                            for item in package["capacity_forecast"]["roles"]))

    def test_dependency_cycle_is_rejected_without_side_effects(self):
        cyclic = {**self.project, "epic_catalog": [
            {"epic_id": "EP-A", "name": "A", "dependencies": ["EP-B"]},
            {"epic_id": "EP-B", "name": "B", "dependencies": ["EP-A"]},
        ]}

        with self.assertRaises(ValueError):
            build_delivery_execution_package(cyclic)

    def test_simulation_outputs_have_no_runtime_or_mutation_authority(self):
        package = build_delivery_execution_package(self.project)

        for scenario in package["execution_simulator"]["scenarios"]:
            self.assertFalse(scenario["execution_started"])
            self.assertFalse(scenario["project_changed"])
            self.assertFalse(scenario["assignment_changed"])
        self.assertFalse(package["release_plan"]["deployment_performed"])
        self.assertFalse(package["project_health"]["execution_authorized"])

    def test_delivery_preview_api_returns_plan_only(self):
        request = FactoryBlueprintRequest(
            title="Secure analytics portal",
            description="Create a secure analytics portal with external API integration and audited delivery.",
            priority="High",
        )

        package = create_delivery_execution_plan(request)

        self.assertEqual(package["package"], "Autonomous Delivery Factory")
        self.assertEqual(package["source_project"]["priority"], "High")
        self.assertFalse(any(package["controls"].values()))


if __name__ == "__main__":
    unittest.main()