import unittest

from app.api.workforce import FactoryCodePackageRequest, create_test_execution_simulation
from app.services.agent_factory import build_factory_blueprint
from app.services.code_factory import build_code_package
from app.services.testing_execution_factory import build_testing_execution_package


class TestingExecutionFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = build_factory_blueprint(
            title="Secure analytics portal",
            description="Create a customer analytics portal with authenticated API, audit, testing, and cloud release.",
            technology_changes=["React", "Python", "Azure AI"],
            priority="High",
        )
        cls.code_package = build_code_package(cls.blueprint["technical_delivery_package"], "python")

    def test_test_package_contains_all_test_and_quality_views(self):
        package = build_testing_execution_package(
            self.blueprint["technical_delivery_package"],
            self.blueprint["project_delivery_package"],
            self.blueprint["delivery_execution_package"],
            self.code_package,
        )

        for key in ("testing_strategy", "test_coverage_map", "unit_test_report",
                    "integration_report", "security_report", "performance_report",
                    "uat_report", "defect_report", "quality_dashboard", "release_assessment",
                    "test_execution_package"):
            self.assertTrue(package[key], key)
        self.assertIn(package["release_assessment"]["status"],
                      {"NOT READY", "PARTIALLY READY", "READY"})
        self.assertNotEqual(package["release_assessment"]["status"], "READY")

    def test_simulation_metrics_are_not_observed_and_no_execution_occurs(self):
        package = build_testing_execution_package(
            self.blueprint["technical_delivery_package"],
            self.blueprint["project_delivery_package"],
            self.blueprint["delivery_execution_package"],
            self.code_package,
        )

        self.assertEqual(package["unit_test_report"]["execution_status"], "NOT_EXECUTED")
        self.assertEqual(package["unit_test_report"]["pass_rate_basis"], "SIMULATED_FORECAST_NOT_OBSERVED")
        self.assertIsNone(package["unit_test_report"]["observed_pass_rate_percent"])
        self.assertFalse(any(package["controls"].values()))
        self.assertTrue(package["security_report"]["findings"])
        self.assertTrue(package["defect_report"]["expected_defects"])

    def test_release_gate_is_blocked_by_unexecuted_tests_and_security_templates(self):
        package = build_testing_execution_package(
            self.blueprint["technical_delivery_package"],
            self.blueprint["project_delivery_package"],
            self.blueprint["delivery_execution_package"],
            self.code_package,
        )

        self.assertEqual(package["release_assessment"]["status"], "NOT READY")
        blockers = " ".join(package["release_assessment"]["blockers"]).lower()
        self.assertIn("not executed", blockers)
        self.assertIn("identity", blockers)

    def test_missing_packages_return_explicit_unavailable_basis(self):
        package = build_testing_execution_package({}, {}, {}, None)

        self.assertEqual(package["status"], "SIMULATION_ONLY")
        self.assertEqual(package["test_coverage_map"]["coverage_percent"], 0.0)
        self.assertEqual(package["release_assessment"]["status"], "NOT READY")
        self.assertFalse(package["controls"]["tests_executed"])

    def test_api_generates_report_without_execution_or_returning_code_files(self):
        request = FactoryCodePackageRequest(
            title="Secure analytics portal",
            description="Create a secure portal with audited API access and test coverage.",
            backend_language="python",
        )

        package = create_test_execution_simulation(request)

        self.assertEqual(package["status"], "SIMULATION_ONLY")
        self.assertFalse(any(package["controls"].values()))
        self.assertNotIn("files", package)
        self.assertEqual(package["unit_test_report"]["execution_status"], "NOT_EXECUTED")


if __name__ == "__main__":
    unittest.main()