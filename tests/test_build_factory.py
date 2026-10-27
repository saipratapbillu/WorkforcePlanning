import unittest
from pydantic import ValidationError

from app.services.agent_factory import build_factory_blueprint
from app.services.code_factory import build_code_package
from app.services.testing_execution_factory import build_testing_execution_package
from app.services.build_factory import build_release_artifact_package
from app.api.workforce import BuildPlanRequest, create_build_release_plan


class BuildFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = build_factory_blueprint(
            title="Secure analytics portal",
            description="Create a secure portal with audited API access, database, test plan, and release packaging.",
            technology_changes=["React", "Python", "Azure AI"], priority="High",
        )
        cls.code_package = build_code_package(cls.blueprint["technical_delivery_package"], "python")
        cls.test_package = build_testing_execution_package(
            cls.blueprint["technical_delivery_package"], cls.blueprint["project_delivery_package"],
            cls.blueprint["delivery_execution_package"], cls.code_package,
        )

    def test_build_package_contains_manifest_dependencies_version_and_quality_gates(self):
        package = build_release_artifact_package(
            self.code_package, self.test_package, self.blueprint["project_delivery_package"])

        for key in ("build_blueprint", "artifact_manifest", "dependency_analysis",
                    "compilation_assessment", "artifact_plans", "version_plan",
                    "release_package_plan", "quality_gates", "build_risk_report",
                    "build_dashboard", "build_readiness_assessment", "build_execution_package"):
            self.assertTrue(package[key], key)
        self.assertTrue(package["artifact_manifest"]["artifacts"])
        self.assertTrue(package["dependency_analysis"]["dependencies"])
        self.assertEqual(package["version_plan"]["semantic_version"], "0.1.0")
        self.assertIn(package["build_readiness_assessment"]["status"],
                      {"NOT READY", "PARTIALLY READY", "READY"})

    def test_never_claims_compilation_or_release_readiness_without_execution(self):
        package = build_release_artifact_package(
            self.code_package, self.test_package, self.blueprint["project_delivery_package"])

        self.assertEqual(package["compilation_assessment"]["execution_status"], "NOT_COMPILED")
        self.assertIsNone(package["compilation_assessment"]["observed_build_result"])
        self.assertNotEqual(package["build_readiness_assessment"]["status"], "READY")
        self.assertEqual(package["authority"], "NONE")
        self.assertFalse(package["action_allowed"])
        self.assertFalse(package["persistence"])
        self.assertFalse(any(package["controls"].values()))
        self.assertFalse(package["artifact_plans"]["container"]["container_built"])
        self.assertFalse(package["artifact_plans"]["application"]["package_published"])

    def test_dependency_report_is_static_analysis_not_resolution(self):
        package = build_release_artifact_package(
            self.code_package, self.test_package, self.blueprint["project_delivery_package"])

        report = package["dependency_analysis"]
        self.assertFalse(report["dependencies_installed"])
        self.assertFalse(report["compatibility_verified"])
        self.assertIn("fastapi", " ".join(item["name"] for item in report["dependencies"]).lower())
        self.assertTrue(report["risks"])

    def test_missing_packages_are_not_ready(self):
        package = build_release_artifact_package({}, {}, {})

        self.assertEqual(package["build_readiness_assessment"]["status"], "NOT READY")
        self.assertTrue(package["build_readiness_assessment"]["blockers"])
        self.assertFalse(package["controls"]["compilation_performed"])

    def test_build_preview_api_returns_plan_not_source_or_compilation(self):
        request = BuildPlanRequest(
            title="Secure analytics portal",
            description="Create a secure portal with audited API access, database, and tests.",
            backend_language="python", semantic_version="1.2.3-rc.1",
        )

        package = create_build_release_plan(request)

        self.assertEqual(package["version_plan"]["semantic_version"], "1.2.3-rc.1")
        self.assertEqual(package["compilation_assessment"]["execution_status"], "NOT_COMPILED")
        self.assertNotIn("files", package)
        self.assertFalse(any(package["controls"].values()))

    def test_build_plan_rejects_invalid_semver(self):
        with self.assertRaises(ValidationError):
            BuildPlanRequest(
                title="Versioned plan", description="This package needs a build version.",
                semantic_version="latest",
            )


if __name__ == "__main__":
    unittest.main()