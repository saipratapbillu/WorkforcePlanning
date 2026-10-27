import unittest
import uuid
from unittest.mock import Mock, patch

from app.api.workforce import (
    FactoryCandidatePreviewRequest,
    workforce_assignment_preview,
    workforce_factory_dashboard,
    workforce_replacement_preview,
)
from app.services.agent_factory import build_factory_blueprint, rank_assignment_candidates


class AgentFactoryTests(unittest.TestCase):
    def test_blueprint_generates_governed_role_artifacts_without_lifecycle_actions(self):
        blueprint = build_factory_blueprint(
            title="Modernize analytics portal",
            description="Build a secure Angular frontend and .NET API with Azure AI insights.",
            technology_changes=["Angular", ".NET", "Azure AI"],
        )

        self.assertIn("AI Frontend Developer", {role["role_name"] for role in blueprint["roles"]})
        self.assertIn("AI Backend Developer", {role["role_name"] for role in blueprint["roles"]})
        self.assertTrue(all(role["job_description"]["purpose"] for role in blueprint["roles"]))
        self.assertEqual({"Bronze", "Silver", "Gold", "Platinum"},
                         set(blueprint["certification_framework"]["tiers"]))
        self.assertEqual("BLUEPRINT_ONLY", blueprint["lifecycle_actions"]["mode"])
        self.assertFalse(blueprint["lifecycle_actions"]["agent_records_created"])
        self.assertFalse(blueprint["lifecycle_actions"]["agents_assigned"])
        self.assertFalse(blueprint["lifecycle_actions"]["agents_activated"])

    def test_requirement_blueprint_contains_complete_planning_only_sdlc_package(self):
        inputs = dict(
            title="Secure analytics portal",
            description="Build a customer web portal, API, and analytics database with login, audit, testing, and cloud hosting.",
            technology_changes=["Angular", ".NET", "Azure AI"],
            priority="Critical",
        )
        blueprint = build_factory_blueprint(**inputs)
        replay = build_factory_blueprint(**inputs)

        package = blueprint["technical_delivery_package"]
        expected = {
            "executive_assessment", "architecture_blueprint", "database_blueprint",
            "api_catalog", "ui_blueprint", "security_blueprint", "testing_blueprint",
            "deployment_blueprint", "workforce_plan",
        }
        self.assertEqual(set(package["artifacts"]), expected)
        self.assertTrue(all(package["artifacts"][name] for name in expected))
        self.assertEqual(package["workflow"][0], "Requirement")
        self.assertEqual(package["workflow"][-1], "Deployment Design")
        self.assertEqual(package["status"], "PLANNING_ONLY")
        self.assertFalse(package["controls"]["code_generated"])
        self.assertFalse(package["controls"]["infrastructure_created"])
        self.assertFalse(package["controls"]["deployed"])
        self.assertFalse(package["controls"]["runtime_started"])
        self.assertIn("Authentication", package["artifacts"]["security_blueprint"]["authentication_design"])
        self.assertEqual(package["artifacts"]["executive_assessment"]["priority"], "Critical")
        self.assertEqual(package["artifacts"]["executive_assessment"]["priority_basis"], "Requester-selected priority")
        self.assertTrue(package["artifacts"]["architecture_blueprint"]["backend_design"]["service_boundaries"])
        self.assertEqual(package, replay["technical_delivery_package"])
        self.assertTrue(package["artifacts"]["database_blueprint"]["assumptions"])
        self.assertEqual(package["artifacts"]["deployment_blueprint"]["deployment_status"],
                 "DESIGN_ONLY_NO_INFRASTRUCTURE_CREATED")
        self.assertTrue(package["artifacts"]["ui_blueprint"]["forms"])
        self.assertTrue(package["artifacts"]["ui_blueprint"]["dashboards"])
        disciplines = {item["discipline"] for item in package["artifacts"]["workforce_plan"]["role_alignment"]}
        self.assertTrue({"Architect", "Developers", "QA", "Security", "DevOps"}.issubset(disciplines))
        self.assertIn("project_delivery_package", blueprint)
        self.assertIn("delivery_execution_package", blueprint)
        self.assertEqual(blueprint["delivery_execution_package"]["status"], "PLANNING_AND_SIMULATION_ONLY")
        self.assertFalse(any(blueprint["delivery_execution_package"]["controls"].values()))
        self.assertIn("assignment_recommendation_package", blueprint)
        self.assertEqual(blueprint["assignment_recommendation_package"]["authority"], "NONE")
        self.assertIsNone(blueprint["assignment_recommendation_package"]["assignment_readiness"]["readiness_score_percent"])
        self.assertIn("testing_execution_package", blueprint)
        self.assertEqual(blueprint["testing_execution_package"]["status"], "SIMULATION_ONLY")
        self.assertIsNone(blueprint["testing_execution_package"]["unit_test_report"]["observed_pass_rate_percent"])
        self.assertFalse(any(blueprint["testing_execution_package"]["controls"].values()))
        self.assertIn("build_execution_package", blueprint)
        self.assertEqual(blueprint["build_execution_package"]["status"], "PLANNING_AND_SIMULATION_ONLY")
        self.assertEqual(blueprint["build_execution_package"]["compilation_assessment"]["execution_status"], "NOT_COMPILED")
        self.assertFalse(any(blueprint["build_execution_package"]["controls"].values()))
        self.assertIn("hosting_execution_package", blueprint)
        self.assertEqual(blueprint["hosting_execution_package"]["status"], "PLANNING_AND_SIMULATION_ONLY")
        self.assertEqual(blueprint["hosting_execution_package"]["authority"], "NONE")
        self.assertFalse(any(blueprint["hosting_execution_package"]["controls"].values()))

    def test_domain_and_role_rules_do_not_match_incidental_substrings(self):
        blueprint = build_factory_blueprint(
            title="Improve throughput monitoring",
            description="Measure throughput and latency across operational workloads.",
        )

        package = blueprint["technical_delivery_package"]["artifacts"]
        self.assertEqual(package["executive_assessment"]["business_domain"], "General Business")
        self.assertNotIn("AI Data Analyst", {role["role_name"] for role in blueprint["roles"]})
        self.assertNotIn("AI Backend Developer", {role["role_name"] for role in blueprint["roles"]})

    def test_assignment_ranking_requires_all_governed_gates(self):
        candidates = [
            {"agent_id": "ready", "skills": {"Python": 4}, "certifications": ["Capability", "Safety", "Security", "Governance"],
             "available": True, "capacity_percent": 20, "completed_projects": 3, "performance_score": 95},
            {"agent_id": "uncertified", "skills": {"Python": 5}, "certifications": ["Capability"],
             "available": True, "capacity_percent": 10, "completed_projects": 5, "performance_score": 99},
        ]

        ranked = rank_assignment_candidates(candidates, {"Python": 4})

        self.assertEqual(ranked[0]["agent_id"], "ready")
        self.assertTrue(ranked[0]["eligible_for_authorized_assignment"])
        self.assertFalse(ranked[1]["eligible_for_authorized_assignment"])
        self.assertIn("missing required certifications", ranked[1]["blockers"][0].lower())
        self.assertFalse(any(item["assignment_performed"] for item in ranked))

    def test_dashboard_readiness_uses_live_denominators_and_performs_no_writes(self):
        ready_agent = {
            "status": "Active", "skill_gaps": [], "certification_gaps": [],
            "model_provider": "Approved Provider", "model": "Approved Model", "model_version": "v1",
            "active_assignments": 1, "current_workload_percent": 40,
        }
        gap_agent = {
            "status": "Active", "skill_gaps": [{"skill": "Python"}],
            "certification_gaps": ["Security"], "model_provider": "UNCONFIGURED",
            "model": "UNCONFIGURED", "model_version": "UNCONFIGURED",
            "active_assignments": 0, "current_workload_percent": 60,
        }
        provisioning_agent = {**ready_agent, "status": "Provisioning", "active_assignments": 0}
        readiness = {
            "agents": [ready_agent, gap_agent, provisioning_agent], "available_agents": 1,
            "required_skills": [{"qualified_agent_count": 1}, {"qualified_agent_count": 0}],
            "skill_gaps": [{"skill": "No active coverage"}],
        }
        database = Mock()
        with patch("app.api.workforce.agent_readiness", return_value=readiness), \
             patch("app.api.workforce.agent_capacity", return_value={"agents": []}):
            report = workforce_factory_dashboard(database, {"sub": "workforce-manager"})

        self.assertEqual(report["total_agents"], 3)
        self.assertEqual(report["active_agents"], 2)
        self.assertEqual(report["certification_coverage_percent"], 50.0)
        self.assertEqual(report["skill_coverage_percent"], 50.0)
        self.assertEqual(report["capacity_utilization_percent"], 50.0)
        self.assertEqual(report["workforce_readiness_percent"], 33.3)
        self.assertFalse(report["lifecycle_mutations_enabled"])
        database.commit.assert_not_called()

    def test_assignment_and_replacement_previews_are_read_only(self):
        agent_id = uuid.uuid4()
        profile_result = Mock()
        profile_result.mappings.return_value.first.return_value = {
            "RoleCode": "BACKEND", "PositionName": "Backend Developer",
            "RequiredSkillsJson": '[{"name":"Python","minimum_proficiency":4}]',
        }
        history_result = Mock()
        history_result.mappings.return_value.all.return_value = []
        database = Mock()
        database.execute.side_effect = [profile_result, history_result, profile_result, history_result]
        live_agent = {
            "agent_id": str(agent_id), "name": "Qualified Agent", "status": "Active",
            "agent_type": "Specialist", "skills": [{"name": "Python", "proficiency": 4, "status": "Active"}],
            "certifications": {name: {"passed": True} for name in ("Capability", "Safety", "Security", "Governance")},
            "available_task_slots": 1, "current_workload_percent": 25,
        }

        with patch("app.api.workforce.agent_readiness", return_value={"agents": [live_agent]}):
            assignment = workforce_assignment_preview(
                FactoryCandidatePreviewRequest(role_code="BACKEND"), database, {"sub": "manager"})
            replacement = workforce_replacement_preview(
                FactoryCandidatePreviewRequest(role_code="BACKEND", exclude_agent_id=agent_id),
                database, {"sub": "manager"})

        self.assertTrue(assignment["recommendation_only"])
        self.assertTrue(assignment["recommendations"][0]["eligible_for_authorized_assignment"])
        self.assertFalse(assignment["assignment_performed"])
        self.assertEqual(replacement["preview_type"], "replacement")
        self.assertEqual(replacement["recommendations"], [])
        database.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()