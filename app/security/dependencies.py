import uuid
from types import SimpleNamespace

from jose import JWTError, jwt

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import AppUser
from app.security.jwt import ALGORITHM, SECRET_KEY
from app.security.roles import canonical_role

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if not hasattr(request, "state"):
        request.state = SimpleNamespace()
    cached_user = getattr(getattr(request, "state", None), "security_principal", None)
    if cached_user:
        return cached_user

    token = credentials.credentials if credentials else request.cookies.get("ai_workforce_session")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer="ai-workforce-os",
            audience="ai-workforce-os-web",
            options={"require_sub": True, "require_exp": True},
        )
        user = db.get(AppUser, uuid.UUID(payload["sub"]))
    except (JWTError, KeyError, ValueError):
        user = None
        payload = None

    if not user or not getattr(user, "IsActive", False) or not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role_record = getattr(user, "Role", None)
    if not role_record or not getattr(role_record, "IsActive", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    legacy_role = getattr(role_record, "RoleCode", None)
    if not legacy_role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_context = {
        "sub": str(user.UserID),
        "email": getattr(user, "Email", None),
        "name": getattr(user, "DisplayName", None),
        "department": getattr(user, "Department", None),
        "role": canonical_role(legacy_role),
        "legacy_role": legacy_role,
        "company_id": str(getattr(user, "CompanyID", None)) if getattr(user, "CompanyID", None) else None,
        "department_id": str(getattr(user, "DepartmentID", None)) if getattr(user, "DepartmentID", None) else None,
        "position_id": str(getattr(user, "PositionID", None)) if getattr(user, "PositionID", None) else None,
    }
    request.state.security_principal = user_context
    return user_context