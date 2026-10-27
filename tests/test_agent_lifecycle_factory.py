import unittest

from app.api.workforce import FactoryBlueprintRequest, create_agent_lifecycle_plan
from app.services.agent_factory import build_factory_blueprint
from app.services.agent_lifecycle_factory import build_agent_lifecycle_package


class AgentLifecycleFactoryTests(unittest.TestCase):
    def test_package_generates_profiles_jds_skills_certification_and_lifecycle_blueprints(self):
        workforce = build_factory_blueprint(
            title="Secure analytics portal",
            description="Create a secure Angular and React portal with Python API, Azure AI, OpenAI and Anthropic integrations.",
            technology_changes=["Angular", "React", "Python", "Azure AI", "OpenAI", "Anthropic"],
        )
        package = build_agent_lifecycle_package(workforce)

        self.assertEqual(len(package["agent_catalog"]), 10)
        self.assertTrue(package["agent_profiles"])
        profile = next(item for item in package["agent_profiles"] if item["role_name"] == "AI Frontend Developer")
        self.assertTrue(profile["agent_id"].startswith("SIM-AGENT-"))
        self.assertTrue(profile["job_description"]["governance_responsibilities"])
        self.assertTrue({"Technical", "Domain", "Security", "Governance"}.issubset(
            {item["category"] for item in profile["skill_matrix"]}))
        self.assertEqual(set(profile["certification_path"]["tiers"]), {"Bronze", "Silver", "Gold", "Platinum"})
        self.assertEqual([item["phase"] for item in package["lifecycle_blueprints"]],
                         ["Created", "Provisioned", "Certified", "Active", "Assigned", "Paused", "Retired"])
        self.assertTrue(package["upskilling_factory"]["technology_updates"])
        self.assertTrue(package["assignment_readiness"]["recommendations"])
        self.assertTrue(package["replacement_plans"])
        self.assertTrue(package["governance_package"])
        self.assertTrue(package["workforce_director_report"])

    def test_simulation_authority_and_lifecycle_actions_are_disabled(self):
        package = build_agent_lifecycle_package(build_factory_blueprint(
            title="Requirements service", description="Create a secure requirements service with audited API access."
        ))

        self.assertEqual(package["authority"], "NONE")
        self.assertFalse(package["action_allowed"])
        self.assertFalse(package["persistence"])
        self.assertFalse(any(package["controls"].values()))
        self.assertTrue(all(item["creation_status"] == "SIMULATED_NOT_CREATED" for item in package["agent_profiles"]))
        self.assertTrue(all(item["certification_status"] == "NOT_ISSUED" for item in package["agent_profiles"]))
        self.assertTrue(all(item["assignment_status"] == "NOT_ASSIGNED" for item in package["assignment_readiness"]["recommendations"]))
        self.assertIsNone(package["assignment_readiness"]["readiness_score_percent"])
        self.assertEqual(package["assignment_readiness"]["status"], "UNVERIFIED_NO_CANDIDATE_ROSTER")

    def test_lifecycle_preview_api_returns_simulation_only_package(self):
        request = FactoryBlueprintRequest(
            title="Secure analytics portal",
            description="Create a secure portal with audited API access and human review.",
            technology_changes=["React", "OpenAI", "Anthropic"],
        )

        package = create_agent_lifecycle_plan(request)

        self.assertEqual(package["status"], "SIMULATION_ONLY")
        self.assertIn("React", {item["technology"] for item in package["upskilling_factory"]["technology_updates"]})
        self.assertIn("OpenAI", {item["technology"] for item in package["upskilling_factory"]["technology_updates"]})
        self.assertIn("Anthropic", {item["technology"] for item in package["upskilling_factory"]["technology_updates"]})
        self.assertFalse(any(package["controls"].values()))


if __name__ == "__main__":
    unittest.main()