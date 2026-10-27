import unittest

from app.services.agent_factory import build_factory_blueprint
from app.services.code_factory import build_code_package
from app.services.testing_execution_factory import build_testing_execution_package
from app.services.build_factory import build_release_artifact_package
from app.services.deployment_factory import build_deployment_package
from app.services.hosting_factory import build_hosting_package
from app.api.workforce import BuildPlanRequest, create_hosting_plan


class HostingFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = build_factory_blueprint(
            title="Secure analytics portal",
            description="Create a secure customer portal and API with audited analytics, SQL database, backup, monitoring, and cloud hosting.",
            technology_changes=["React", "Python", "Azure AI"], priority="High",
        )
        code = build_code_package(cls.blueprint["technical_delivery_package"], "python")
        tests = build_testing_execution_package(
            cls.blueprint["technical_delivery_package"], cls.blueprint["project_delivery_package"],
            cls.blueprint["delivery_execution_package"], code)
        build = build_release_artifact_package(code, tests, cls.blueprint["project_delivery_package"])
        cls.deployment = build_deployment_package(build, tests, cls.blueprint["project_delivery_package"])

    def test_hosting_package_contains_all_requested_plans(self):
        package = build_hosting_package(self.deployment, self.blueprint["technical_delivery_package"])

        self.assertIn("hosting_blueprint", package)
        self.assertIn("application_hosting", package)
        self.assertEqual(set(package["application_hosting"]["options"]),
                         {"App Service", "Container Apps", "AKS", "Functions", "Virtual Machines"})
        self.assertEqual(set(package["environment_plans"]), {"development", "qa", "uat", "production"})
        for key in ("network_plan", "security_plan", "monitoring_plan", "recovery_plan",
                    "hosting_readiness_report", "hosting_dashboard", "execution_simulator",
                    "risk_report", "executive_summary", "hosting_execution_package"):
            self.assertTrue(package[key], key)

    def test_no_cloud_infrastructure_or_runtime_actions_are_possible(self):
        package = build_hosting_package(self.deployment, self.blueprint["technical_delivery_package"])

        self.assertEqual(package["authority"], "NONE")
        self.assertFalse(package["action_allowed"])
        self.assertFalse(package["persistence"])
        self.assertFalse(any(package["controls"].values()))
        self.assertTrue(all(not option["provisioned"] for option in package["application_hosting"]["options"].values()))
        self.assertTrue(all(not item["cloud_calls_performed"] for item in package["execution_simulator"]["scenarios"]))

    def test_unconfirmed_architecture_does_not_force_hosting_recommendation(self):
        package = build_hosting_package({}, {})

        self.assertEqual(package["application_hosting"]["recommendation_status"], "UNCONFIRMED")
        self.assertIsNone(package["application_hosting"]["recommended_option"])
        self.assertEqual(package["hosting_readiness_report"]["status"], "NOT READY")
        self.assertTrue(package["hosting_readiness_report"]["blockers"])

    def test_workforce_blueprint_includes_hosting_package_without_mutations(self):
        blueprint = build_factory_blueprint(
            title="Secure analytics portal",
            description="Create a secure portal and API with audited database access.",
            priority="High",
        )

        self.assertIn("hosting_execution_package", blueprint)
        self.assertEqual(blueprint["hosting_execution_package"]["authority"], "NONE")
        self.assertFalse(any(blueprint["hosting_execution_package"]["controls"].values()))

    def test_api_composes_plan_only_and_makes_no_cloud_calls(self):
        request = BuildPlanRequest(
            title="Secure analytics portal",
            description="Create a secure portal with audited API access and database backups.",
            backend_language="python", semantic_version="0.2.0",
        )

        package = create_hosting_plan(request)

        self.assertEqual(package["status"], "PLANNING_AND_SIMULATION_ONLY")
        self.assertEqual(package["authority"], "NONE")
        self.assertEqual(package["hosting_readiness_report"]["status"], "NOT READY")
        self.assertFalse(any(package["controls"].values()))


if __name__ == "__main__":
    unittest.main()