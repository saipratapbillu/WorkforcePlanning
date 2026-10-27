from dataclasses import dataclass
from uuid import UUID

from app.security.roles import canonical_role


@dataclass(frozen=True)
class VisibilityContext:
    user_id: UUID
    role: str
    company_id: UUID | None = None
    department_id: UUID | None = None

    @classmethod
    def from_user(cls, user: dict):
        return cls(
            user_id=UUID(str(user["sub"])),
            role=canonical_role(user.get("role")),
            company_id=UUID(str(user["company_id"])) if user.get("company_id") else None,
            department_id=UUID(str(user["department_id"])) if user.get("department_id") else None,
        )

    @property
    def supported(self) -> bool:
        return self.role in {"BUSINESS_USER", "APPROVER", "EXECUTIVE", "WORKFORCE_MANAGER", "PLATFORM_OWNER"}

    @property
    def is_super_admin(self) -> bool:
        return self.role == "PLATFORM_OWNER"

    @property
    def is_organization_scope(self) -> bool:
        return self.role in {"EXECUTIVE", "WORKFORCE_MANAGER", "PLATFORM_OWNER"}
