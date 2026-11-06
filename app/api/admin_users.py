import json
import re
import uuid
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.security.dependencies import get_current_user
from app.security.passwords import hash_password
from app.security.permissions import require_roles

router = APIRouter(prefix="/admin/users", tags=["Super Admin User Management"])
OWNER_ROLE_CODES = ("PLATFORM_OWNER", "OWNER", "SUPER_ADMIN")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=4, max_length=128)
    display_name: str = Field(min_length=1, max_length=200)
    role_id: UUID
    department: str | None = Field(default=None, max_length=100)
    manager_user_id: UUID | None = None
    company_id: UUID | None = None
    department_id: UUID | None = None
    position_id: UUID | None = None


class UserPatch(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=255)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    department: str | None = Field(default=None, max_length=100)
    manager_user_id: UUID | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=4, max_length=128)


class RoleAssignment(BaseModel):
    role_id: UUID


class OrganizationAssignment(BaseModel):
    company_id: UUID
    department_id: UUID
    position_id: UUID


class SkillAssignment(BaseModel):
    skill_id: UUID
    proficiency: int = Field(ge=1, le=5)
    status: Literal["Pending", "Active", "Revoked"] = "Pending"
    evidence: str | None = Field(default=None, max_length=2000)


class SkillsAssignment(BaseModel):
    skills: list[SkillAssignment] = Field(max_length=200)


def _validate_email(email: str) -> str:
    normalized = email.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=422, detail="A valid email address is required")
    return normalized


def _actor_id(user: dict) -> str:
    actor_id = user.get("sub")
    if not actor_id:
        raise HTTPException(status_code=401, detail="Authenticated user identity is missing")
    try:
        return str(UUID(str(actor_id)))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Authenticated user identity is invalid") from None


def _audit(db: Session, actor_id: str, action: str, user_id: UUID, details: dict | None = None):
    db.execute(text("""
        INSERT dbo.AuditLog(CorrelationID,ActorType,ActorID,Action,ResourceType,ResourceID,Outcome,Details)
        VALUES(:correlation,'User',:actor,:action,'AppUser',:resource,'Success',:details)
    """), {
        "correlation": uuid.uuid4(),
        "actor": actor_id,
        "action": action,
        "resource": str(user_id),
        "details": json.dumps(details or {}, default=str),
    })


def _active_role(db: Session, role_id: UUID):
    role = db.execute(text("""
        SELECT RoleID,RoleCode FROM dbo.Role WHERE RoleID=:role_id AND IsActive=1
    """), {"role_id": role_id}).mappings().first()
    if not role:
        raise HTTPException(status_code=422, detail="Role must exist and be active")
    return role


def _guard_reviewer_role(
    role,
    actor_id: str,
    target_id,
    target_email: str | None = None,
    actor_email: str | None = None,
    target_creator_id=None,
):
    """Require reviewer identities to predate and be independent of the assigning actor."""
    if str(role["RoleCode"]).upper() != "RUNTIME_REVIEWER":
        return
    same_user_id = target_id is not None and str(target_id).lower() == actor_id.lower()
    same_email = target_email is not None and (
        not actor_email or target_email.strip().lower() == actor_email.strip().lower()
    )
    unknown_or_self_creator = (
        target_creator_id is None or str(target_creator_id).lower() == actor_id.lower()
    )
    if same_user_id or same_email or unknown_or_self_creator:
        raise HTTPException(
            status_code=403,
            detail="RUNTIME_REVIEWER must be provisioned independently by a different actor",
        )


def _validate_organization(db: Session, company_id: UUID, department_id: UUID, position_id: UUID):
    valid = db.execute(text("""
        SELECT c.CompanyID
        FROM dbo.Company c
        JOIN dbo.Department d ON d.DepartmentID=:department_id
            AND d.CompanyID=c.CompanyID AND d.Status='Active'
        JOIN dbo.Position p ON p.PositionID=:position_id
            AND p.DepartmentID=d.DepartmentID AND p.Status='Active'
        WHERE c.CompanyID=:company_id AND c.Status='Active'
    """), {
        "company_id": company_id,
        "department_id": department_id,
        "position_id": position_id,
    }).scalar_one_or_none()
    if not valid:
        raise HTTPException(
            status_code=422,
            detail="Company, department, and position must be active and have valid parent relationships",
        )


