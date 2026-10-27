import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.services.project_factory import ProjectFactory


class ProjectFactoryOwnershipTests(unittest.TestCase):
    def test_legacy_guid_owner_is_propagated_when_app_user_exists(self):
        owner_id = uuid.uuid4()
        requirement = SimpleNamespace(CreatedBy=str(owner_id), CreatedByUserID=None)
        db = Mock()
        db.execute.return_value.scalar_one_or_none.return_value = owner_id

        resolved = ProjectFactory._created_by_user_id(db, requirement)

        self.assertEqual(resolved, owner_id)
        self.assertEqual(requirement.CreatedByUserID, owner_id)

    def test_missing_or_unmatched_owner_fails_closed(self):
        for legacy_owner, existing_user in (("unknown-user", None), (str(uuid.uuid4()), None)):
            with self.subTest(legacy_owner=legacy_owner):
                requirement = SimpleNamespace(CreatedBy=legacy_owner, CreatedByUserID=None)
                db = Mock()
                db.execute.return_value.scalar_one_or_none.return_value = existing_user

                with self.assertRaises(HTTPException) as raised:
                    ProjectFactory._created_by_user_id(db, requirement)

                self.assertEqual(raised.exception.status_code, 409)
                self.assertIsNone(requirement.CreatedByUserID)

    def test_existing_normalized_owner_is_still_validated_against_app_user(self):
        owner_id = uuid.uuid4()
        requirement = SimpleNamespace(CreatedBy=str(owner_id), CreatedByUserID=owner_id)
        db = Mock()
        db.execute.return_value.scalar_one_or_none.return_value = None

        with self.assertRaises(HTTPException) as raised:
            ProjectFactory._created_by_user_id(db, requirement)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("does not match an AppUser", raised.exception.detail)

    def test_task_decomposition_binds_owner_id_on_every_task_insert(self):
        owner_id = uuid.uuid4()
        requirement = SimpleNamespace(
            CreatedBy=str(owner_id),
            CreatedByUserID=owner_id,
            Priority="High",
            RiskLevel="Medium",
        )
        owner_result = Mock()
        owner_result.scalar_one_or_none.return_value = owner_id
        count_result = Mock()
        count_result.scalar_one.return_value = 0
        db = Mock()
        db.execute.side_effect = [owner_result, count_result] + [Mock() for _ in range(7)]

        ProjectFactory().generate_tasks(db, uuid.uuid4(), requirement)

        task_insert_calls = db.execute.call_args_list[2:]
        self.assertEqual(len(task_insert_calls), 7)
        for call in task_insert_calls:
            self.assertEqual(call.args[1]["created_by_user_id"], owner_id)

    def test_project_creation_binds_owner_to_project_and_all_tasks(self):
        owner_id = uuid.uuid4()
        requirement_id = uuid.uuid4()
        requirement = SimpleNamespace(
            RequirementID=requirement_id,
            CreatedBy=str(owner_id),
            CreatedByUserID=owner_id,
            RequestedBy="Test User",
            Title="Ownership test project",
            Description="Project owner should propagate into all generated work.",
            Priority="High",
            RiskLevel="Medium",
        )
        user_result = Mock()
        user_result.scalar_one_or_none.return_value = owner_id
        no_project_result = Mock()
        no_project_result.scalar_one_or_none.return_value = None
        no_tasks_result = Mock()
        no_tasks_result.scalar_one.return_value = 0
        db = Mock()
        db.execute.side_effect = [user_result, no_project_result, Mock(), user_result, no_tasks_result]
        db.execute.side_effect = list(db.execute.side_effect) + [Mock() for _ in range(7)]

        with patch("app.services.project_factory.WorkforcePlanner") as planner, patch(
            "app.services.agent_runtime.queue_pending_tasks", return_value={"queued_count": 0}
        ):
            project_id = ProjectFactory().create_project(db, requirement)

        self.assertIsInstance(project_id, uuid.UUID)
        project_insert = db.execute.call_args_list[2]
        self.assertEqual(project_insert.args[1]["created_by_user_id"], owner_id)
        task_inserts = db.execute.call_args_list[5:]
        self.assertEqual(len(task_inserts), 7)
        self.assertTrue(all(call.args[1]["created_by_user_id"] == owner_id for call in task_inserts))
        planner.return_value.auto_assign_agents.assert_called_once()


if __name__ == "__main__":
    unittest.main()