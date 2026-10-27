import unittest
from pydantic import ValidationError

from app.services.agent_factory import build_factory_blueprint
from app.services.assignment_factory import build_assignment_package
from app.api.workforce import AssignmentPlanRequest, create_agent_assignment_plan


class AssignmentFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = build_factory_blueprint(
            title="Secure analytics portal",
            description="Create a secure Angular portal and Python API with analytics, audit, testing, and cloud release.",
            technology_changes=["Angular", "Python", "Azure AI"],
        )

    def test_no_roster_is_unverified_and_does_not_invent_candidates(self):
        package = build_assignment_package(self.blueprint)

        self.assertEqual(package["assignment_readiness"]["status"], "NOT_READY")
        self.assertIsNone(package["assignment_readiness"]["readiness_score_percent"])
        self.assertEqual(package["assignment_readiness"]["verified_readiness_status"], "UNVERIFIED")
        self.assertIsNone(package["assignment_readiness"]["verified_readiness_score_percent"])
        self.assertTrue(package["capacity_plan"]["roles"])
        self.assertTrue(all(item["available_capacity_hours"] is None
                            for item in package["capacity_plan"]["roles"]))
        self.assertTrue(all(item["recommendations"] == [] for item in package["assignment_blueprint"]["work_items"]))
        self.assertFalse(any(package["controls"].values()))

    def test_verified_candidate_evidence_produces_scores_but_never_assigns(self):
        lifecycle = self.blueprint["agent_lifecycle_package"]
        architect = next(profile for profile in lifecycle["agent_profiles"]
                         if profile["agent_name"] == "AI Solution Architect")
        candidates = [{
            "candidate_id": "candidate-architect-1", "display_name": "Architect Candidate",
            "agent_role": "AI Solution Architect",
            "skills": {skill["skill"]: skill["required_level"] for skill in architect["skill_matrix"]},
            "certifications_current": architect["certification_path"]["required_evaluations"],
            "available": True, "available_capacity_hours": 32, "reserved_capacity_hours": 8,
            "project_fit_tags": ["portal", "analytics"], "technology_experience": ["Angular", "Python"],
            "performance_score": 88, "performance_evidence_reference": "review-ref-2026-01",
        }]

        package = build_assignment_package(self.blueprint, candidates)
        architect_item = next(item for item in package["assignment_blueprint"]["work_items"]
                              if item["role_discipline"] == "Architect")

        self.assertTrue(architect_item["recommendations"])
        candidate = architect_item["recommendations"][0]
        self.assertEqual(candidate["candidate_id"], "candidate-architect-1")
        self.assertIsInstance(candidate["match_score"], (int, float))
        self.assertEqual(candidate["assignment_status"], "NOT_ASSIGNED")
        self.assertFalse(candidate["score_components"]["performance_evidence_verified"])
        self.assertEqual(candidate["score_status"], "PROVISIONAL_CALLER_SUPPLIED_EVIDENCE")
        self.assertFalse(package["execution_readiness_report"]["can_project_be_staffed"])
        self.assertTrue(package["assignment_package"]["resource_plan"])
        self.assertFalse(package["controls"]["assignments_created"])

    def test_missing_certification_and_capacity_are_readiness_blockers(self):
        candidates = [{
            "candidate_id": "candidate-dev-1", "display_name": "Developer Candidate",
            "agent_role": "AI Backend Developer", "skills": {"BackendDevelopment": 5},
            "certifications_current": ["Capability"], "available": True,
            "available_capacity_hours": 0, "reserved_capacity_hours": 40,
            "project_fit_tags": [], "technology_experience": [],
        }]

        package = build_assignment_package(self.blueprint, candidates)

        developer_item = next(item for item in package["assignment_blueprint"]["work_items"]
                              if item["role_discipline"] == "Developer")
        result = developer_item["recommendations"][0]
        self.assertIn("certification", " ".join(result["blockers"]).lower())
        self.assertIn("capacity", " ".join(result["blockers"]).lower())
        self.assertNotEqual(developer_item["readiness"], "READY")
        self.assertFalse(result["assignment_performed"])

    def test_unknown_performance_evidence_is_not_scored_as_zero(self):
        package = build_assignment_package(self.blueprint, [{
            "candidate_id": "candidate-qa-1", "agent_role": "AI QA Engineer",
            "skills": {}, "certifications_current": [], "available": None,
            "available_capacity_hours": None, "reserved_capacity_hours": None,
            "performance_score": 99,
        }])
        qa_item = next(item for item in package["assignment_blueprint"]["work_items"]
                       if item["role_discipline"] == "QA")
        result = qa_item["recommendations"][0]
        self.assertIsNone(result["score_components"]["performance"])
        self.assertIn("performance", result["unverified_dimensions"])
        self.assertEqual(result["assignment_status"], "NOT_ASSIGNED")

    def test_assignment_api_returns_recommendations_only(self):
        request = AssignmentPlanRequest(
            title="Secure analytics portal",
            description="Create a secure portal with audited API access.",
            candidate_evidence=[{
                "candidate_id": "candidate-1", "agent_role": "AI Backend Developer",
                "skills": {"BackendDevelopment": 5}, "certifications_current": ["Capability"],
                "available": True, "available_capacity_hours": 20, "reserved_capacity_hours": 0,
            }],
        )

        package = create_agent_assignment_plan(request)

        self.assertEqual(package["authority"], "NONE")
        self.assertFalse(any(package["controls"].values()))
        self.assertFalse(package["execution_readiness_report"]["can_project_be_staffed"])
        self.assertTrue(all(candidate["assignment_status"] == "NOT_ASSIGNED"
                            for candidate in package["match_results"]))

    def test_assignment_api_without_candidates_keeps_dashboard_unverified(self):
        request = AssignmentPlanRequest(
            title="Secure analytics portal",
            description="Create a secure portal with audited API access.",
        )

        package = create_agent_assignment_plan(request)

        dashboard = package["workforce_director_dashboard"]
        self.assertEqual(dashboard["assignment_readiness"]["status"], "NOT_READY")
        self.assertEqual(dashboard["coverage"]["status"], "UNVERIFIED")
        self.assertEqual(dashboard["replacement_readiness"], "UNAVAILABLE_NO_CANDIDATE_EVIDENCE")
        self.assertFalse(package["execution_readiness_report"]["can_project_be_staffed"])

    def test_candidate_payload_has_bounded_evidence(self):
        with self.assertRaises(ValidationError):
            AssignmentPlanRequest(
                title="Bounded plan", description="This description has enough characters.",
                candidate_evidence=[{
                    "candidate_id": "candidate-1", "agent_role": "AI QA Engineer",
                    "skills": {"x" * 101: 4},
                }],
            )


if __name__ == "__main__":
    unittest.main()