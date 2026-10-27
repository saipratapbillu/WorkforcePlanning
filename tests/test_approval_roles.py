import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import HTTPException

from app.services.approval_service import ApprovalService


class ApprovalRoleTests(unittest.TestCase):
    def test_authorized_platform_owner_decision_updates_gate_and_creates_project(self):
        actor_id, approval_id, requirement_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        approval = SimpleNamespace(
            ApprovalID=approval_id,
            RequirementID=requirement_id,
            AssignedToUserID=uuid.uuid4(),
            ApprovalStage="CEO_REVIEW",
            Status="Pending",
            Comments=None,
            DecisionAtUtc=None,
            ApprovedAtUtc=None,
        )
        requirement = SimpleNamespace(
            RequirementID=requirement_id,
            Status="PendingApproval",
            CreatedByUserID=actor_id,
            CreatedBy=str(actor_id),
            ModifiedAtUtc=None,
            ModifiedBy=None,
        )
        approval_result = Mock()
        approval_result.scalar_one_or_none.return_value = approval
        lock_result = Mock()
        lock_result.first.return_value = (requirement_id,)
        pending_result = Mock()
        pending_result.first.return_value = None
        rejected_result = Mock()
        rejected_result.first.return_value = None
        database = Mock()
        database.execute.side_effect = [
            approval_result, lock_result, Mock(), pending_result, rejected_result, Mock()
        ]
        database.get.return_value = requirement
        project_factory = Mock()

        decided = ApprovalService(project_factory=project_factory).decide(
            database,
            approval_id,
            {"sub": str(actor_id), "role": "PLATFORM_OWNER"},
            "approve",
            "Approved for governed planning only.",
        )

        self.assertIs(decided, approval)
        self.assertEqual(approval.Status, "Approved")
        self.assertEqual(requirement.Status, "Approved")
        project_factory.create_project.assert_called_once_with(
            database, requirement, approval_id=approval_id
        )
        database.flush.assert_called()

    def test_assigned_business_user_cannot_decide_approval(self):
        user_id, approval_id = uuid.uuid4(), uuid.uuid4()
        approval = SimpleNamespace(AssignedToUserID=user_id, Status="Pending")
        database = Mock()
        database.execute.return_value.scalar_one_or_none.return_value = approval

        with self.assertRaises(HTTPException) as raised:
            ApprovalService().decide(
                database,
                approval_id,
                {"sub": str(user_id), "role": "BUSINESS_USER"},
                "approve",
                "Not authorized to approve this request.",
            )

        self.assertEqual(raised.exception.status_code, 403)
        database.flush.assert_not_called()


if __name__ == "__main__":
    unittest.main()
