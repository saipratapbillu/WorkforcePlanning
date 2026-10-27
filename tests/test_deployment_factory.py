import unittest

from app.services.agent_factory import build_factory_blueprint
from app.services.code_factory import build_code_package
from app.services.testing_execution_factory import build_testing_execution_package
from app.services.build_factory import build_release_artifact_package
from app.services.deployment_factory import build_deployment_package
from app.api.workforce import BuildPlanRequest, create_deployment_plan


class DeploymentFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = build_factory_blueprint(
            title="Secure analytics portal",
            description="Create a customer analytics portal with external API and database integrations, authentication, backup, monitoring, and release review.",
            technology_changes=["React", "Python", "Azure AI"], priority="High",
        )
        cls.code = build_code_package(cls.blueprint["technical_delivery_package"], "python")
        cls.tests = build_testing_execution_package(
            cls.blueprint["technical_delivery_package"], cls.blueprint["project_delivery_package"],
            cls.blueprint["delivery_execution_package"], cls.code)
        cls.build = build_release_artifact_package(
            cls.code, cls.tests, cls.blueprint["project_delivery_package"])

    def test_deployment_package_contains_all_readiness_and_planning_sections(self):
        package = build_deployment_package(
            self.build, self.tests, self.blueprint["project_delivery_package"])

        for key in ("deployment_blueprint", "environment_plan", "release_plan", "rollback_plan",
                    "security_gates", "readiness_report", "risk_report", "deployment_dashboard",
                    "execution_simulation", "executive_deployment_package"):
            self.assertTrue(package[key], key)
        self.assertEqual(set(package["environment_plan"]), {"development", "qa", "uat", "production"})
        self.assertEqual(package["status"], "PLANNING_AND_SIMULATION_ONLY")
        self.assertEqual(package["authority"], "NONE")
        self.assertFalse(any(package["controls"].values()))

    def test_missing_build_and_test_evidence_blocks_release(self):
        package = build_deployment_package({}, {}, {})

        self.assertIn(package["readiness_report"]["status"], {"NOT READY", "PARTIALLY READY"})
        self.assertFalse(package["readiness_report"]["deployment_ready"])
        self.assertTrue(package["readiness_report"]["blockers"])
        self.assertFalse(package["release_plan"]["release_authorized"])

    def test_simulation_has_only_forecast_outcomes_no_actions(self):
        package = build_deployment_package(
            self.build, self.tests, self.blueprint["project_delivery_package"])

        self.assertEqual({scenario["scenario"] for scenario in package["execution_simulation"]["scenarios"]},
                         {"success_path", "rollback_path", "blocked_path"})
        self.assertTrue(all(not scenario["deployment_performed"] for scenario in package["execution_simulation"]["scenarios"]))
        self.assertFalse(package["execution_simulation"]["cloud_calls_performed"])
        self.assertFalse(package["rollback_plan"]["rollback_executed"])

    def test_api_composes_plan_only_and_returns_no_cloud_or_deployment_action(self):
        request = BuildPlanRequest(
            title="Secure analytics portal",
            description="Create a secure portal with audited API access and release workflow.",
            backend_language="python", semantic_version="0.2.0",
        )

        package = create_deployment_plan(request)

        self.assertEqual(package["status"], "PLANNING_AND_SIMULATION_ONLY")
        self.assertEqual(package["authority"], "NONE")
        self.assertEqual(package["readiness_report"]["status"], "NOT READY")
        self.assertFalse(any(package["controls"].values()))


if __name__ == "__main__":
    unittest.main()