def _target_user(db: Session, user_id: UUID, for_update: bool = False):
    lock_hint = " WITH (UPDLOCK,ROWLOCK)" if for_update else ""
    user = db.execute(text(f"""
        SELECT u.UserID,u.IsActive,u.CreatedByUserID,r.RoleCode,r.IsActive AS RoleIsActive
        FROM dbo.AppUser u{lock_hint}
        LEFT JOIN dbo.Role r ON r.RoleID=u.RoleID
        WHERE u.UserID=:user_id
    """), {"user_id": user_id}).mappings().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _protect_last_owner(db: Session, target, target_id: UUID, actor_id: str):
    if UUID(actor_id) != target_id:
        return
    if not target.get("IsActive"):
        return
    if not target.get("RoleIsActive"):
        return
    if str(target.get("RoleCode") or "").upper() not in OWNER_ROLE_CODES:
        return
    active_owners = db.execute(text("""
        SELECT COUNT(*)
        FROM dbo.AppUser u WITH (UPDLOCK,HOLDLOCK)
        JOIN dbo.Role r ON r.RoleID=u.RoleID AND r.IsActive=1
        WHERE u.IsActive=1 AND UPPER(r.RoleCode) IN
            ('PLATFORM_OWNER','OWNER','SUPER_ADMIN')
    """)).scalar_one()
    if active_owners <= 1:
        raise HTTPException(status_code=409, detail="The last active platform owner cannot deactivate or demote themselves")


@router.get("", dependencies=[Depends(require_roles("PLATFORM_OWNER"))])
def list_users(
    active: bool | None = None,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),
    db: Session = Depends(get_db),
):
    predicates = []
    params = {"limit": limit, "offset": offset}
    if active is not None:
        predicates.append("u.IsActive=:active")
        params["active"] = int(active)
    if q:
        predicates.append("(u.Email LIKE :query OR u.DisplayName LIKE :query)")
        params["query"] = f"%{q.strip()}%"
    where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
    rows = db.execute(text(f"""
        SELECT u.UserID AS user_id,u.Email AS email,u.DisplayName AS display_name,
               u.Department AS department,u.RoleID AS role_id,r.RoleCode AS role_code,
               u.ManagerUserID AS manager_user_id,u.CompanyID AS company_id,
               u.DepartmentID AS department_id,u.PositionID AS position_id,
               u.IsActive AS is_active
        FROM dbo.AppUser u
        LEFT JOIN dbo.Role r ON r.RoleID=u.RoleID
        {where}
        ORDER BY u.Email
        OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
    """), params).mappings().all()
    return {"items": [dict(row) for row in rows], "limit": limit, "offset": offset}


@router.get("/catalogs", dependencies=[Depends(require_roles("PLATFORM_OWNER"))])
def user_management_catalogs(db: Session = Depends(get_db)):
    roles = db.execute(text("""
        SELECT RoleID AS id,RoleCode AS code,RoleName AS name
        FROM dbo.Role WHERE IsActive=1 ORDER BY RoleLevel,RoleName
    """)).mappings().all()
    skills = db.execute(text("""
        SELECT SkillID AS id,Name AS name
        FROM dbo.Skill WHERE Status IN ('Approved','Active') ORDER BY Name
    """)).mappings().all()
    companies = db.execute(text("""
        SELECT CompanyID AS id,CompanyName AS name
        FROM dbo.Company WHERE Status='Active' ORDER BY CompanyName
    """)).mappings().all()
    departments = db.execute(text("""
        SELECT DepartmentID AS id,CompanyID AS company_id,DepartmentName AS name
        FROM dbo.Department WHERE Status='Active' ORDER BY DepartmentName
    """)).mappings().all()
    positions = db.execute(text("""
        SELECT p.PositionID AS id,p.DepartmentID AS department_id,p.PositionName AS name,p.Grade AS grade
        FROM dbo.Position p JOIN dbo.Department d ON d.DepartmentID=p.DepartmentID
        WHERE p.Status='Active' AND d.Status='Active' ORDER BY p.PositionName
    """)).mappings().all()
    managers = db.execute(text("""
        SELECT u.UserID AS id,u.DisplayName AS name,u.Email AS email
        FROM dbo.AppUser u
        JOIN dbo.Role r ON r.RoleID=u.RoleID AND r.IsActive=1
        WHERE u.IsActive=1 AND UPPER(r.RoleCode) IN
            ('WORKFORCE_MANAGER','PLATFORM_OWNER','MANAGER','ADMIN','OWNER','SUPER_ADMIN')
        ORDER BY u.DisplayName
    """)).mappings().all()
    return {
        "roles": [dict(row) for row in roles],
        "skills": [dict(row) for row in skills],
        "companies": [dict(row) for row in companies],
        "departments": [dict(row) for row in departments],
        "positions": [dict(row) for row in positions],
        "managers": [dict(row) for row in managers],
    }


