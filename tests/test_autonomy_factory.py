import unittest

from app.api.workforce import FactoryBlueprintRequest, create_autonomy_plan
from app.services.agent_factory import build_factory_blueprint
from app.services.autonomy_factory import build_autonomy_package, classify_risk


class AutonomyFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = build_factory_blueprint(
            title="Secure analytics portal",
            description="Create a customer analytics portal with SQL, identity, monitoring, backups, and support.",
            technology_changes=["React", "Python"], priority="High",
        )
        cls.package = build_autonomy_package(cls.blueprint)

    def test_package_contains_all_workstreams(self):
        for key in ("autonomy_blueprint", "autonomy_readiness_report", "decision_catalog", "autonomy_policy_engine",
                    "risk_matrix_engine", "human_override_framework", "rollback_governance",
                    "autonomy_dashboard", "autonomy_simulation", "executive_summary", "controlled_autonomy_package"):
            self.assertTrue(self.package[key], key)
        for key in ("autonomy_blueprint", "policy_package", "risk_package", "override_package",
                    "rollback_package", "readiness_report", "executive_summary"):
            self.assertTrue(self.package["controlled_autonomy_package"][key], key)
        for key in ("decision_dashboard", "risk_dashboard", "policy_dashboard", "readiness_dashboard"):
            self.assertIn(key, self.package["autonomy_dashboard"])
        self.assertEqual({s["scenario"] for s in self.package["autonomy_simulation"]["scenarios"]},
                         {"approval", "override", "rollback", "blocked"})

    def test_all_four_risk_tiers_are_populated_and_covered(self):
        counts = self.package["decision_catalog"]["tier_counts"]
        for tier in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            self.assertGreater(counts[tier], 0, tier)
        self.assertEqual(self.package["autonomy_policy_engine"]["policy_coverage"]["coverage_percent"], 100.0)
        self.assertFalse(self.package["autonomy_policy_engine"]["policy_coverage"]["uncovered_decisions"])

    def test_risk_classification_escalates_severe_impact(self):
        self.assertEqual(classify_risk(1, 1)["tier"], "LOW")
        self.assertEqual(classify_risk(2, 3)["tier"], "MEDIUM")
        self.assertEqual(classify_risk(4, 4)["tier"], "HIGH")
        self.assertEqual(classify_risk(5, 5)["tier"], "CRITICAL")
        self.assertEqual(classify_risk(1, 5)["tier"], "HIGH")

    def test_irreversible_and_critical_decisions_are_never_autonomous(self):
        for decision in self.package["decision_catalog"]["decision_inventory"]:
            self.assertFalse(decision["autonomy_enabled"])
            self.assertFalse(decision["action_allowed"])
            if not decision["reversible"]:
                self.assertIn(decision["risk_tier"], ("HIGH", "CRITICAL"))
            if decision["risk_tier"] == "CRITICAL":
                self.assertEqual(decision["future_autonomy_ceiling"], "HUMAN_ONLY")

    def test_readiness_is_not_ready_and_safety_flags_hold(self):
        self.assertEqual(self.package["autonomy_readiness_report"]["overall_autonomy_readiness"]["status"], "NOT READY")
        self.assertEqual(self.package["authority"], "NONE")
        self.assertFalse(self.package["action_allowed"])
        self.assertFalse(self.package["persistence"])
        self.assertFalse(any(self.package["controls"].values()))
        self.assertFalse(self.package["human_override_framework"]["overrides_executed"])
        self.assertFalse(self.package["rollback_governance"]["rollbacks_executed"])

    def test_empty_input_and_blueprint_integration(self):
        empty = build_autonomy_package(None)
        self.assertEqual(empty["status"], "DESIGN_ONLY")
        self.assertEqual(self.blueprint["autonomy_execution_package"]["status"], "DESIGN_ONLY")

    def test_authorized_api_returns_design_only_package(self):
        package = create_autonomy_plan(FactoryBlueprintRequest(
            title="Secure analytics portal", description="Create a secure portal with audited API access."))
        self.assertEqual(package["authority"], "NONE")
        self.assertFalse(any(package["controls"].values()))


if __name__ == "__main__":
    unittest.main()
