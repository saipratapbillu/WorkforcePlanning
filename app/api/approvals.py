from fastapi import APIRouter, Depends
from uuid import UUID
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.schemas import ApprovalDecisionRequest
from app.security.dependencies import get_current_user
from app.security.permissions import require_roles
from app.models.entities import Approval
from app.services.approval_service import ApprovalService
from app.services.security_service import SecurityService

router = APIRouter(prefix="/approvals", tags=["Approvals"])
service = ApprovalService()


def serialize_approval(row, can_decide=False):
    return {
        "approval_id": str(row.ApprovalID),
        "requirement_id": str(row.RequirementID),
        "assigned_to_user_id": str(row.AssignedToUserID),
        "stage": row.ApprovalStage,
        "status": row.Status,
        "comments": row.Comments,
        "created_at_utc": row.CreatedAtUtc,
        "decision_at_utc": row.DecisionAtUtc,
        "can_decide": can_decide and row.Status == "Pending",
    }


@router.get("")
def approvals(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = SecurityService(db).GetVisibleApprovals(user)
    return [
        {
            "approval_id": str(row["ApprovalID"]),
            "requirement_id": str(row["RequirementID"]),
            "assigned_to_user_id": str(row["AssignedToUserID"]) if row["AssignedToUserID"] else None,
            "stage": row["ApprovalStage"],
            "status": row["Status"],
            "comments": row["Comments"],
            "created_at_utc": row["CreatedAtUtc"],
            "decision_at_utc": row["DecisionAtUtc"],
            "can_decide": bool(row["CanDecide"]) and row["Status"] == "Pending",
            "requirement_title": row["RequirementTitle"],
            "requirement_priority": row["RequirementPriority"],
            "requirement_status": row["RequirementStatus"],
        }
        for row in rows
    ]


@router.post("/{approval_id}/decision")
def decide_approval(
    approval_id: UUID,
    body: ApprovalDecisionRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if not SecurityService(db).GetVisibleApprovals(user, approval_id):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Approval not found")
    row = service.decide(db, approval_id, user, body.action, body.reason)
    db.commit()
    db.refresh(row)
    return serialize_approval(row)