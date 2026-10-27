import unittest
import uuid
from unittest.mock import Mock

from app.api.dashboard import _owned_dashboard_records, dashboard, my_dashboard


class DashboardScopeTests(unittest.TestCase):
    def test_personal_dashboard_consumes_each_result_before_next_query(self):
        class Result:
            def __init__(self, db):
                self.db = db

            def mappings(self):
                return self

            def all(self):
                self.db.cursor_open = False
                return []

            def scalar_one(self):
                self.db.cursor_open = False
                return 0

        class CursorBoundDatabase:
            cursor_open = False

            def execute(self, *_args, **_kwargs):
                if self.cursor_open:
                    raise RuntimeError("Connection is busy with results for another command")
                self.cursor_open = True
                return Result(self)

        records = _owned_dashboard_records(CursorBoundDatabase(), uuid.uuid4())

        self.assertEqual(records["my_requirements"], [])
        self.assertEqual(records["my_projects"], [])
        self.assertEqual(records["my_tasks"], [])
        self.assertEqual(records["my_notifications"], [])
        self.assertEqual(records["my_approvals"], [])
        self.assertEqual(records["my_assessments"], 0)

    def test_company_dashboard_includes_visible_notifications_matching_count(self):
        notifications = [
            {"NotificationID": uuid.uuid4(), "IsRead": False},
            {"NotificationID": uuid.uuid4(), "IsRead": True},
        ]
        user = {"sub": str(uuid.uuid4()), "role": "PLATFORM_OWNER"}
        db = Mock()

        with unittest.mock.patch("app.api.dashboard.SecurityService") as security_service:
            service = security_service.return_value
            service.GetVisibleSummary.return_value = {
                "requirements": 1, "projects": 0, "tasks": 0,
                "approvals": 0, "notifications": len(notifications), "assessments": 0,
            }
            service.GetVisibleNotifications.return_value = notifications

            result = dashboard(db, user)

        self.assertEqual(result["notifications"], len(result["my_notifications"]))
        self.assertEqual(result["my_notifications"], notifications)

    def test_personal_dashboard_uses_owner_filtered_join_paths(self):
        user_id = uuid.uuid4()
        db = Mock()
        db.execute.side_effect = [
            self.rows([]),
            self.rows([]),
            self.rows([]),
            self.rows([]),
            self.rows([]),
            self.scalar(0),
        ]

        result = _owned_dashboard_records(db, user_id)

        self.assertEqual(result["my_requirements"], [])
        self.assertEqual(result["my_projects"], [])
        self.assertEqual(result["my_tasks"], [])
        self.assertEqual(result["my_notifications"], [])
        self.assertEqual(result["my_approvals"], [])
        self.assertEqual(result["my_assessments"], 0)
        self.assertEqual(db.execute.call_count, 6)
        statements = [str(call.args[0]) for call in db.execute.call_args_list]
        params = [call.args[1] for call in db.execute.call_args_list]
        self.assertIn("WHERE CreatedByUserID=:owner_id", statements[0])
        self.assertIn("JOIN Requirement r ON r.RequirementID=p.RequirementID", statements[1])
        self.assertIn("WHERE p.CreatedByUserID=:owner_id AND r.CreatedByUserID=:owner_id", statements[1])
        self.assertIn("JOIN Requirement r ON r.RequirementID=p.RequirementID", statements[2])
        self.assertIn("WHERE t.CreatedByUserID=:owner_id AND p.CreatedByUserID=:owner_id AND r.CreatedByUserID=:owner_id", statements[2])
        self.assertIn("WHERE UserID=:user_id", statements[3])
        self.assertIn("a.AssignedToUserID=:user_id OR r.CreatedByUserID=:owner_id", statements[4])
        self.assertTrue(all(item["owner_id"] == str(user_id) for item in params if "owner_id" in item))
        self.assertTrue(all(item["user_id"] == user_id for item in params if "user_id" in item))

    def test_personal_dashboard_response_has_requested_collections_and_counts(self):
        user_id = uuid.uuid4()
        records = {
            "my_requirements": [{"RequirementID": uuid.uuid4()}],
            "my_projects": [{"ProjectID": uuid.uuid4()}],
            "my_tasks": [{"TaskID": uuid.uuid4()}],
            "my_notifications": [{"NotificationID": uuid.uuid4()}],
            "my_approvals": [{"ApprovalID": uuid.uuid4()}],
            "my_assessments": 2,
        }
        db = Mock()
        with unittest.mock.patch("app.api.dashboard._owned_dashboard_records", return_value=records):
            result = my_dashboard(db, {"sub": str(user_id), "role": "USER"})

        self.assertEqual(result["visibility_scope"], "personal")
        for collection in ("my_requirements", "my_projects", "my_tasks", "my_notifications", "my_approvals"):
            self.assertEqual(len(result[collection]), 1)
        self.assertEqual((result["requirements"], result["projects"], result["tasks"], result["notifications"], result["approvals"], result["assessments"]), (1, 1, 1, 1, 1, 2))

    @staticmethod
    def rows(items):
        result = Mock()
        result.mappings.return_value.all.return_value = items
        return result

    @staticmethod
    def scalar(value):
        result = Mock()
        result.scalar_one.return_value = value
        return result


if __name__ == "__main__":
    unittest.main()
