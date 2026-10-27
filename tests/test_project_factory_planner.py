import unittest
from unittest.mock import Mock

from app.api.workforce import FactoryBlueprintRequest, create_project_delivery_blueprint
from app.services.agent_factory import build_factory_blueprint
from app.services.project_factory_planner import build_project_delivery_package


class ProjectFactoryPlannerTests(unittest.TestCase):
    def test_delivery_package_contains_all_planning_catalogs(self):
        package = build_project_delivery_package(
            title="Secure analytics portal",
            description="Create a customer portal with audited data analytics and external API integration.",
            priority="High",
            technical_delivery_package={"artifacts": {
                "executive_assessment": {"business_domain": "Data and Analytics", "complexity": "High"},
                "architecture_blueprint": {"components": [{"name": "API layer"}]},
                "security_blueprint": {"threat_review": ["Cross-tenant access"]},
                "testing_blueprint": {"acceptance_gates": ["Critical tests pass"]},
                "workforce_plan": {"role_alignment": [
                    {"discipline": "Architect", "proposed_role": "AI Solution Architect"},
                    {"discipline": "Developers", "proposed_role": "AI Backend Developer"},
                    {"discipline": "QA", "proposed_role": "AI QA Engineer"},
                    {"discipline": "Security", "proposed_role": "AI Security Engineer"},
                    {"discipline": "DevOps", "proposed_role": "AI DevOps Engineer"},
                ]},
            }},
        )

        for key in ("project_charter", "epic_catalog", "feature_catalog", "user_story_catalog",
                    "task_catalog", "sprint_plan", "work_breakdown_structure", "workforce_mapping",
                    "governance_package"):
            self.assertTrue(package[key], key)
        self.assertIn("vision", package["project_charter"])
        self.assertTrue(package["project_charter"]["success_metrics"])
        self.assertTrue(any(epic["dependencies"] for epic in package["epic_catalog"]))
        self.assertTrue(package["feature_catalog"][0]["acceptance_criteria"])
        self.assertTrue(package["user_story_catalog"][0]["acceptance_criteria"])
        self.assertGreater(package["user_story_catalog"][0]["story_points"], 0)
        self.assertTrue(package["task_catalog"][0]["task_type"])
        self.assertTrue(package["work_breakdown_structure"]["milestones"])
        developer_mapping = next(item for item in package["workforce_mapping"] if item["discipline"] == "Developer")
        self.assertTrue(developer_mapping["work_item_ids"])

    def test_sprints_are_estimates_and_every_work_item_remains_unassigned(self):
        package = build_project_delivery_package(
            title="Portal", description="Build a customer-facing web portal with secure API."
        )

        self.assertIn("assumed", package["sprint_plan"]["capacity_basis"].lower())
        self.assertIsNone(package["sprint_plan"]["historical_velocity"])
        self.assertTrue(all(item["status"] == "PROPOSED_NOT_CREATED" for item in package["task_catalog"]))
        self.assertTrue(all(item["assignment_status"] == "NOT_ASSIGNED" for item in package["workforce_mapping"]))
        self.assertFalse(any(package["controls"].values()))
        self.assertEqual(package["status"], "PLANNING_ONLY")

    def test_project_and_work_item_identifiers_are_stable_across_replay(self):
        arguments = {"title": "Secure portal", "description": "Build a secure project portal with audit logging."}

        first = build_project_delivery_package(**arguments)
        second = build_project_delivery_package(**arguments)

        self.assertEqual(first, second)
        self.assertTrue(all(item["epic_id"].startswith("EP-") for item in first["epic_catalog"]))
        self.assertTrue(all(item["story_id"].startswith("US-") for item in first["user_story_catalog"]))

    def test_workforce_blueprint_includes_project_package_and_api_preview_is_read_only(self):
        blueprint = build_factory_blueprint(
            title="Secure analytics portal",
            description="Create a customer analytics portal with a secure API.",
            priority="High",
        )
        request = FactoryBlueprintRequest(
            title="Secure analytics portal",
            description="Create a customer analytics portal with a secure API.",
            priority="High",
        )
        preview = create_project_delivery_blueprint(request)

        self.assertIn("project_delivery_package", blueprint)
        self.assertEqual(preview["package"], "Autonomous Project Factory")
        self.assertEqual(preview["project_charter"]["priority"], "High")
        self.assertFalse(any(preview["controls"].values()))


if __name__ == "__main__":
    unittest.main()