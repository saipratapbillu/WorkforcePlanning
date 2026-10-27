from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.security.visibility import VisibilityContext


_OWNER_SCOPE = """
    (:is_super_admin = 1 OR EXISTS (
        SELECT 1
        FROM dbo.AppUser owner_user
        WHERE owner_user.UserID = {owner_column}
          AND owner_user.IsActive = 1
          AND (
                (:role IN ('BUSINESS_USER', 'APPROVER') AND owner_user.UserID = :user_id)
             OR :is_organization_scope = 1
          )
    ))
"""


class SecurityRepository:
    """Single source of truth for human-user row visibility."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _context(user: dict) -> VisibilityContext:
        context = VisibilityContext.from_user(user)
        if not context.supported:
            return context
        return context

    @staticmethod
    def _params(context: VisibilityContext) -> dict:
        return {
            "user_id": context.user_id,
            "role": context.role,
            "is_super_admin": context.is_super_admin,
            "is_organization_scope": context.is_organization_scope,
        }

    @staticmethod
    def _owner_scope(owner_column: str) -> str:
        if not owner_column.replace(".", "").replace("_", "").isalnum():
            raise ValueError("Invalid SQL owner column")
        return _OWNER_SCOPE.format(owner_column=owner_column)

    def _all(self, statement: str, params: dict) -> list[dict]:
        try:
            result = self.db.execute(text(statement), params)
            rows = result.mappings().all() if hasattr(result, "mappings") else result
            if rows is None:
                return []
            return [dict(row) for row in rows]
        except TypeError:
            return []

    def GetVisibleRequirements(self, user: dict, requirement_id: UUID | None = None) -> list[dict]:
        context = self._context(user)
        if not context.supported:
            return []
        owner_scope = self._owner_scope("r.CreatedByUserID")
        return self._all(f"""
            SELECT r.RequirementID,r.Title,r.Description,r.RequestedBy,r.Priority,r.RiskLevel,
                   r.Status,r.CreatedAtUtc,r.CreatedByUserID,r.ModifiedAtUtc,r.ModifiedBy
            FROM dbo.Requirement r
            WHERE {owner_scope}
              AND (:requirement_id IS NULL OR r.RequirementID=:requirement_id)
            ORDER BY r.CreatedAtUtc DESC
        """, {**self._params(context), "requirement_id": requirement_id})

    def GetVisibleProjects(self, user: dict, project_id: UUID | None = None) -> list[dict]:
        context = self._context(user)
        if not context.supported:
            return []
        owner_scope = self._owner_scope("p.CreatedByUserID")
        req_scope = self._owner_scope("r.CreatedByUserID")
        return self._all(f"""
            SELECT p.ProjectID,p.RequirementID,p.ProjectName,p.Objective,p.BusinessOwner,
                   p.BudgetAmount,p.Status,p.CreatedAtUtc,p.CreatedByUserID,p.ModifiedAtUtc,p.ModifiedBy
            FROM dbo.Project p
            JOIN dbo.Requirement r ON r.RequirementID=p.RequirementID
            WHERE {owner_scope} AND {req_scope}
              AND (:project_id IS NULL OR p.ProjectID=:project_id)
            ORDER BY p.CreatedAtUtc DESC
        """, {**self._params(context), "project_id": project_id})

    def GetVisibleTasks(self, user: dict, task_id: UUID | None = None) -> list[dict]:
        context = self._context(user)
        if not context.supported:
            return []
        task_scope = self._owner_scope("t.CreatedByUserID")
        project_scope = self._owner_scope("p.CreatedByUserID")
        requirement_scope = self._owner_scope("r.CreatedByUserID")
        return self._all(f"""
            SELECT t.TaskID,t.ProjectID,p.ProjectName,t.ParentTaskID,t.Description,t.Priority,
                   t.AssignedAgentID,t.RiskLevel,t.Status,t.ApprovalRequired,t.CreatedAtUtc,
                   t.CreatedByUserID,t.ModifiedAtUtc,t.ModifiedBy,t.PlannedSequence,
                   t.RequiredRoleCode,t.EstimatedEffortHours,t.CompletedAtUtc
            FROM dbo.Task t
            JOIN dbo.Project p ON p.ProjectID=t.ProjectID
            JOIN dbo.Requirement r ON r.RequirementID=p.RequirementID
            WHERE {task_scope} AND {project_scope} AND {requirement_scope}
              AND (:task_id IS NULL OR t.TaskID=:task_id)
            ORDER BY t.PlannedSequence,t.CreatedAtUtc DESC
        """, {**self._params(context), "task_id": task_id})

    def GetVisibleApprovals(self, user: dict, approval_id: UUID | None = None) -> list[dict]:
        context = self._context(user)
        if not context.supported:
            return []
        req_scope = self._owner_scope("r.CreatedByUserID")
        return self._all(f"""
            SELECT a.ApprovalID,a.RequirementID,a.AssignedToUserID,a.ApprovalStage,a.Status,
                   a.Comments,a.CreatedAtUtc,a.ApprovedAtUtc,a.DecisionAtUtc,
                   r.Title AS RequirementTitle,r.Priority AS RequirementPriority,
                   r.Status AS RequirementStatus,
                   CASE WHEN (a.AssignedToUserID=:user_id AND :role='APPROVER') OR :role='PLATFORM_OWNER' THEN 1 ELSE 0 END AS CanDecide
            FROM dbo.Approval a
            JOIN dbo.Requirement r ON r.RequirementID=a.RequirementID
            WHERE (a.AssignedToUserID=:user_id OR {req_scope})
              AND (:approval_id IS NULL OR a.ApprovalID=:approval_id)
            ORDER BY a.CreatedAtUtc DESC
        """, {**self._params(context), "approval_id": approval_id})

    def GetVisibleNotifications(self, user: dict, notification_id: UUID | None = None) -> list[dict]:
        context = self._context(user)
        if not context.supported:
            return []
        return self._all("""
            SELECT n.NotificationID,n.UserID,n.NotificationType,n.Title,n.Body,n.ResourceType,
                   n.ResourceID,n.CorrelationID,n.IsRead,n.CreatedAtUtc,n.ReadAtUtc
            FROM dbo.Notification n
            WHERE (n.UserID=:user_id OR :is_super_admin=1)
              AND (:notification_id IS NULL OR n.NotificationID=:notification_id)
            ORDER BY n.CreatedAtUtc DESC
        """, {**self._params(context), "notification_id": notification_id})

    def MarkVisibleNotificationRead(self, user: dict, notification_id: UUID) -> bool:
        context = self._context(user)
        if not context.supported:
            return False
        result = self.db.execute(text("""
            UPDATE dbo.Notification
            SET IsRead=1,ReadAtUtc=SYSUTCDATETIME()
            WHERE NotificationID=:notification_id
              AND (:is_super_admin=1 OR UserID=:user_id) AND IsRead=0
        """), {"notification_id": notification_id, "user_id": context.user_id,
              "is_super_admin": context.is_super_admin})
        return bool(result.rowcount)

    def GetVisibleSummary(self, user: dict) -> dict:
        context = self._context(user)
        if not context.supported:
            return {key: 0 for key in ("requirements", "projects", "tasks", "approvals", "notifications", "assessments")}
        params = self._params(context)
        requirement_scope = self._owner_scope("r.CreatedByUserID")
        project_scope = self._owner_scope("p.CreatedByUserID")
        task_scope = self._owner_scope("t.CreatedByUserID")
        query = f"""
            SELECT
              (SELECT COUNT(*) FROM dbo.Requirement r WHERE {requirement_scope}) AS Requirements,
              (SELECT COUNT(*) FROM dbo.Project p JOIN dbo.Requirement r ON r.RequirementID=p.RequirementID WHERE {project_scope} AND {self._owner_scope('r.CreatedByUserID')}) AS Projects,
              (SELECT COUNT(*) FROM dbo.Task t JOIN dbo.Project p ON p.ProjectID=t.ProjectID JOIN dbo.Requirement r ON r.RequirementID=p.RequirementID WHERE {task_scope} AND {self._owner_scope('p.CreatedByUserID')} AND {self._owner_scope('r.CreatedByUserID')}) AS Tasks,
              (SELECT COUNT(*) FROM dbo.Approval a JOIN dbo.Requirement r ON r.RequirementID=a.RequirementID WHERE (a.AssignedToUserID=:user_id OR {self._owner_scope('r.CreatedByUserID')})) AS Approvals,
              (SELECT COUNT(*) FROM dbo.Notification n WHERE (n.UserID=:user_id OR :is_super_admin=1)) AS Notifications,
              (SELECT COUNT(*) FROM dbo.RequirementAssessment x JOIN dbo.Requirement r ON r.RequirementID=x.RequirementID WHERE {self._owner_scope('r.CreatedByUserID')}) AS Assessments
        """
        row = self.db.execute(text(query), params).mappings().one()
        return {
            "requirements": int(row["Requirements"]),
            "projects": int(row["Projects"]),
            "tasks": int(row["Tasks"]),
            "approvals": int(row["Approvals"]),
            "notifications": int(row["Notifications"]),
            "assessments": int(row["Assessments"]),
        }
