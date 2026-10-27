import json
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.security.dependencies import get_current_user
from app.security.org_scope import organization_mapping_issues
from app.security.permissions import require_roles

router = APIRouter(prefix="/admin/org-mappings", tags=["Organization Mapping"])
ADMIN_ROLES = ("OWNER", "SUPER_ADMIN")


class OrganizationMapping(BaseModel):
    company_id: UUID
    department_id: UUID
    position_id: UUID


def _validate_mapping(db: Session, user_id: UUID, mapping: OrganizationMapping):
    valid = db.execute(text("""
        SELECT u.UserID
        FROM dbo.AppUser u
        JOIN dbo.Company c ON c.CompanyID=:company_id AND c.Status='Active'
        JOIN dbo.Department d ON d.DepartmentID=:department_id AND d.CompanyID=c.CompanyID AND d.Status='Active'
        JOIN dbo.Position p ON p.PositionID=:position_id AND p.DepartmentID=d.DepartmentID AND p.Status='Active'
        WHERE u.UserID=:user_id AND u.IsActive=1
    """), {
        "company_id": mapping.company_id,
        "department_id": mapping.department_id,
        "position_id": mapping.position_id,
        "user_id": user_id,
    }).scalar_one_or_none()
    if not valid:
        raise HTTPException(status_code=422, detail="User, company, department, and position must be active and have valid parent relationships")


def _mapping_state(db: Session):
    users = db.execute(text("""
        SELECT u.UserID,u.Email,u.DisplayName,u.Department AS LegacyDepartment,u.IsActive,
               u.CompanyID,u.DepartmentID,u.PositionID,
               c.CompanyName,d.DepartmentName,p.PositionName
        FROM dbo.AppUser u
        LEFT JOIN dbo.Company c ON c.CompanyID=u.CompanyID
        LEFT JOIN dbo.Department d ON d.DepartmentID=u.DepartmentID
        LEFT JOIN dbo.Position p ON p.PositionID=u.PositionID
        ORDER BY u.IsActive DESC,u.Email
    """)).mappings().all()
    companies = db.execute(text("""
        SELECT CompanyID,CompanyName FROM dbo.Company WHERE Status='Active' ORDER BY CompanyName
    """)).mappings().all()
    departments = db.execute(text("""
        SELECT DepartmentID,CompanyID,DepartmentName FROM dbo.Department
        WHERE Status='Active' ORDER BY DepartmentName
    """)).mappings().all()
    positions = db.execute(text("""
        SELECT p.PositionID,p.DepartmentID,d.CompanyID,p.PositionName,p.Grade
        FROM dbo.Position p JOIN dbo.Department d ON d.DepartmentID=p.DepartmentID
        WHERE p.Status='Active' AND d.Status='Active' ORDER BY p.PositionName
    """)).mappings().all()
    return {
        "users": [dict(row) for row in users],
        "companies": [dict(row) for row in companies],
        "departments": [dict(row) for row in departments],
        "positions": [dict(row) for row in positions],
        "validation": organization_mapping_issues(db),
    }


@router.get("", dependencies=[Depends(require_roles(*ADMIN_ROLES))])
def get_mapping_state(db: Session = Depends(get_db)):
    return _mapping_state(db)


@router.get("/report", dependencies=[Depends(require_roles(*ADMIN_ROLES))])
def mapping_report(db: Session = Depends(get_db)):
    state = _mapping_state(db)
    active_users = [user for user in state["users"] if user["IsActive"]]
    return {
        "active_user_count": len(active_users),
        "fully_mapped_count": sum(bool(user["CompanyID"] and user["DepartmentID"] and user["PositionID"]) for user in active_users),
        "issues": state["validation"],
        "ready": not any(state["validation"].values()),
    }


@router.post("/{user_id}/validate", dependencies=[Depends(require_roles(*ADMIN_ROLES))])
def validate_mapping(
    user_id: UUID,
    body: OrganizationMapping,
    db: Session = Depends(get_db),
):
    _validate_mapping(db, user_id, body)
    user_exists = db.execute(text("""
        SELECT COUNT(*) FROM dbo.AppUser WHERE UserID=:user_id AND IsActive=1
    """), {"user_id": user_id}).scalar_one()
    return {
        "valid": user_exists == 1,
        "unique_user_mapping": True,
        "company_id": str(body.company_id),
        "department_id": str(body.department_id),
        "position_id": str(body.position_id),
    }


@router.put("/{user_id}", dependencies=[Depends(require_roles(*ADMIN_ROLES))])
def save_mapping(
    user_id: UUID,
    body: OrganizationMapping,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    target = db.execute(text("""
        SELECT UserID,CompanyID,DepartmentID,PositionID
        FROM dbo.AppUser WITH (UPDLOCK,ROWLOCK)
        WHERE UserID=:user_id AND IsActive=1
    """), {"user_id": user_id}).mappings().first()
    if not target:
        raise HTTPException(status_code=404, detail="Active user not found")

    _validate_mapping(db, user_id, body)
    db.execute(text("""
        UPDATE dbo.AppUser SET CompanyID=:company_id,DepartmentID=:department_id,PositionID=:position_id
        WHERE UserID=:user_id AND IsActive=1
    """), {
        "company_id": body.company_id,
        "department_id": body.department_id,
        "position_id": body.position_id,
        "user_id": user_id,
    })
    db.execute(text("""
        INSERT dbo.AuditLog(CorrelationID,ActorType,ActorID,Action,ResourceType,ResourceID,Outcome,Details)
        VALUES(:correlation,'User',:actor,'OrganizationMappingUpdated','AppUser',:resource,'Success',:details)
    """), {
        "correlation": uuid.uuid4(),
        "actor": user["sub"],
        "resource": str(user_id),
        "details": json.dumps({
            "company_id": str(body.company_id),
            "department_id": str(body.department_id),
            "position_id": str(body.position_id),
        }),
    })
    db.commit()
    issues = organization_mapping_issues(db)
    return {"user_id": str(user_id), "mapping": body.model_dump(mode="json"), "validation": issues, "ready": not any(issues.values())}
