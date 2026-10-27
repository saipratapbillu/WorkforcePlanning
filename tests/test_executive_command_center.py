import unittest

from app.api.workforce import FactoryBlueprintRequest, create_executive_command_center
from app.services.agent_factory import build_factory_blueprint
from app.services.executive_command_center import build_executive_command_center


class ExecutiveCommandCenterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = build_factory_blueprint(
            title="Secure analytics portal",
            description="Create a customer analytics portal with SQL, identity, monitoring, and support.",
            technology_changes=["React", "Python"], priority="High",
        )
        cls.center = build_executive_command_center(cls.blueprint)

    def test_all_dashboards_present(self):
        ceo = self.center["ceo_dashboard"]
        for key in ("portfolio_health", "strategic_objectives", "business_outcomes",
                    "roi_forecast", "investment_status", "executive_risks"):
            self.assertIn(key, ceo)
        self.assertTrue(ceo["strategic_objectives"] and ceo["executive_risks"])
        for key in ("workforce_readiness", "capacity_coverage", "skill_coverage",
                    "certification_coverage", "replacement_readiness", "assignment_readiness"):
            self.assertIn(key, self.center["workforce_dashboard"])
        delivery = self.center["delivery_dashboard"]
        self.assertEqual((delivery["projects"], delivery["epics"], delivery["features"], delivery["stories"], delivery["tasks"]),
                         (1, 5, 5, 5, 25))
        for key in ("sprint_health", "release_readiness"):
            self.assertIn(key, delivery)
        for key in ("testing_readiness", "build_readiness", "deployment_readiness",
                    "hosting_readiness", "operations_readiness"):
            self.assertIn(key, self.center["quality_dashboard"])
        for key in ("approval_readiness", "risk_index", "compliance_status", "override_analytics", "governance_score"):
            self.assertIn(key, self.center["governance_dashboard"])
        for key in ("autonomy_readiness", "decision_coverage", "risk_coverage", "override_coverage"):
            self.assertIn(key, self.center["autonomy_dashboard"])
        self.assertEqual(self.center["autonomy_dashboard"]["risk_coverage"]["tiers_defined"], 4)

    def test_unknown_values_are_not_fabricated(self):
        self.assertIsNone(self.center["ceo_dashboard"]["roi_forecast"]["value"])
        self.assertIsNone(self.center["ceo_dashboard"]["investment_status"]["approved_budget"])
        self.assertEqual(self.center["governance_dashboard"]["governance_score"], "UNAVAILABLE")
        self.assertEqual(self.center["enterprise_readiness"]["status"], "NOT READY")
        self.assertEqual(self.center["quality_dashboard"]["overall_status"], "NOT READY")

    def test_dashboard_only_safety_flags(self):
        self.assertEqual(self.center["status"], "DASHBOARD_ONLY")
        self.assertEqual(self.center["authority"], "NONE")
        self.assertFalse(self.center["action_allowed"])
        self.assertFalse(self.center["persistence"])
        self.assertFalse(any(self.center["controls"].values()))

    def test_empty_input_and_blueprint_integration(self):
        empty = build_executive_command_center(None)
        self.assertEqual(empty["enterprise_readiness"]["status"], "NOT READY")
        self.assertEqual(empty["delivery_dashboard"]["projects"], 0)
        self.assertEqual(self.blueprint["executive_command_center"]["status"], "DASHBOARD_ONLY")

    def test_authorized_api_returns_dashboard(self):
        result = create_executive_command_center(FactoryBlueprintRequest(
            title="Secure analytics portal", description="Create a secure portal with audited API access."))
        self.assertEqual(result["authority"], "NONE")
        self.assertIn("executive_dashboard", result)


if __name__ == "__main__":
    unittest.main()
