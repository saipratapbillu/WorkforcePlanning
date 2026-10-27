import unittest

from app.api.workforce import FactoryBlueprintRequest, create_enterprise_architecture
from app.services.agent_factory import build_factory_blueprint
from app.services.autonomous_enterprise import build_autonomous_enterprise_package


class AutonomousEnterpriseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = build_factory_blueprint(
            title="Secure analytics portal",
            description="Create a customer analytics portal with SQL, identity, monitoring, and support.",
            technology_changes=["React", "Python"], priority="High",
        )
        cls.package = build_autonomous_enterprise_package(cls.blueprint)

    def test_six_directors_with_required_areas(self):
        expected = {
            "ai_ceo": ("strategy_engine", "portfolio_management", "investment_governance",
                       "business_outcome_management", "executive_dashboard"),
            "ai_cto": ("technology_governance", "architecture_governance", "engineering_governance", "platform_strategy"),
            "ai_workforce_director": ("workforce_governance", "agent_governance", "skill_governance", "capacity_governance"),
            "ai_program_director": ("portfolio_planning", "program_governance", "project_governance", "delivery_governance"),
            "ai_release_director": ("release_governance", "change_governance", "deployment_governance", "rollback_governance"),
            "ai_operations_director": ("operations_governance", "monitoring_governance", "incident_governance",
                                       "problem_governance", "cost_governance"),
        }
        for key, areas in expected.items():
            for area in areas:
                self.assertTrue(self.package[key][area]["capabilities"], f"{key}.{area}")
                self.assertFalse(self.package[key][area]["enabled"])
            self.assertFalse(self.package[key]["activated"])

    def test_control_plane_runtime_and_governance_model(self):
        for engine in ("policy_engine", "decision_engine", "governance_engine", "approval_engine", "risk_engine", "audit_engine"):
            self.assertFalse(self.package["control_plane"][engine]["deployed"])
            self.assertEqual(self.package["control_plane"][engine]["default_effect"], "DENY")
        for part in ("agent_runtime", "workflow_runtime", "decision_runtime", "enterprise_event_mesh", "integration_architecture"):
            self.assertFalse(self.package["runtime_blueprint"][part]["deployed"])
        for part in ("authority_model", "delegation_model", "risk_controls", "human_override_controls", "emergency_controls"):
            self.assertTrue(self.package["governance_model"][part])
        for key in ("enterprise_architecture", "reference_architecture", "future_roadmap", "executive_summary"):
            self.assertTrue(self.package["autonomous_enterprise_package"][key])

    def test_nothing_is_active_or_authorized(self):
        self.assertEqual(self.package["status"], "ARCHITECTURE_ONLY")
        self.assertEqual(self.package["authority"], "NONE")
        self.assertFalse(self.package["action_allowed"])
        self.assertFalse(self.package["persistence"])
        self.assertFalse(any(self.package["controls"].values()))
        self.assertEqual(self.package["enterprise_readiness"]["status"], "NOT READY")
        self.assertEqual(self.package["executive_dashboard"]["directors_active"], 0)

    def test_empty_input_and_blueprint_integration(self):
        self.assertEqual(build_autonomous_enterprise_package(None)["status"], "ARCHITECTURE_ONLY")
        self.assertEqual(self.blueprint["autonomous_enterprise_package"]["status"], "ARCHITECTURE_ONLY")

    def test_authorized_api_returns_architecture_only(self):
        package = create_enterprise_architecture(FactoryBlueprintRequest(
            title="Secure analytics portal", description="Create a secure portal with audited API access."))
        self.assertEqual(package["authority"], "NONE")
        self.assertFalse(any(package["controls"].values()))


if __name__ == "__main__":
    unittest.main()
