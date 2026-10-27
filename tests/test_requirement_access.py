import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import HTTPException

from app.api.requirements import _planning_summary, can_access_requirement, track_requirement
from app.services.workforce_planner import TASK_PLAN, WorkforcePlanner, agent_meets_profile


class RequirementAccessTests(unittest.TestCase):
    def setUp(self):
        self.user_id = uuid.uuid4()
        self.report_id = uuid.uuid4()
        self.other_id = uuid.uuid4()

    @staticmethod
    def make_user(user_id, role):
        return {"sub": str(user_id), "role": role}

    @staticmethod
    def make_requirement(created_by):
        return SimpleNamespace(CreatedBy=str(created_by))

    def test_user_can_access_only_own_requirement(self):
        user = self.make_user(self.user_id, "USER")
        db = Mock()

        self.assertTrue(can_access_requirement(self.make_requirement(self.user_id), user, db))
        self.assertFalse(can_access_requirement(self.make_requirement(self.other_id), user, db))
        db.execute.assert_not_called()

    def test_workforce_manager_scope_does_not_depend_on_org_mappings(self):
        user = self.make_user(self.user_id, "WORKFORCE_MANAGER")
        db = Mock()

        self.assertTrue(can_access_requirement(self.make_requirement(self.user_id), user, db))
        self.assertTrue(can_access_requirement(self.make_requirement(self.report_id), user, db))
        self.assertTrue(can_access_requirement(self.make_requirement(self.other_id), user, db))
        db.execute.assert_not_called()

    def test_company_roles_have_global_request_read_scope(self):
        db = Mock()
        requirement = self.make_requirement(self.other_id)

        for role in ("ADMIN", "OWNER", "SUPER_ADMIN"):
            with self.subTest(role=role):
                self.assertTrue(can_access_requirement(requirement, self.make_user(self.user_id, role), db))

        db.execute.assert_not_called()

    def test_tracker_returns_not_found_for_an_unrelated_user(self):
        requirement_id = uuid.uuid4()
        db = Mock()
        db.get.return_value = self.make_requirement(self.other_id)
        user = self.make_user(self.user_id, "USER")

        with self.assertRaises(HTTPException) as raised:
            track_requirement(requirement_id, db, user)

        self.assertEqual(raised.exception.status_code, 404)
        db.execute.assert_not_called()

    def test_planned_project_reports_effort_and_staffing_gap_without_fake_dates(self):
        summary = _planning_summary(
            [
                {"skill": "RequirementAnalysis", "estimated_effort_hours": 32, "qualified_active_agents": 0},
                {"skill": "ProjectPlanning", "estimated_effort_hours": 24, "qualified_active_agents": 0},
                {"skill": "SecurityReview", "estimated_effort_hours": 24, "qualified_active_agents": 0},
            ],
            [{"status": "Planned", "task_count": 7, "assigned_task_count": 0, "unestimated_task_count": 4, "open_workforce_request_count": 6}],
        )

        self.assertEqual(summary["delivery_state"], "planned_unstaffed")
        self.assertEqual(summary["estimated_skill_hours"], 80)
        self.assertEqual(summary["indicative_person_days_at_8h"], 10)
        self.assertEqual(summary["skills_with_active_agent_coverage"], 0)
        self.assertEqual(summary["task_count"], 7)
        self.assertEqual(summary["assigned_task_count"], 0)
        self.assertEqual(summary["unestimated_task_count"], 4)
        self.assertEqual(summary["open_workforce_request_count"], 6)
        self.assertIsNone(summary["calendar_estimate_days"])

    def test_workforce_agent_must_meet_every_profile_skill_threshold(self):
        profile = {
            "RequiredSkillsJson": '[{"name":"ProjectPlanning","minimum_proficiency":4},'
            '{"name":"DeliveryManagement","minimum_proficiency":4}]'
        }

        self.assertTrue(agent_meets_profile(profile, {"ProjectPlanning": 5, "DeliveryManagement": 4}))
        self.assertFalse(agent_meets_profile(profile, {"ProjectPlanning": 5, "DeliveryManagement": 3}))
        self.assertFalse(agent_meets_profile(profile, {"ProjectPlanning": 5}))

    def test_delivery_plan_has_governed_role_assignments(self):
        role_by_task = {task[0]: task[1] for task in TASK_PLAN}

        self.assertEqual(role_by_task["Solution design"], "DELIVERY_LEAD")
        self.assertEqual(role_by_task["Training and handover"], "HR_WORKFORCE_COORDINATOR")
        self.assertEqual(role_by_task["Implementation"], "SOFTWARE_DEVELOPER")
        self.assertEqual(role_by_task["Verification and testing"], "QA_ENGINEER")
        self.assertEqual(role_by_task["Deployment readiness"], "SECURITY_ENGINEER")

    def test_provisioned_agent_cannot_activate_until_configured_and_evaluated(self):
        agent = {"Status": "Provisioning", "ModelProvider": "UNCONFIGURED", "Model": "UNCONFIGURED", "ModelVersion": "UNCONFIGURED"}

        blockers = WorkforcePlanner.agent_activation_blockers(agent, set())

        self.assertEqual(len(blockers), 4)
        self.assertIn("approved provider is not configured", blockers)
        self.assertIn("approved model is not configured", blockers)
        self.assertIn("model version is not configured", blockers)
        self.assertIn("passed evaluations missing: Capability, Governance, Safety, Security", blockers)

    def test_activation_requires_both_independent_evaluations(self):
        agent = {"Status": "Provisioning", "ModelProvider": "approved", "Model": "model-x", "ModelVersion": "v1"}

        self.assertEqual(WorkforcePlanner.agent_activation_blockers(agent, {"Capability", "Safety", "Governance"}), [
            "passed evaluations missing: Security"
        ])
        self.assertEqual(WorkforcePlanner.agent_activation_blockers(agent, {"Capability", "Safety", "Security"}), [
            "passed evaluations missing: Governance"
        ])
        self.assertEqual(WorkforcePlanner.agent_activation_blockers(agent, {"Capability", "Safety", "Security", "Governance"}), [])


if __name__ == "__main__":
    unittest.main()