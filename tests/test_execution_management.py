import inspect
import unittest
import uuid
from datetime import date
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.api import execution_management as em
from app.api.execution_management import (
    StoryTransition,
    burndown_series,
    has_path,
    router,
    sprint_health,
    transition_story,
)


class PureLogicTests(unittest.TestCase):
    def test_dependency_cycle_detection(self):
        a, b, c = "a", "b", "c"
        edges = {a: [b], b: [c]}
        self.assertTrue(has_path(edges, c, c))
        self.assertTrue(has_path(edges, a, c))
        self.assertFalse(has_path(edges, c, a))

    def test_burndown_ideal_and_actual(self):
        series = burndown_series(10, [(date(2025, 1, 2), 4)], date(2025, 1, 1), date(2025, 1, 5),
                                 today=date(2025, 1, 3))
        self.assertEqual(series[0]["ideal"], 10)
        self.assertEqual(series[-1]["ideal"], 0)
        self.assertEqual(series[0]["actual"], 10)
        self.assertEqual(series[1]["actual"], 6)
        self.assertEqual(series[2]["actual"], 6)
        self.assertIsNone(series[3]["actual"])

    def test_sprint_health_states(self):
        start, end = date(2025, 1, 1), date(2025, 1, 10)
        today = date(2025, 1, 6)
        self.assertEqual(sprint_health(10, 5, 40, 80, start, end, "Active", today)["health"], "OnTrack")
        self.assertEqual(sprint_health(10, 0, 40, 80, start, end, "Active", today)["health"], "Behind")
        self.assertEqual(sprint_health(10, 0, 100, 80, start, end, "Planned", today)["health"], "Overloaded")
        self.assertEqual(sprint_health(10, 10, 40, 80, start, end, "Completed", today)["health"], "Completed")
        self.assertEqual(sprint_health(10, 5, 40, 80, start, end, "Active", today)["capacity_utilization"], 50.0)

    def test_story_workflow_is_forward_only(self):
        self.assertNotIn("Planned", em.STORY_TRANSITIONS["Completed"])
        self.assertNotIn("Completed", em.STORY_TRANSITIONS["Backlog"])


class GovernanceTests(unittest.TestCase):
    def test_every_route_requires_management_roles(self):
        for route in router.routes:
            closures = [c.cell_contents for d in route.dependencies
                        for c in (d.dependency.__closure__ or ())]
            self.assertIn(("WORKFORCE_MANAGER", "PLATFORM_OWNER"), closures, route.path)

    def test_module_never_creates_assignments(self):
        source = inspect.getsource(em)
        self.assertNotIn("INSERT INTO dbo.ProjectTaskAssignment", source)
        self.assertNotIn("INSERT INTO dbo.ResourceAssignmentRecommendation", source)

    def test_start_work_requires_approved_assignment(self):
        story_id = uuid.uuid4()
        db = Mock()
        rows = iter([
            {"ProjectID": uuid.uuid4()},
            {"Status": "Planned", "SprintID": uuid.uuid4()},
            {"n": 0},
            {"n": 0},
        ])
        db.execute.return_value.mappings.return_value.first.side_effect = lambda: next(rows)
        with patch.object(em, "_require_visible_project"):
            with self.assertRaises(HTTPException) as ctx:
                transition_story(story_id, StoryTransition(status="InProgress"), db,
                                 {"sub": str(uuid.uuid4()), "role": "WORKFORCE_MANAGER"})
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("manager-approved", ctx.exception.detail)
        db.commit.assert_not_called()

    def test_invalid_transition_rejected(self):
        db = Mock()
        rows = iter([{"ProjectID": uuid.uuid4()}, {"Status": "Backlog", "SprintID": None}])
        db.execute.return_value.mappings.return_value.first.side_effect = lambda: next(rows)
        with patch.object(em, "_require_visible_project"):
            with self.assertRaises(HTTPException) as ctx:
                transition_story(uuid.uuid4(), StoryTransition(status="Completed"), db,
                                 {"sub": str(uuid.uuid4())})
        self.assertEqual(ctx.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