@router.post("", status_code=201, dependencies=[Depends(require_roles("PLATFORM_OWNER"))])
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    actor_id = _actor_id(user)
    email = _validate_email(body.email)
    duplicate = db.execute(text("""
        SELECT UserID FROM dbo.AppUser WHERE LOWER(Email)=:email
    """), {"email": email}).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    role = _active_role(db, body.role_id)
    new_user_id = uuid.uuid4()
    _guard_reviewer_role(
        role,
        actor_id,
        new_user_id,
        target_email=email,
        actor_email=user.get("email"),
        target_creator_id=actor_id,
    )
    if body.manager_user_id is not None:
        manager = db.execute(text("""
            SELECT UserID FROM dbo.AppUser WHERE UserID=:manager_id AND IsActive=1
        """), {"manager_id": body.manager_user_id}).scalar_one_or_none()
        if not manager:
            raise HTTPException(status_code=422, detail="Manager must be an active user")

    org_values = (body.company_id, body.department_id, body.position_id)
    if any(value is not None for value in org_values):
        if any(value is None for value in org_values):
            raise HTTPException(status_code=422, detail="Company, department, and position must be provided together")
        _validate_organization(db, body.company_id, body.department_id, body.position_id)

    db.execute(text("""
        INSERT dbo.AppUser
            (UserID,Email,PasswordHash,DisplayName,Department,RoleID,ManagerUserID,CreatedByUserID,
             CompanyID,DepartmentID,PositionID,IsActive)
        VALUES
            (:user_id,:email,:password_hash,:display_name,:department,:role_id,:manager_id,:created_by_user_id,
             :company_id,:department_id,:position_id,1)
    """), {
        "user_id": new_user_id,
        "email": email,
        "password_hash": hash_password(body.password),
        "display_name": body.display_name.strip(),
        "department": body.department,
        "role_id": body.role_id,
        "manager_id": body.manager_user_id,
        "created_by_user_id": actor_id,
        "company_id": body.company_id,
        "department_id": body.department_id,
        "position_id": body.position_id,
    })
    _audit(db, actor_id, "AdminUserCreated", new_user_id, {"email": email, "role_id": str(body.role_id)})
    db.commit()
    return {"user_id": str(new_user_id), "email": email, "display_name": body.display_name.strip(), "is_active": True}


@router.patch("/{user_id}", dependencies=[Depends(require_roles("PLATFORM_OWNER"))])
def update_user(
    user_id: UUID,
    body: UserPatch,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    actor_id = _actor_id(user)
    _target_user(db, user_id, for_update=True)
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="At least one field must be provided")
    if "email" in changes:
        if changes["email"] is None:
            raise HTTPException(status_code=422, detail="Email cannot be null")
        changes["email"] = _validate_email(changes["email"])
        duplicate = db.execute(text("""
            SELECT UserID FROM dbo.AppUser
            WHERE LOWER(Email)=:email AND UserID<>:user_id
        """), {"email": changes["email"], "user_id": user_id}).scalar_one_or_none()
        if duplicate:
            raise HTTPException(status_code=409, detail="A user with this email already exists")
    if "display_name" in changes:
        if changes["display_name"] is None:
            raise HTTPException(status_code=422, detail="Display name cannot be null")
        changes["display_name"] = changes["display_name"].strip()
    if "manager_user_id" in changes and changes["manager_user_id"] is not None:
        if changes["manager_user_id"] == user_id:
            raise HTTPException(status_code=422, detail="A user cannot be their own manager")
        manager = db.execute(text("""
            SELECT UserID FROM dbo.AppUser WHERE UserID=:manager_id AND IsActive=1
        """), {"manager_id": changes["manager_user_id"]}).scalar_one_or_none()
        if not manager:
            raise HTTPException(status_code=422, detail="Manager must be an active user")
    columns = {
        "email": "Email",
        "display_name": "DisplayName",
        "department": "Department",
        "manager_user_id": "ManagerUserID",
    }
    assignments = ", ".join(f"{columns[key]}=:{key}" for key in changes)
    db.execute(text(f"UPDATE dbo.AppUser SET {assignments} WHERE UserID=:user_id"), {**changes, "user_id": user_id})
    _audit(db, actor_id, "AdminUserUpdated", user_id, changes)
    db.commit()
    return {"user_id": str(user_id), "updated_fields": sorted(changes)}


