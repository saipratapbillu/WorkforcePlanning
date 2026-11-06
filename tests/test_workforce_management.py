import unittest
import uuid
from unittest.mock import Mock

from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.api.workforce_management import (
    BacklogPlan,
    PlannedEpic,
    PlannedFeature,
    PlannedSprint,
    PlannedStory,
    PlannedTask,
    RecommendationDecision,
    decide_recommendation,
    router,
    score_candidate,
)


class WorkforceManagementTests(unittest.TestCase):
    def test_candidate_requires_active_skills_certification_availability_and_capacity(self):
        result = score_candidate(
            [{"name": "Arabic", "minimum_proficiency": 4}],
            ["Azure Fundamentals"],
            [{"Name": "Arabic", "Proficiency": 5, "Status": "Pending"}],
            [],
            True,
            12,
            2,
            8,
        )

        self.assertFalse(result["eligible_for_approval"])
        self.assertEqual(result["missing_skills"], ["Arabic"])
        self.assertEqual(result["missing_certifications"], ["Azure Fundamentals"])
        self.assertEqual(result["remaining_hours"], 10)

    def test_complete_candidate_is_recommendable_but_not_automatically_assigned(self):
        result = score_candidate(
            [{"name": "Arabic", "minimum_proficiency": 4}],
            ["Azure Fundamentals"],
            [{"Name": "Arabic", "Proficiency": 5, "Status": "Active"}],
            ["Azure Fundamentals"],
            True,
            12,
            2,
            8,
        )

        self.assertTrue(result["eligible_for_approval"])
        self.assertEqual(result["match_score"], 100)

    def test_only_assigned_manager_can_approve_recommendation(self):
        manager_id = uuid.uuid4()
        recommendation_id = uuid.uuid4()
        db = Mock()
        db.execute.return_value.mappings.return_value.first.return_value = {
            "RecommendationID": recommendation_id,
            "ProjectTaskID": uuid.uuid4(),
            "UserID": uuid.uuid4(),
            "Status": "PendingApproval",
            "ManagerUserID": manager_id,
        }

        with self.assertRaises(HTTPException) as raised:
            decide_recommendation(
                recommendation_id,
                RecommendationDecision(action="approve", reason="Approve this assignment"),
                db=db,
                actor={"sub": str(uuid.uuid4()), "role": "PLATFORM_OWNER"},
            )

        self.assertEqual(raised.exception.status_code, 403)
        db.commit.assert_not_called()
        self.assertEqual(db.execute.call_count, 1)

    def test_recommendation_without_manager_remains_blocked(self):
        recommendation_id = uuid.uuid4()
        db = Mock()
        db.execute.return_value.mappings.return_value.first.return_value = {
            "RecommendationID": recommendation_id,
            "ProjectTaskID": uuid.uuid4(),
            "UserID": uuid.uuid4(),
            "Status": "PendingApproval",
            "ManagerUserID": None,
        }

        with self.assertRaises(HTTPException) as raised:
            decide_recommendation(
                recommendation_id,
                RecommendationDecision(action="approve", reason="Approve this assignment"),
                db=db,
                actor={"sub": str(uuid.uuid4()), "role": "WORKFORCE_MANAGER"},
            )

        self.assertEqual(raised.exception.status_code, 409)
        db.commit.assert_not_called()

    def test_assignment_is_created_only_after_the_assigned_manager_approves(self):
        manager_id = uuid.uuid4()
        task_id = uuid.uuid4()
        user_id = uuid.uuid4()
        recommendation_id = uuid.uuid4()
        first_result = Mock()
        first_result.mappings.return_value.first.return_value = {
            "RecommendationID": recommendation_id,
            "ProjectTaskID": task_id,
            "UserID": user_id,
            "Status": "PendingApproval",
            "ManagerUserID": manager_id,
            "TaskStatus": "Planned",
        }
        active_assignment_result = Mock()
        active_assignment_result.scalar_one_or_none.return_value = None
        db = Mock()
        db.execute.side_effect = [first_result, active_assignment_result, Mock(), Mock(), Mock()]

        result = decide_recommendation(
            recommendation_id,
            RecommendationDecision(action="approve", reason="Approve this assignment"),
            db=db,
            actor={"sub": str(manager_id), "role": "WORKFORCE_MANAGER"},
        )

        self.assertEqual(result["status"], "Assigned")
        self.assertTrue(result["assignment_created"])
        assignment_statement = str(db.execute.call_args_list[3].args[0])
        self.assertIn("INSERT dbo.ProjectTaskAssignment", assignment_statement)
        self.assertEqual(db.execute.call_args_list[3].args[1]["actor_id"], manager_id)
        db.commit.assert_called_once()

    def test_backlog_rejects_story_effort_above_sprint_capacity(self):
        with self.assertRaises(ValueError):
            BacklogPlan(
                sprints=[PlannedSprint(
                    name="Sprint 1",
                    start_date="2026-07-06",
                    end_date="2026-07-17",
                    capacity_hours=5,
                )],
                epics=[PlannedEpic(
                    title="Offers",
                    description="Offer intelligence",
                    features=[PlannedFeature(
                        title="Search",
                        description="Search offers",
                        stories=[PlannedStory(
                            title="Find offers",
                            description="Search active retailer offers",
                            acceptance_criteria=["Returns current offers"],
                            story_points=3,
                            sprint_name="Sprint 1",
                            tasks=[PlannedTask(
                                title="Build search",
                                description="Create search endpoint",
                                estimated_effort_hours=8,
                            )],
                        )],
                    )],
                )],
            )

    def test_all_workforce_management_routes_require_management_role(self):
        routes = [route for route in router.routes if isinstance(route, APIRoute)]

        self.assertGreaterEqual(len(routes), 10)
        for route in routes:
            self.assertTrue(route.dependencies, route.path)
            closure_values = [
                cell.cell_contents
                for cell in (route.dependencies[0].dependency.__closure__ or ())
            ]
            self.assertIn(("WORKFORCE_MANAGER", "PLATFORM_OWNER"), closure_values)


if __name__ == "__main__":
    unittest.main()
