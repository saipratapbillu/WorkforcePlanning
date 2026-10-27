import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import case, select, text

from app.models.entities import AppUser, Approval, Notification, Requirement, Role
from app.services.project_factory import ProjectFactory
from app.security.roles import canonical_role, has_role


class ApprovalService:
    DECISION_ROLES = {"APPROVER", "PLATFORM_OWNER"}
    OVERSIGHT_ROLES = ("APPROVER", "PLATFORM_OWNER", "OWNER", "SUPER_ADMIN")

    def __init__(self, project_factory=None):
        self.project_factory = project_factory or ProjectFactory()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _notify(db, user_id, notification_type, title, body, resource_type, resource_id, correlation_id):
        db.add(Notification(
            NotificationID=uuid.uuid4(),
            UserID=user_id,
            NotificationType=notification_type,
            Title=title,
            Body=body,
            ResourceType=resource_type,
            ResourceID=str(resource_id),
            CorrelationID=correlation_id,
            IsRead=False,
            CreatedAtUtc=ApprovalService._now(),
        ))

    def create_requirement_approval(self, db, requirement, assessment, correlation_id):
        existing = db.execute(
            select(Approval).where(
                Approval.RequirementID == requirement.RequirementID,
                Approval.ApprovalStage == "CEO_REVIEW",
                Approval.Status == "Pending",
            )
        ).scalars().first()
        if existing:
            return existing

        approvers = db.execute(
            select(AppUser, Role.RoleCode)
            .join(Role, AppUser.RoleID == Role.RoleID)
            .where(AppUser.IsActive == True, Role.IsActive == True, Role.RoleCode.in_(self.OVERSIGHT_ROLES))
            .order_by(case((Role.RoleCode == "APPROVER", 0), else_=1), AppUser.Email)
        ).all()
        if not approvers:
            raise HTTPException(status_code=503, detail="No active Owner/Super Admin is configured to receive this approval.")

        assigned_user, _role_code = approvers[0]
        now = self._now()
        approval = Approval(
            ApprovalID=uuid.uuid4(),
            RequirementID=requirement.RequirementID,
            AssignedToUserID=assigned_user.UserID,
            ApprovalStage="CEO_REVIEW",
            Status="Pending",
            Comments=None,
            CreatedAtUtc=now,
            ApprovedAtUtc=None,
            DecisionAtUtc=None,
        )
        db.add(approval)
        db.flush()

        # Notify every active user who has authority to decide, including Owner oversight.
        recipients = {recipient.UserID: recipient for recipient, _role_code in approvers}
        for recipient in recipients.values():
            self._notify(
                db,
                recipient.UserID,
                "APPROVAL_REQUIRED",
                "Approval required",
                f"A {requirement.Priority} priority business request is waiting for governance review.",
                "Approval",
                approval.ApprovalID,
                correlation_id,
            )

        db.execute(text("""
            INSERT INTO AuditLog
                (CorrelationID, ActorType, ActorID, Action, ResourceType, ResourceID, Outcome, Details)
            VALUES
                (:correlation, 'System', 'approval-workflow', 'ApprovalCreated', 'Requirement', :resource, 'Success', :details)
        """), {
            "correlation": correlation_id,
            "resource": str(requirement.RequirementID),
            "details": '{"stage":"CEO_REVIEW","status":"Pending"}',
        })
        return approval

    def create_approval(self, db, requirement, assessment, correlation_id):
        return self.create_requirement_approval(db, requirement, assessment, correlation_id)

    def list_for_user(self, db, user):
        query = select(Approval, Requirement.Title, Requirement.Priority, Requirement.Status).join(
            Requirement, Requirement.RequirementID == Approval.RequirementID
        ).order_by(Approval.CreatedAtUtc.desc())
        role = canonical_role(user["role"])
        if role not in {"EXECUTIVE", "WORKFORCE_MANAGER", "PLATFORM_OWNER"}:
            user_id = uuid.UUID(user["sub"])
            query = query.where(
                (Approval.AssignedToUserID == user_id)
                | (Requirement.CreatedByUserID == user_id)
            )
        rows = db.execute(query).all()
        actor_id = uuid.UUID(user["sub"])
        can_decide_role = has_role(user["role"], *self.DECISION_ROLES)
        return [
            (approval, title, priority, requirement_status, can_decide_role or approval.AssignedToUserID == actor_id)
            for approval, title, priority, requirement_status in rows
        ]

    def decide(self, db, approval_id, user, action, reason):
        approval = db.execute(
            select(Approval).where(Approval.ApprovalID == approval_id).with_for_update()
        ).scalar_one_or_none()
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")

        actor_id = uuid.UUID(user["sub"])
        can_decide_role = has_role(user["role"], *self.DECISION_ROLES)
        if not can_decide_role or (approval.AssignedToUserID != actor_id and user["role"] != "PLATFORM_OWNER"):
            raise HTTPException(status_code=403, detail="An assigned Approver or Platform Owner is required to decide this approval")
        if approval.Status != "Pending":
            raise HTTPException(status_code=409, detail=f"Approval is already {approval.Status.lower()}")

        # Serialize gate decisions for one requirement so concurrent approvals cannot double-create delivery.
        db.execute(text("""
            SELECT RequirementID
            FROM Requirement WITH (UPDLOCK, HOLDLOCK)
            WHERE RequirementID = :requirement_id
        """), {"requirement_id": approval.RequirementID}).first()

        now = self._now()
        status_by_action = {"approve": "Approved", "reject": "Rejected", "request_information": "InformationRequired"}
        if action not in status_by_action:
            raise HTTPException(status_code=422, detail="Unsupported approval decision")
        approval.Status = status_by_action[action]
        approval.Comments = reason.strip()
        approval.DecisionAtUtc = now
        approval.ApprovedAtUtc = now if action == "approve" else None

        requirement = db.get(Requirement, approval.RequirementID)
        if not requirement:
            raise HTTPException(status_code=409, detail="Approval is linked to a missing requirement")

        db.execute(text("""
            INSERT INTO AuditLog
                (CorrelationID, ActorType, ActorID, Action, ResourceType, ResourceID, Outcome, Details)
            VALUES
                (:correlation, 'User', :actor, :action, 'Approval', :resource, 'Success', :details)
        """), {
            "correlation": uuid.uuid4(),
            "actor": str(actor_id),
            "action": f"Approval{action.title()}",
            "resource": str(approval.ApprovalID),
            "details": '{"reason_recorded":true}',
        })

        db.flush()

        pending_count = db.execute(
            select(Approval.ApprovalID).where(
                Approval.RequirementID == approval.RequirementID,
                Approval.ApprovalStage == approval.ApprovalStage,
                Approval.Status == "Pending",
            )
        ).first()
        rejected_count = db.execute(
            select(Approval.ApprovalID).where(
                Approval.RequirementID == approval.RequirementID,
                Approval.ApprovalStage == approval.ApprovalStage,
                Approval.Status.in_(["Rejected", "InformationRequired"]),
            )
        ).first()

        if action == "reject":
            requirement.Status = "Rejected"
        elif action == "request_information":
            requirement.Status = "InformationRequired"
        elif not pending_count and not rejected_count:
            requirement.Status = "Approved"
            self.project_factory.create_project(db, requirement, approval_id=approval.ApprovalID)
            try:
                requester_id = requirement.CreatedByUserID or uuid.UUID(requirement.CreatedBy)
            except (ValueError, TypeError, AttributeError):
                requester_id = None
            if requester_id:
                self._notify(
                    db,
                    requester_id,
                    "REQUEST_APPROVED",
                    "Request approved",
                    "All required governance approvals are complete. A planned project and delivery tasks have been created.",
                    "Requirement",
                    requirement.RequirementID,
                    uuid.uuid4(),
                )

        if action in {"reject", "request_information"}:
            try:
                requester_id = requirement.CreatedByUserID or uuid.UUID(requirement.CreatedBy)
            except (ValueError, TypeError, AttributeError):
                requester_id = None
            if requester_id:
                self._notify(
                    db,
                    requester_id,
                    "APPROVAL_DECISION",
                    "Approval decision recorded",
                    "A governance decision was recorded for your request. Sign in to review the request status.",
                    "Requirement",
                    requirement.RequirementID,
                    uuid.uuid4(),
                )

        requirement.ModifiedAtUtc = now
        requirement.ModifiedBy = str(actor_id)
        db.flush()
        return approval