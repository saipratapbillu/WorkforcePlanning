import unittest
from unittest.mock import patch

from app.api.workforce import FactoryBlueprintRequest, create_approval_sandbox_preview
from app.services.agent_factory import build_factory_blueprint
from app.services.approval_sandbox import build_approval_sandbox_package


class ApprovalSandboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = build_factory_blueprint(
            title="Secure analytics portal",
            description="Create a secure portal with audited API access, testing, release, and workforce planning.",
            technology_changes=["React", "Python", "Azure AI"], priority="High",
        )

    def test_sandbox_contains_recommendations_and_human_review_queue(self):
        package = build_approval_sandbox_package(self.blueprint)

        self.assertEqual(set(package["recommendation_engine"]["recommendations"]), {
            "worker", "assignment", "certification", "release", "governance"})
        self.assertTrue(package["review_queue"])
        self.assertTrue(all(item["state"] == "PENDING_HUMAN_REVIEW" for item in package["review_queue"]))
        self.assertTrue(package["human_review_workflow"]["states"])
        self.assertTrue(package["override_management"]["categories"])
        self.assertTrue(package["decision_audit"]["event_schema"])

    def test_no_operational_decision_or_persistence_is_possible(self):
        package = build_approval_sandbox_package(self.blueprint)

        self.assertEqual(package["authority"], "NONE")
        self.assertFalse(package["action_allowed"])
        self.assertFalse(package["persistence"])
        self.assertFalse(any(package["controls"].values()))
        self.assertFalse(package["human_review_workflow"]["workflow_executed"])
        self.assertEqual(package["approval_dashboard"]["approval_accuracy"], "UNAVAILABLE_NO_DECISIONS")

    def test_sandbox_scenarios_are_transient_and_analytics_not_fabricated(self):
        package = build_approval_sandbox_package(self.blueprint)

        self.assertEqual({item["scenario"] for item in package["sandbox_simulation"]["scenarios"]},
                         {"recommendation_for_review", "human_rejection", "human_override", "escalation"})
        self.assertTrue(all(item["simulation_only"] and not item["decision_persisted"]
                            for item in package["sandbox_simulation"]["scenarios"]))
        self.assertEqual(package["governance_analytics"]["override_frequency"], "UNAVAILABLE_NO_DECISIONS")
        self.assertIsNone(package["confidence_engine"]["recommendation_confidence_percent"])
        self.assertEqual(package["confidence_engine"]["decision_strength"], "UNVERIFIED")

    def test_preview_route_returns_package_without_database_access(self):
        body = FactoryBlueprintRequest(
            title="Secure analytics portal",
            description="Create a secure portal with audited API access, testing, release, and workforce planning.",
            technology_changes=["React", "Python"], priority="High",
        )
        expected = self.blueprint["approval_sandbox_package"]
        with patch("app.api.workforce.build_factory_blueprint", return_value=self.blueprint) as builder:
            result = create_approval_sandbox_preview(body)

        self.assertEqual(result, expected)
        builder.assert_called_once()


if __name__ == "__main__":
    unittest.main()