def _deactivate_user(user_id: UUID, db: Session, user: dict, action: str):
    actor_id = _actor_id(user)
    target = _target_user(db, user_id, for_update=True)
    if target["IsActive"]:
        _protect_last_owner(db, target, user_id, actor_id)
    db.execute(text("UPDATE dbo.AppUser SET IsActive=0 WHERE UserID=:user_id"), {"user_id": user_id})
    _audit(db, actor_id, action, user_id)
    db.commit()
    return {"user_id": str(user_id), "is_active": False}


@router.delete("/{user_id}", dependencies=[Depends(require_roles("PLATFORM_OWNER"))])
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return _deactivate_user(user_id, db, user, "AdminUserDeleted")


@router.post("/{user_id}/disable", dependencies=[Depends(require_roles("PLATFORM_OWNER"))])
def disable_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return _deactivate_user(user_id, db, user, "AdminUserDisabled")


@router.post("/{user_id}/enable", dependencies=[Depends(require_roles("PLATFORM_OWNER"))])
def enable_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    actor_id = _actor_id(user)
    _target_user(db, user_id, for_update=True)
    db.execute(text("UPDATE dbo.AppUser SET IsActive=1 WHERE UserID=:user_id"), {"user_id": user_id})
    _audit(db, actor_id, "AdminUserEnabled", user_id)
    db.commit()
    return {"user_id": str(user_id), "is_active": True}


