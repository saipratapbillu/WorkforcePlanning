# projects api blueprint
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.security.dependencies import get_current_user
from app.services.security_service import SecurityService
from app.security.roles import has_role


router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def require_project_scope(user: dict):
    if not has_role(user.get("role"), "BUSINESS_USER", "APPROVER", "EXECUTIVE", "WORKFORCE_MANAGER", "PLATFORM_OWNER"):
        raise HTTPException(status_code=403, detail="Project access denied")
    return user


@router.get("")
def projects(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    require_project_scope(user)
    if "text/html" in request.headers.get("accept", ""):
        return FileResponse(STATIC_DIR / "projects.html")
    return SecurityService(db).GetVisibleProjects(user)
