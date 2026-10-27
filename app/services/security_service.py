from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.security_repository import SecurityRepository


class SecurityService:
    def __init__(self, db: Session):
        self.repository = SecurityRepository(db)

    def GetVisibleRequirements(self, user: dict, requirement_id: UUID | None = None) -> list[dict]:
        return self.repository.GetVisibleRequirements(user, requirement_id)

    def GetVisibleProjects(self, user: dict, project_id: UUID | None = None) -> list[dict]:
        return self.repository.GetVisibleProjects(user, project_id)

    def GetVisibleTasks(self, user: dict, task_id: UUID | None = None) -> list[dict]:
        return self.repository.GetVisibleTasks(user, task_id)

    def GetVisibleApprovals(self, user: dict, approval_id: UUID | None = None) -> list[dict]:
        return self.repository.GetVisibleApprovals(user, approval_id)

    def GetVisibleNotifications(self, user: dict, notification_id: UUID | None = None) -> list[dict]:
        return self.repository.GetVisibleNotifications(user, notification_id)

    def MarkVisibleNotificationRead(self, user: dict, notification_id: UUID) -> bool:
        return self.repository.MarkVisibleNotificationRead(user, notification_id)

    def GetVisibleSummary(self, user: dict) -> dict:
        return self.repository.GetVisibleSummary(user)
