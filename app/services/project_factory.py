import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import text
from app.services.workforce_planner import WorkforcePlanner
from app.services.organization_orchestrator import OrganizationOrchestrator


class ProjectFactory:
    TASK_TEMPLATES = (
        "Requirements confirmation",
        "Solution design",
        "Implementation",
        "Verification and testing",
        "Deployment readiness",
        "Training and handover",
        "Hypercare and support",
    )

    @staticmethod
    def _created_by_user_id(db, requirement):
        owner_id = getattr(requirement, "CreatedByUserID", None)
        if not owner_id:
            try:
                owner_id = uuid.UUID(str(requirement.CreatedBy))
            except (ValueError, TypeError, AttributeError) as error:
                raise HTTPException(
                    status_code=409,
                    detail="Requirement has no normalized user owner; project creation is blocked",
                ) from error
        exists = db.execute(
            text("SELECT UserID FROM AppUser WHERE UserID=:user_id"),
            {"user_id": owner_id},
        ).scalar_one_or_none()
        if not exists:
            raise HTTPException(
                status_code=409,
                detail="Requirement owner does not match an AppUser; project creation is blocked",
            )
        requirement.CreatedByUserID = owner_id
        return owner_id

    def create_project(self, db, requirement, assessment=None, approval_id=None):
        created_by_user_id = self._created_by_user_id(db, requirement)
        existing = db.execute(
            text("SELECT ProjectID FROM Project WHERE RequirementID = :requirement_id"),
            {"requirement_id": requirement.RequirementID},
        ).scalar_one_or_none()

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if existing:
            project_id = existing
        else:
            project_id = uuid.uuid4()
            db.execute(
                text("""
                    INSERT INTO Project
                        (ProjectID, RequirementID, ProjectName, Objective, BusinessOwner,CreatedByUserID,
                         BudgetAmount, Status, CreatedAtUtc, CreatedBy, ModifiedAtUtc, ModifiedBy)
                    VALUES
                        (:project_id, :requirement_id, :name, :objective, :owner,:created_by_user_id,
                         0, 'Planned', :created_at, :created_by, :modified_at, :modified_by)
                """),
                {
                    "project_id": project_id,
                    "requirement_id": requirement.RequirementID,
                    "name": requirement.Title[:250],
                    "objective": requirement.Description,
                    "owner": requirement.RequestedBy,
                    "created_by_user_id": created_by_user_id,
                    "created_at": now,
                    "created_by": requirement.CreatedBy,
                    "modified_at": now,
                    "modified_by": requirement.CreatedBy,
                },
            )

        self.generate_tasks(db, project_id, requirement)
        WorkforcePlanner().auto_assign_agents(db, project_id, requirement)
        from app.services.agent_runtime import queue_pending_tasks
        queue_pending_tasks(db, project_id, requirement.CreatedBy)
        if approval_id:
            OrganizationOrchestrator().bootstrap_approved_company(
                db, requirement.RequirementID, approval_id
            )
        return project_id

    def generate_tasks(self, db, project_id, requirement):
        created_by_user_id = self._created_by_user_id(db, requirement)
        existing_count = db.execute(
            text("SELECT COUNT(*) FROM Task WHERE ProjectID = :project_id"),
            {"project_id": project_id},
        ).scalar_one()
        if existing_count:
            return

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for description in self.TASK_TEMPLATES:
            db.execute(
                text("""
                    INSERT INTO Task
                        (TaskID, ProjectID, ParentTaskID, Description, Priority,
                         AssignedAgentID, RiskLevel, BudgetLimit, TokenLimit, Status,
                         ApprovalRequired, CreatedAtUtc, CreatedBy, CreatedByUserID,ModifiedAtUtc, ModifiedBy)
                    VALUES
                        (:task_id, :project_id, NULL, :description, :priority,
                         NULL, :risk_level, 0, 0, 'Planned', 0,
                         :created_at, :created_by, :created_by_user_id,:modified_at, :modified_by)
                """),
                {
                    "task_id": uuid.uuid4(),
                    "project_id": project_id,
                    "description": description,
                    "priority": requirement.Priority,
                    "risk_level": requirement.RiskLevel,
                    "created_at": now,
                    "created_by": requirement.CreatedBy,
                    "created_by_user_id": created_by_user_id,
                    "modified_at": now,
                    "modified_by": requirement.CreatedBy,
                },
            )
