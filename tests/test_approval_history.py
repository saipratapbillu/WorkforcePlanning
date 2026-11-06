import unittest
import uuid
from datetime import datetime
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.api.approvals import approval_history


class ApprovalHistoryTests(unittest.TestCase):
    def test_history_requires_visible_approval_before_audit_query(self):
        database = Mock()
        approval_id = uuid.uuid4()
        with patch("app.api.approvals.SecurityService") as security_service:
            security_service.return_value.GetVisibleApprovals.return_value = []
            with self.assertRaises(HTTPException) as raised:
                approval_history(approval_id, database, {"sub": str(uuid.uuid4()), "role": "BUSINESS_USER"})

        self.assertEqual(raised.exception.status_code, 404)
        database.execute.assert_not_called()

    def test_history_returns_bounded_metadata_without_details(self):
        approval_id = uuid.uuid4()
        event_time = datetime(2026, 11, 6, 12, 0)
        row = {
            "CorrelationID": uuid.uuid4(),
            "ActorType": "User",
            "ActorID": str(uuid.uuid4()),
            "Action": "ApprovalApprove",
            "Outcome": "Success",
            "CreatedAtUtc": event_time,
            "Details": '{"reason_recorded":true}',
        }
        database = Mock()
        database.execute.return_value.mappings.return_value.all.return_value = [row]
        user = {"sub": str(uuid.uuid4()), "role": "PLATFORM_OWNER"}
        with patch("app.api.approvals.SecurityService") as security_service:
            security_service.return_value.GetVisibleApprovals.return_value = [{"ApprovalID": approval_id}]
            history = approval_history(approval_id, database, user)

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["action"], "ApprovalApprove")
        self.assertEqual(history[0]["created_at_utc"], event_time)
        self.assertNotIn("details", history[0])
        statement = str(database.execute.call_args.args[0])
        self.assertIn("TOP (50)", statement)
        self.assertIn("ResourceType='Approval'", statement)
        self.assertEqual(database.execute.call_args.args[1], {"approval_id": str(approval_id)})


if __name__ == "__main__":
    unittest.main()