@router.post("/{user_id}/reset-password", dependencies=[Depends(require_roles("PLATFORM_OWNER"))])
def reset_password(
    user_id: UUID,
    body: PasswordReset,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    actor_id = _actor_id(user)
    _target_user(db, user_id, for_update=True)
    db.execute(text("""
        UPDATE dbo.AppUser SET PasswordHash=:password_hash WHERE UserID=:user_id
    """), {"password_hash": hash_password(body.password), "user_id": user_id})
    _audit(db, actor_id, "AdminUserPasswordReset", user_id)
    db.commit()
    return {"user_id": str(user_id), "password_reset": True}


@router.put("/{user_id}/role", dependencies=[Depends(require_roles("PLATFORM_OWNER"))])
def assign_role(
    user_id: UUID,
    body: RoleAssignment,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    actor_id = _actor_id(user)
    target = _target_user(db, user_id, for_update=True)
    role = _active_role(db, body.role_id)
    new_role_code = str(role["RoleCode"]).upper()
    _guard_reviewer_role(
        role,
        actor_id,
        user_id,
        target_creator_id=target.get("CreatedByUserID"),
    )
    if (str(target.get("RoleCode") or "").upper() in OWNER_ROLE_CODES
            and new_role_code not in OWNER_ROLE_CODES):
        _protect_last_owner(db, target, user_id, actor_id)
    db.execute(text("UPDATE dbo.AppUser SET RoleID=:role_id WHERE UserID=:user_id"), {
        "role_id": body.role_id,
        "user_id": user_id,
    })
    _audit(db, actor_id, "AdminUserRoleUpdated", user_id, {"role_id": str(body.role_id)})
    db.commit()
    return {"user_id": str(user_id), "role_id": str(body.role_id), "role_code": role["RoleCode"]}


@router.put("/{user_id}/organization", dependencies=[Depends(require_roles("PLATFORM_OWNER"))])
def assign_organization(
    user_id: UUID,
    body: OrganizationAssignment,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    actor_id = _actor_id(user)
    _target_user(db, user_id, for_update=True)
    _validate_organization(db, body.company_id, body.department_id, body.position_id)
    db.execute(text("""
        UPDATE dbo.AppUser
        SET CompanyID=:company_id,DepartmentID=:department_id,PositionID=:position_id
        WHERE UserID=:user_id
    """), {
        "company_id": body.company_id,
        "department_id": body.department_id,
        "position_id": body.position_id,
        "user_id": user_id,
    })
    details = body.model_dump(mode="json")
    _audit(db, actor_id, "AdminUserOrganizationUpdated", user_id, details)
    db.commit()
    return {"user_id": str(user_id), "organization": details}


@router.put("/{user_id}/skills", dependencies=[Depends(require_roles("PLATFORM_OWNER"))])
def assign_skills(
    user_id: UUID,
    body: SkillsAssignment,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    actor_id = _actor_id(user)
    _target_user(db, user_id, for_update=True)
    skill_ids = [item.skill_id for item in body.skills]
    if len(skill_ids) != len(set(skill_ids)):
        raise HTTPException(status_code=422, detail="Each skill may be assigned only once")
    if skill_ids:
        found = db.execute(text("""
            SELECT SkillID FROM dbo.Skill WHERE SkillID IN :skill_ids
        """).bindparams(bindparam("skill_ids", expanding=True)), {
            "skill_ids": skill_ids,
        }).scalars().all()
        if {str(v).lower() for v in found} != {str(v).lower() for v in skill_ids}:
            raise HTTPException(status_code=422, detail="Every assigned skill must exist")
    for skill in body.skills:
        existing = db.execute(text("""
            SELECT UserID FROM dbo.AppUserSkill
            WHERE UserID=:user_id AND SkillID=:skill_id
        """), {"user_id": user_id, "skill_id": skill.skill_id}).scalar_one_or_none()
        params = {
            "user_id": user_id,
            "skill_id": skill.skill_id,
            "proficiency": skill.proficiency,
            "status": skill.status,
            "evidence": skill.evidence or "Administrative assignment",
            "actor": actor_id,
        }
        if existing:
            db.execute(text("""
                UPDATE dbo.AppUserSkill
                SET Proficiency=:proficiency,Status=:status,Evidence=:evidence
                WHERE UserID=:user_id AND SkillID=:skill_id
            """), params)
        else:
            db.execute(text("""
                INSERT dbo.AppUserSkill
                    (UserID,SkillID,Proficiency,Status,Evidence,CreatedAtUtc,CreatedBy)
                VALUES
                    (:user_id,:skill_id,:proficiency,:status,:evidence,SYSUTCDATETIME(),:actor)
            """), params)
    if skill_ids:
        db.execute(text("""
            DELETE FROM dbo.AppUserSkill
            WHERE UserID=:user_id AND SkillID NOT IN :skill_ids
        """).bindparams(bindparam("skill_ids", expanding=True)), {
            "user_id": user_id,
            "skill_ids": skill_ids,
        })
    else:
        db.execute(text("DELETE FROM dbo.AppUserSkill WHERE UserID=:user_id"), {"user_id": user_id})
    _audit(db, actor_id, "AdminUserSkillsUpdated", user_id, {"skill_ids": [str(item) for item in skill_ids]})
    db.commit()
    return {"user_id": str(user_id), "skills_updated": len(skill_ids)}


@router.get("/{user_id}/skills", dependencies=[Depends(require_roles("PLATFORM_OWNER"))])
def get_user_skills(
    user_id: UUID,
    db: Session = Depends(get_db),
):
    _target_user(db, user_id)
    rows = db.execute(text("""
        SELECT s.SkillID AS skill_id,s.Name AS name,us.Proficiency AS proficiency,
               us.Status AS status,us.Evidence AS evidence,us.CreatedAtUtc AS created_at_utc,
               us.CreatedBy AS created_by,us.ApprovedAtUtc AS approved_at_utc,
               us.ApprovedBy AS approved_by
        FROM dbo.AppUserSkill us
        JOIN dbo.Skill s ON s.SkillID=us.SkillID
        WHERE us.UserID=:user_id
        ORDER BY s.Name
    """), {"user_id": user_id}).mappings().all()
    return {"user_id": str(user_id), "skills": [dict(row) for row in rows]}
