import unittest
import uuid
from unittest.mock import Mock

from app.api import requirements


class RequirementTimelineAuditTests(unittest.TestCase):
    def test_history_includes_decisions_logged_against_approval_resource(self):
        requirement_id = uuid.uuid4()
        decision_event = {
            "Action": "ApprovalApprove",
            "Outcome": "Success",
            "CreatedAtUtc": "2026-10-26T12:00:00",
        }
        result = Mock()
        result.mappings.return_value.all.return_value = [decision_event]
        db = Mock()
        db.execute.return_value = result

        history_loader = getattr(requirements, "_requirement_audit_history", None)
        self.assertIsNotNone(history_loader, "requirement audit history loader is missing")
        history = history_loader(db, requirement_id)

        statement = str(db.execute.call_args.args[0])
        self.assertIn("JOIN Approval", statement)
        self.assertIn("ResourceType = 'Approval'", statement)
        self.assertIn("RequirementID", statement)
        self.assertEqual(history, [decision_event])


if __name__ == "__main__":
    unittest.main()