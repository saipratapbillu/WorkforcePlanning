import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.security.dependencies import get_current_user
from app.security.permissions import require_roles
from app.repositories.security_repository import SecurityRepository


router = APIRouter(prefix="/workforce/management", tags=["Workforce Management"])
MANAGEMENT_ROLES = ("WORKFORCE_MANAGER", "PLATFORM_OWNER")


class SkillNeed(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    minimum_proficiency: int = Field(default=3, ge=1, le=5)


class PlannedTask(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=2000)
    estimated_effort_hours: float = Field(gt=0, le=10000)
    required_skills: list[SkillNeed] = Field(default_factory=list, max_length=30)
    required_certifications: list[str] = Field(default_factory=list, max_length=20)


class PlannedStory(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=2000)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=30)
    story_points: int = Field(ge=1, le=100)
    required_skills: list[SkillNeed] = Field(default_factory=list, max_length=30)
    required_certifications: list[str] = Field(default_factory=list, max_length=20)
    sprint_name: str | None = Field(default=None, max_length=100)
    tasks: list[PlannedTask] = Field(min_length=1, max_length=30)


class PlannedFeature(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=2000)
    stories: list[PlannedStory] = Field(min_length=1, max_length=50)


class PlannedEpic(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=2000)
    features: list[PlannedFeature] = Field(min_length=1, max_length=30)


class PlannedSprint(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    start_date: date
    end_date: date
    capacity_hours: float = Field(ge=0, le=100000)

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.end_date < self.start_date:
            raise ValueError("Sprint end date must be on or after its start date")
        return self


class BacklogPlan(BaseModel):
    sprints: list[PlannedSprint] = Field(default_factory=list, max_length=30)
    epics: list[PlannedEpic] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_sprint_names_and_capacity(self):
        sprint_names = [sprint.name.strip().casefold() for sprint in self.sprints]
        if len(sprint_names) != len(set(sprint_names)):
            raise ValueError("Sprint names must be unique within the project plan")
        sprints = {name: sprint.capacity_hours for name, sprint in zip(sprint_names, self.sprints)}
        planned_hours: dict[str, float] = {}
        for epic in self.epics:
            for feature in epic.features:
                for story in feature.stories:
                    sprint_name = story.sprint_name.strip().casefold() if story.sprint_name else None
                    if sprint_name and sprint_name not in sprints:
                        raise ValueError(f"Unknown sprint name: {story.sprint_name}")
                    if sprint_name:
                        planned_hours[sprint_name] = planned_hours.get(sprint_name, 0) + sum(
                            task.estimated_effort_hours for task in story.tasks
                        )
        for sprint_name, total_hours in planned_hours.items():
            if total_hours > sprints[sprint_name]:
                raise ValueError(f"Planned task effort exceeds sprint capacity for {sprint_name}")
        return self


class AvailabilityUpdate(BaseModel):
    week_start_date: date
    available_hours: float = Field(ge=0, le=168)
    is_available: bool
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_monday(self):
        if self.week_start_date.weekday() != 0:
            raise ValueError("week_start_date must be a Monday")
        return self


class CertificationCreate(BaseModel):
    certification_name: str = Field(min_length=2, max_length=200)
    issuer: str | None = Field(default=None, max_length=200)
    issued_at_utc: datetime | None = None
    expires_at_utc: datetime | None = None
    evidence: str = Field(min_length=10, max_length=2000)


class SkillDecision(BaseModel):
    action: Literal["approve", "reject"]
    reason: str = Field(min_length=5, max_length=2000)


class CertificationDecision(BaseModel):
    action: Literal["approve", "reject"]
    reason: str = Field(min_length=5, max_length=2000)


class RecommendationDecision(BaseModel):
    action: Literal["approve", "reject"]
    reason: str = Field(min_length=5, max_length=2000)


def _week_start(value: date | None = None) -> date:
    current = value or date.today()
    return current - timedelta(days=current.weekday())


def _audit(db: Session, user: dict, action: str, resource_type: str, resource_id: str, details: dict):
    db.execute(text("""
        INSERT INTO dbo.AuditLog
            (CorrelationID, ActorType, ActorID, Action, ResourceType, ResourceID, Outcome, Details)
        VALUES
            (:correlation_id, 'User', :actor_id, :action, :resource_type, :resource_id, 'Success', :details)
    """), {
        "correlation_id": uuid.uuid4(),
        "actor_id": user["sub"],
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": json.dumps(details, ensure_ascii=True),
    })


def _require_manager_scope(db: Session, actor: dict, user_id: UUID):
    if actor.get("role") == "PLATFORM_OWNER":
        return
    visible = db.execute(text("""
        SELECT 1
        FROM dbo.AppUser target
        WHERE target.UserID=:user_id AND target.IsActive=1
          AND (target.UserID=:actor_id OR target.ManagerUserID=:actor_id)
    """), {"user_id": user_id, "actor_id": UUID(actor["sub"])}).scalar_one_or_none()
    if not visible:
        raise HTTPException(status_code=404, detail="Workforce member not found")


def _require_visible_project(db: Session, actor: dict, project_id: UUID):
    if not SecurityRepository(db).GetVisibleProjects(actor, project_id):
        raise HTTPException(status_code=404, detail="Project not found")


def _planning_permissions():
    return Depends(require_roles(*MANAGEMENT_ROLES))


@router.get("/skills", dependencies=[_planning_permissions()])
def list_skills(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT SkillID, Name, Description, RiskLevel
        FROM dbo.Skill
        WHERE Status IN ('Approved', 'Active')
        ORDER BY Name
    """)).mappings().all()
    return [dict(row) for row in rows]


@router.get("/capacity", dependencies=[_planning_permissions()])
def workforce_capacity(
    db: Session = Depends(get_db),
    actor=Depends(get_current_user),
):
    week = _week_start()
    if actor.get("role") == "PLATFORM_OWNER":
        people = db.execute(text("""
            SELECT u.UserID,u.DisplayName,u.Email,u.ManagerUserID,u.CompanyID,u.DepartmentID,u.PositionID,
                   a.AvailableHours,a.IsAvailable,a.Note
            FROM dbo.AppUser u
            LEFT JOIN dbo.AppUserAvailability a ON a.UserID=u.UserID AND a.WeekStartDate=:week_start
            WHERE u.IsActive=1
            ORDER BY u.DisplayName
        """), {"week_start": week}).mappings().all()
    else:
        people = db.execute(text("""
            SELECT u.UserID,u.DisplayName,u.Email,u.ManagerUserID,u.CompanyID,u.DepartmentID,u.PositionID,
                   a.AvailableHours,a.IsAvailable,a.Note
            FROM dbo.AppUser u
            LEFT JOIN dbo.AppUserAvailability a ON a.UserID=u.UserID AND a.WeekStartDate=:week_start
            WHERE u.IsActive=1 AND (u.UserID=:actor_id OR u.ManagerUserID=:actor_id)
            ORDER BY u.DisplayName
        """), {"week_start": week, "actor_id": UUID(actor["sub"])}).mappings().all()
    people_items = []
    for row in people:
        user_id = row["UserID"]
        skills = db.execute(text("""
            SELECT s.Name,us.Proficiency,us.Status
            FROM dbo.AppUserSkill us JOIN dbo.Skill s ON s.SkillID=us.SkillID
            WHERE us.UserID=:user_id
            ORDER BY s.Name
        """), {"user_id": user_id}).mappings().all()
        certifications = db.execute(text("""
            SELECT CertificationName,Issuer,ExpiresAtUtc,Status
            FROM dbo.AppUserCertification
            WHERE UserID=:user_id
            ORDER BY CertificationName
        """), {"user_id": user_id}).mappings().all()
        reserved = db.execute(text("""
            SELECT COALESCE(SUM(t.EstimatedEffortHours),0)
            FROM dbo.ProjectTaskAssignment a
            JOIN dbo.ProjectDeliveryTask t ON t.ProjectTaskID=a.ProjectTaskID
            WHERE a.UserID=:user_id AND a.Status='Active'
        """), {"user_id": user_id}).scalar_one()
        available_hours = float(row["AvailableHours"] or 0)
        reserved_hours = float(reserved or 0)
        active_skills = [skill for skill in skills if skill["Status"] == "Active"]
        active_certifications = [
            certification for certification in certifications
            if certification["Status"] == "Active"
            and (certification["ExpiresAtUtc"] is None or certification["ExpiresAtUtc"].date() >= week)
        ]
        people_items.append({
            "user_id": str(user_id),
            "display_name": row["DisplayName"],
            "email": row["Email"],
            "manager_user_id": str(row["ManagerUserID"]) if row["ManagerUserID"] else None,
            "company_id": str(row["CompanyID"]) if row["CompanyID"] else None,
            "department_id": str(row["DepartmentID"]) if row["DepartmentID"] else None,
            "position_id": str(row["PositionID"]) if row["PositionID"] else None,
            "week_start_date": week.isoformat(),
            "is_available": bool(row["IsAvailable"]) if row["IsAvailable"] is not None else False,
            "available_hours": available_hours,
            "reserved_hours": reserved_hours,
            "remaining_hours": max(0.0, available_hours - reserved_hours),
            "skills": [dict(skill) for skill in skills],
            "certifications": [dict(certification) for certification in certifications],
            "readiness": "READY" if active_skills and active_certifications and row["IsAvailable"] and available_hours > reserved_hours else "NOT_READY",
        })
    return {"week_start_date": week.isoformat(), "people": people_items}


@router.put("/users/{user_id}/capacity", dependencies=[_planning_permissions()])
def update_availability(
    user_id: UUID,
    body: AvailabilityUpdate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_user),
):
    _require_manager_scope(db, actor, user_id)
    params = {
        "user_id": user_id,
        "week_start": body.week_start_date,
        "hours": body.available_hours,
        "available": body.is_available,
        "note": body.note,
        "actor": actor["sub"],
    }
    exists = db.execute(text("""
        SELECT 1 FROM dbo.AppUserAvailability
        WHERE UserID=:user_id AND WeekStartDate=:week_start
    """), params).scalar_one_or_none()
    if exists:
        db.execute(text("""
            UPDATE dbo.AppUserAvailability
            SET AvailableHours=:hours,IsAvailable=:available,Note=:note,
                UpdatedAtUtc=SYSUTCDATETIME(),UpdatedBy=:actor
            WHERE UserID=:user_id AND WeekStartDate=:week_start
        """), params)
    else:
        db.execute(text("""
            INSERT dbo.AppUserAvailability
                (UserID,WeekStartDate,AvailableHours,IsAvailable,Note,UpdatedAtUtc,UpdatedBy)
            VALUES
                (:user_id,:week_start,:hours,:available,:note,SYSUTCDATETIME(),:actor)
        """), params)
    _audit(db, actor, "WorkforceAvailabilityUpdated", "AppUser", str(user_id), {
        "week_start_date": body.week_start_date.isoformat(),
        "available_hours": body.available_hours,
        "is_available": body.is_available,
    })
    db.commit()
    return {"user_id": str(user_id), "week_start_date": body.week_start_date.isoformat(), "saved": True}


@router.post("/users/{user_id}/certifications", status_code=201, dependencies=[_planning_permissions()])
def add_certification(
    user_id: UUID,
    body: CertificationCreate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_user),
):
    _require_manager_scope(db, actor, user_id)
    certification_id = uuid.uuid4()
    db.execute(text("""
        INSERT dbo.AppUserCertification
            (UserCertificationID,UserID,CertificationName,Issuer,IssuedAtUtc,ExpiresAtUtc,
             Status,Evidence,CreatedAtUtc,CreatedBy)
        VALUES
            (:id,:user_id,:name,:issuer,:issued,:expires,'Pending',:evidence,SYSUTCDATETIME(),:actor)
    """), {
        "id": certification_id, "user_id": user_id,
        "name": body.certification_name.strip(), "issuer": body.issuer,
        "issued": body.issued_at_utc, "expires": body.expires_at_utc,
        "evidence": body.evidence.strip(), "actor": actor["sub"],
    })
    _audit(db, actor, "WorkforceCertificationSubmitted", "AppUserCertification", str(certification_id), {
        "user_id": str(user_id), "certification_name": body.certification_name.strip(),
    })
    db.commit()
    return {"certification_id": str(certification_id), "status": "Pending"}


@router.put("/users/{user_id}/skills/{skill_id}/decision", dependencies=[_planning_permissions()])
def review_skill(
    user_id: UUID,
    skill_id: UUID,
    body: SkillDecision,
    db: Session = Depends(get_db),
    actor=Depends(get_current_user),
):
    _require_manager_scope(db, actor, user_id)
    skill = db.execute(text("""
        SELECT Proficiency,Status FROM dbo.AppUserSkill WITH (UPDLOCK,ROWLOCK)
        WHERE UserID=:user_id AND SkillID=:skill_id
    """), {"user_id": user_id, "skill_id": skill_id}).mappings().first()
    if not skill:
        raise HTTPException(status_code=404, detail="Pending skill record not found")
    if skill["Status"] != "Pending":
        raise HTTPException(status_code=409, detail="Only pending skill evidence can be reviewed")
    next_status = "Active" if body.action == "approve" else "Revoked"
    db.execute(text("""
        UPDATE dbo.AppUserSkill
        SET Status=:status,ApprovedAtUtc=SYSUTCDATETIME(),ApprovedBy=:actor
        WHERE UserID=:user_id AND SkillID=:skill_id AND Status='Pending'
    """), {
        "status": next_status, "actor": actor["sub"],
        "user_id": user_id, "skill_id": skill_id,
    })
    _audit(db, actor, f"WorkforceSkill{body.action.title()}", "AppUserSkill", f"{user_id}:{skill_id}", {
        "reason": body.reason.strip(),
        "proficiency": int(skill["Proficiency"]),
    })
    db.commit()
    return {"user_id": str(user_id), "skill_id": str(skill_id), "status": next_status}


@router.get("/skills/pending", dependencies=[_planning_permissions()])
def pending_skills(
    db: Session = Depends(get_db),
    actor=Depends(get_current_user),
):
    rows = db.execute(text("""
        SELECT us.UserID,us.SkillID,us.Proficiency,us.Evidence,us.CreatedAtUtc,
               u.DisplayName,s.Name AS SkillName,u.ManagerUserID
        FROM dbo.AppUserSkill us
        JOIN dbo.AppUser u ON u.UserID=us.UserID
        JOIN dbo.Skill s ON s.SkillID=us.SkillID
        WHERE us.Status='Pending' AND u.IsActive=1
          AND (:owner=1 OR u.ManagerUserID=:actor_id)
        ORDER BY us.CreatedAtUtc
    """), {
        "owner": actor.get("role") == "PLATFORM_OWNER",
        "actor_id": UUID(actor["sub"]),
    }).mappings().all()
    return [{
        "user_id": str(row["UserID"]),
        "display_name": row["DisplayName"],
        "skill_id": str(row["SkillID"]),
        "skill_name": row["SkillName"],
        "proficiency": int(row["Proficiency"]),
        "evidence": row["Evidence"],
        "created_at_utc": row["CreatedAtUtc"],
    } for row in rows]


@router.get("/certifications/pending", dependencies=[_planning_permissions()])
def pending_certifications(
    db: Session = Depends(get_db),
    actor=Depends(get_current_user),
):
    rows = db.execute(text("""
        SELECT c.UserCertificationID,c.UserID,c.CertificationName,c.Issuer,
               c.IssuedAtUtc,c.ExpiresAtUtc,c.Evidence,c.CreatedAtUtc,u.DisplayName
        FROM dbo.AppUserCertification c
        JOIN dbo.AppUser u ON u.UserID=c.UserID
        WHERE c.Status='Pending' AND u.IsActive=1
          AND (:owner=1 OR u.ManagerUserID=:actor_id)
        ORDER BY c.CreatedAtUtc
    """), {
        "owner": actor.get("role") == "PLATFORM_OWNER",
        "actor_id": UUID(actor["sub"]),
    }).mappings().all()
    return [{
        "certification_id": str(row["UserCertificationID"]),
        "user_id": str(row["UserID"]),
        "display_name": row["DisplayName"],
        "certification_name": row["CertificationName"],
        "issuer": row["Issuer"],
        "issued_at_utc": row["IssuedAtUtc"],
        "expires_at_utc": row["ExpiresAtUtc"],
        "evidence": row["Evidence"],
        "created_at_utc": row["CreatedAtUtc"],
    } for row in rows]


@router.put("/certifications/{certification_id}/decision", dependencies=[_planning_permissions()])
def review_certification(
    certification_id: UUID,
    body: CertificationDecision,
    db: Session = Depends(get_db),
    actor=Depends(get_current_user),
):
    row = db.execute(text("""
        SELECT c.UserID,c.Status,c.ExpiresAtUtc,u.ManagerUserID
        FROM dbo.AppUserCertification c WITH (UPDLOCK,ROWLOCK)
        JOIN dbo.AppUser u ON u.UserID=c.UserID
        WHERE c.UserCertificationID=:certification_id AND u.IsActive=1
    """), {"certification_id": certification_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Certification record not found")
    if actor.get("role") != "PLATFORM_OWNER" and str(row["ManagerUserID"]).lower() != str(actor["sub"]).lower():
        raise HTTPException(status_code=403, detail="Only the candidate's assigned manager may review this certification")
    if row["Status"] != "Pending":
        raise HTTPException(status_code=409, detail="Only pending certification evidence can be reviewed")
    if body.action == "approve" and row["ExpiresAtUtc"] is not None and row["ExpiresAtUtc"].date() < date.today():
        raise HTTPException(status_code=422, detail="Expired certification evidence cannot be approved")
    next_status = "Active" if body.action == "approve" else "Rejected"
    db.execute(text("""
        UPDATE dbo.AppUserCertification
        SET Status=:status,ReviewedAtUtc=SYSUTCDATETIME(),ReviewedBy=:actor
        WHERE UserCertificationID=:certification_id AND Status='Pending'
    """), {
        "status": next_status, "actor": actor["sub"],
        "certification_id": certification_id,
    })
    _audit(db, actor, f"WorkforceCertification{body.action.title()}", "AppUserCertification",
           str(certification_id), {"user_id": str(row["UserID"]), "reason": body.reason.strip()})
    db.commit()
    return {"certification_id": str(certification_id), "status": next_status}


def _skill_name_key(name: str) -> str:
    return " ".join(name.casefold().split())


def score_candidate(
    required_skills: list[dict],
    required_certifications: list[str],
    candidate_skills: list[dict],
    candidate_certifications: list[str],
    is_available: bool,
    available_hours: float,
    reserved_hours: float,
    task_hours: float,
) -> dict:
    skill_levels = {
        _skill_name_key(item["Name"]): int(item["Proficiency"])
        for item in candidate_skills if item["Status"] == "Active"
    }
    missing_skills = [
        item["name"] for item in required_skills
        if skill_levels.get(_skill_name_key(item["name"]), 0) < int(item["minimum_proficiency"])
    ]
    current_certs = {_skill_name_key(item) for item in candidate_certifications}
    missing_certifications = [
        item for item in required_certifications if _skill_name_key(item) not in current_certs
    ]
    remaining = max(0.0, available_hours - reserved_hours)
    enough_capacity = remaining >= task_hours
    eligible = is_available and enough_capacity and not missing_skills and not missing_certifications
    skills_score = 100.0 if not required_skills else round(
        100 * (len(required_skills) - len(missing_skills)) / len(required_skills), 1
    )
    capacity_score = round(min(remaining / task_hours, 1) * 100, 1) if task_hours else 100.0
    score = round(skills_score * 0.6 + (100.0 if is_available else 0.0) * 0.2 + capacity_score * 0.2, 1)
    return {
        "eligible_for_approval": eligible,
        "match_score": score,
        "skills_score": skills_score,
        "remaining_hours": remaining,
        "missing_skills": missing_skills,
        "missing_certifications": missing_certifications,
        "blockers": (
            (["Unavailable for the selected week"] if not is_available else [])
            + ([f"Insufficient capacity: {remaining:g} hours remain; {task_hours:g} required"] if not enough_capacity else [])
            + ([f"Missing skill proficiency: {', '.join(missing_skills)}"] if missing_skills else [])
            + ([f"Missing current certification: {', '.join(missing_certifications)}"] if missing_certifications else [])
        ),
    }


@router.post("/tasks/{task_id}/recommendations", status_code=201, dependencies=[_planning_permissions()])
def recommend_task_assignments(
    task_id: UUID,
    db: Session = Depends(get_db),
    actor=Depends(get_current_user),
):
    task = db.execute(text("""
        SELECT t.ProjectTaskID,t.Title,t.EstimatedEffortHours,t.RequiredSkillsJson,
               t.RequiredCertificationsJson,e.ProjectID
        FROM dbo.ProjectDeliveryTask t
        JOIN dbo.ProjectStory s ON s.StoryID=t.StoryID
        JOIN dbo.ProjectFeature f ON f.FeatureID=s.FeatureID
        JOIN dbo.ProjectEpic e ON e.EpicID=f.EpicID
        WHERE t.ProjectTaskID=:task_id AND t.Status IN ('Planned','InProgress')
    """), {"task_id": task_id}).mappings().first()
    if not task:
        raise HTTPException(status_code=404, detail="Planned task not found")
    _require_visible_project(db, actor, task["ProjectID"])

    required_skills = json.loads(task["RequiredSkillsJson"] or "[]")
    required_certifications = json.loads(task["RequiredCertificationsJson"] or "[]")
    week = _week_start()
    candidates = db.execute(text("""
        SELECT u.UserID,u.DisplayName,u.ManagerUserID,
               COALESCE(a.AvailableHours,0) AS AvailableHours,
               COALESCE(a.IsAvailable,0) AS IsAvailable
        FROM dbo.AppUser u
        LEFT JOIN dbo.AppUserAvailability a ON a.UserID=u.UserID AND a.WeekStartDate=:week_start
        WHERE u.IsActive=1
          AND u.ManagerUserID IS NOT NULL
          AND (:owner=1 OR (u.UserID=:actor_id OR u.ManagerUserID=:actor_id))
        ORDER BY u.DisplayName
    """), {
        "week_start": week,
        "owner": actor.get("role") == "PLATFORM_OWNER",
        "actor_id": UUID(actor["sub"]),
    }).mappings().all()
    scored = []
    skill_gaps: dict[str, set[str]] = {}
    for candidate in candidates:
        user_id = candidate["UserID"]
        skills = db.execute(text("""
            SELECT s.Name,us.Proficiency,us.Status
            FROM dbo.AppUserSkill us JOIN dbo.Skill s ON s.SkillID=us.SkillID
            WHERE us.UserID=:user_id
        """), {"user_id": user_id}).mappings().all()
        certifications = db.execute(text("""
            SELECT CertificationName
            FROM dbo.AppUserCertification
            WHERE UserID=:user_id AND Status='Active'
              AND (ExpiresAtUtc IS NULL OR ExpiresAtUtc>=SYSUTCDATETIME())
        """), {"user_id": user_id}).scalars().all()
        reserved = db.execute(text("""
            SELECT COALESCE(SUM(t.EstimatedEffortHours),0)
            FROM dbo.ProjectTaskAssignment a
            JOIN dbo.ProjectDeliveryTask t ON t.ProjectTaskID=a.ProjectTaskID
            WHERE a.UserID=:user_id AND a.Status='Active'
        """), {"user_id": user_id}).scalar_one()
        result = score_candidate(
            required_skills,
            required_certifications,
            [dict(skill) for skill in skills],
            list(certifications),
            bool(candidate["IsAvailable"]),
            float(candidate["AvailableHours"] or 0),
            float(reserved or 0),
            float(task["EstimatedEffortHours"]),
        )
        for missing in result["missing_skills"]:
            skill_gaps.setdefault(missing, set()).add(str(user_id))
        if result["eligible_for_approval"]:
            recommendation_id = uuid.uuid4()
            evidence = {
                **result,
                "week_start_date": week.isoformat(),
                "required_skills": required_skills,
                "required_certifications": required_certifications,
            }
            db.execute(text("""
                INSERT dbo.ResourceAssignmentRecommendation
                    (RecommendationID,ProjectTaskID,UserID,MatchScore,EvidenceJson,Status,
                     RecommendedAtUtc,RecommendedBy)
                VALUES
                    (:recommendation_id,:task_id,:user_id,:score,:evidence,'PendingApproval',
                     SYSUTCDATETIME(),:actor)
            """), {
                "recommendation_id": recommendation_id, "task_id": task_id,
                "user_id": user_id, "score": result["match_score"],
                "evidence": json.dumps(evidence, ensure_ascii=True), "actor": actor["sub"],
            })
            scored.append({
                "recommendation_id": str(recommendation_id),
                "user_id": str(user_id),
                "display_name": candidate["DisplayName"],
                **evidence,
                "status": "PendingApproval",
            })

    _audit(db, actor, "AssignmentRecommendationsCreated", "ProjectDeliveryTask", str(task_id), {
        "eligible_candidate_count": len(scored),
        "skill_gap_count": len(skill_gaps),
        "assignment_performed": False,
    })
    db.commit()
    return {
        "task_id": str(task_id),
        "recommendation_only": True,
        "assignment_performed": False,
        "manager_approval_required": True,
        "recommendations": sorted(scored, key=lambda item: (-item["match_score"], item["display_name"])),
        "skill_gaps": [
            {"skill": name, "eligible_people_missing_skill": len(people)}
            for name, people in sorted(skill_gaps.items())
        ],
        "week_start_date": week.isoformat(),
    }


@router.get("/recommendations/pending", dependencies=[_planning_permissions()])
def pending_recommendations(
    db: Session = Depends(get_db),
    actor=Depends(get_current_user),
):
    rows = db.execute(text("""
        SELECT r.RecommendationID,r.ProjectTaskID,r.UserID,r.MatchScore,r.EvidenceJson,
               r.Status,r.RecommendedAtUtc,u.DisplayName AS CandidateName,t.Title AS TaskTitle,
               u.ManagerUserID
        FROM dbo.ResourceAssignmentRecommendation r
        JOIN dbo.AppUser u ON u.UserID=r.UserID
        JOIN dbo.ProjectDeliveryTask t ON t.ProjectTaskID=r.ProjectTaskID
        WHERE r.Status='PendingApproval'
          AND (:owner=1 OR u.ManagerUserID=:actor_id)
        ORDER BY r.RecommendedAtUtc DESC
    """), {
        "owner": actor.get("role") == "PLATFORM_OWNER",
        "actor_id": UUID(actor["sub"]),
    }).mappings().all()
    return [{
        "recommendation_id": str(row["RecommendationID"]),
        "task_id": str(row["ProjectTaskID"]),
        "task_title": row["TaskTitle"],
        "user_id": str(row["UserID"]),
        "manager_user_id": str(row["ManagerUserID"]),
        "candidate_name": row["CandidateName"],
        "match_score": float(row["MatchScore"]),
        "evidence": json.loads(row["EvidenceJson"]),
        "status": row["Status"],
        "recommended_at_utc": row["RecommendedAtUtc"],
    } for row in rows]


@router.post("/recommendations/{recommendation_id}/decision", dependencies=[_planning_permissions()])
def decide_recommendation(
    recommendation_id: UUID,
    body: RecommendationDecision,
    db: Session = Depends(get_db),
    actor=Depends(get_current_user),
):
    row = db.execute(text("""
        SELECT r.RecommendationID,r.ProjectTaskID,r.UserID,r.Status,u.ManagerUserID,t.Status AS TaskStatus
        FROM dbo.ResourceAssignmentRecommendation r WITH (UPDLOCK,ROWLOCK)
        JOIN dbo.AppUser u ON u.UserID=r.UserID
        JOIN dbo.ProjectDeliveryTask t ON t.ProjectTaskID=r.ProjectTaskID
        WHERE r.RecommendationID=:recommendation_id
          AND u.IsActive=1
    """), {"recommendation_id": recommendation_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Assignment recommendation not found")
    if not row["ManagerUserID"]:
        raise HTTPException(status_code=409, detail="Candidate has no assigned manager; assignment remains blocked")
    if str(row["ManagerUserID"]).lower() != str(actor["sub"]).lower():
        raise HTTPException(status_code=403, detail="Only the candidate's assigned manager may decide this recommendation")
    if row["Status"] != "PendingApproval":
        raise HTTPException(status_code=409, detail="Recommendation is no longer awaiting manager approval")
    if body.action == "approve" and row["TaskStatus"] not in {"Planned", "InProgress"}:
        raise HTTPException(status_code=409, detail="Only an active planned task can receive an assignment")
    if body.action == "approve":
        active_assignment = db.execute(text("""
            SELECT 1 FROM dbo.ProjectTaskAssignment
            WHERE ProjectTaskID=:task_id AND Status='Active'
        """), {"task_id": row["ProjectTaskID"]}).scalar_one_or_none()
        if active_assignment:
            raise HTTPException(status_code=409, detail="Task already has an active resource assignment")
        db.execute(text("""
            UPDATE dbo.ResourceAssignmentRecommendation
            SET Status='Assigned',DecisionAtUtc=SYSUTCDATETIME(),
                DecisionByUserID=:actor_id,DecisionReason=:reason
            WHERE RecommendationID=:recommendation_id AND Status='PendingApproval'
        """), {
            "actor_id": UUID(actor["sub"]), "reason": body.reason.strip(),
            "recommendation_id": recommendation_id,
        })
        db.execute(text("""
            INSERT dbo.ProjectTaskAssignment
                (AssignmentID,ProjectTaskID,UserID,RecommendationID,AssignedAtUtc,AssignedByUserID,Status)
            VALUES
                (:assignment_id,:task_id,:user_id,:recommendation_id,SYSUTCDATETIME(),:actor_id,'Active')
        """), {
            "assignment_id": uuid.uuid4(), "task_id": row["ProjectTaskID"],
            "user_id": row["UserID"], "recommendation_id": recommendation_id,
            "actor_id": UUID(actor["sub"]),
        })
        status_value = "Assigned"
    else:
        db.execute(text("""
            UPDATE dbo.ResourceAssignmentRecommendation
            SET Status='Rejected',DecisionAtUtc=SYSUTCDATETIME(),
                DecisionByUserID=:actor_id,DecisionReason=:reason
            WHERE RecommendationID=:recommendation_id AND Status='PendingApproval'
        """), {
            "actor_id": UUID(actor["sub"]), "reason": body.reason.strip(),
            "recommendation_id": recommendation_id,
        })
        status_value = "Rejected"
    _audit(db, actor, f"AssignmentRecommendation{body.action.title()}", "ResourceAssignmentRecommendation",
           str(recommendation_id), {"task_id": str(row["ProjectTaskID"]), "reason": body.reason.strip()})
    db.commit()
    return {
        "recommendation_id": str(recommendation_id),
        "status": status_value,
        "assignment_created": body.action == "approve",
    }


@router.get("/projects/{project_id}/backlog", dependencies=[_planning_permissions()])
def get_project_backlog(
    project_id: UUID,
    db: Session = Depends(get_db),
    actor=Depends(get_current_user),
):
    _require_visible_project(db, actor, project_id)
    project = db.execute(text("""
        SELECT ProjectID,ProjectName,Status FROM dbo.Project WHERE ProjectID=:project_id
    """), {"project_id": project_id}).mappings().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    epics = db.execute(text("""
        SELECT EpicID,Title,Description,SequenceNumber,Status
        FROM dbo.ProjectEpic WHERE ProjectID=:project_id ORDER BY SequenceNumber
    """), {"project_id": project_id}).mappings().all()
    features = db.execute(text("""
        SELECT f.FeatureID,f.EpicID,f.Title,f.Description,f.SequenceNumber,f.Status
        FROM dbo.ProjectFeature f JOIN dbo.ProjectEpic e ON e.EpicID=f.EpicID
        WHERE e.ProjectID=:project_id ORDER BY e.SequenceNumber,f.SequenceNumber
    """), {"project_id": project_id}).mappings().all()
    stories = db.execute(text("""
        SELECT s.StoryID,s.FeatureID,s.SprintID,s.Title,s.Description,s.AcceptanceCriteriaJson,
               s.RequiredSkillsJson,s.RequiredCertificationsJson,s.StoryPoints,s.Status
        FROM dbo.ProjectStory s
        JOIN dbo.ProjectFeature f ON f.FeatureID=s.FeatureID
        JOIN dbo.ProjectEpic e ON e.EpicID=f.EpicID
        WHERE e.ProjectID=:project_id
        ORDER BY e.SequenceNumber,f.SequenceNumber,s.Title
    """), {"project_id": project_id}).mappings().all()
    tasks = db.execute(text("""
        SELECT t.ProjectTaskID,t.StoryID,t.Title,t.Description,t.RequiredSkillsJson,
               t.RequiredCertificationsJson,t.EstimatedEffortHours,t.Status
        FROM dbo.ProjectDeliveryTask t
        JOIN dbo.ProjectStory s ON s.StoryID=t.StoryID
        JOIN dbo.ProjectFeature f ON f.FeatureID=s.FeatureID
        JOIN dbo.ProjectEpic e ON e.EpicID=f.EpicID
        WHERE e.ProjectID=:project_id ORDER BY t.Title
    """), {"project_id": project_id}).mappings().all()
    sprints = db.execute(text("""
        SELECT SprintID,SprintName,StartDate,EndDate,CapacityHours,Status
        FROM dbo.ProjectSprint WHERE ProjectID=:project_id ORDER BY StartDate
    """), {"project_id": project_id}).mappings().all()
    return {
        "project": dict(project),
        "epics": [dict(item) for item in epics],
        "features": [dict(item) for item in features],
        "stories": [
            {
                **{key: value for key, value in dict(item).items()
                   if key not in {"AcceptanceCriteriaJson", "RequiredSkillsJson", "RequiredCertificationsJson"}},
                "acceptance_criteria": json.loads(item["AcceptanceCriteriaJson"] or "[]"),
                "required_skills": json.loads(item["RequiredSkillsJson"] or "[]"),
                "required_certifications": json.loads(item["RequiredCertificationsJson"] or "[]"),
            }
            for item in stories
        ],
        "tasks": [
            {
                **{key: value for key, value in dict(item).items()
                   if key not in {"RequiredSkillsJson", "RequiredCertificationsJson"}},
                "required_skills": json.loads(item["RequiredSkillsJson"] or "[]"),
                "required_certifications": json.loads(item["RequiredCertificationsJson"] or "[]"),
            }
            for item in tasks
        ],
        "sprints": [dict(item) for item in sprints],
    }


@router.post("/projects/{project_id}/backlog", status_code=201, dependencies=[_planning_permissions()])
def create_project_backlog(
    project_id: UUID,
    body: BacklogPlan,
    db: Session = Depends(get_db),
    actor=Depends(get_current_user),
):
    _require_visible_project(db, actor, project_id)
    project_exists = db.execute(text("""
        SELECT 1 FROM dbo.Project WHERE ProjectID=:project_id
    """), {"project_id": project_id}).scalar_one_or_none()
    if not project_exists:
        raise HTTPException(status_code=404, detail="Project not found")
    existing = db.execute(text("""
        SELECT 1 FROM dbo.ProjectEpic WHERE ProjectID=:project_id
    """), {"project_id": project_id}).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Project backlog already exists; edit individual plan records through the planning workflow")

    sprint_ids: dict[str, UUID] = {}
    for sprint in body.sprints:
        sprint_id = uuid.uuid4()
        sprint_ids[sprint.name.strip().casefold()] = sprint_id
        db.execute(text("""
            INSERT dbo.ProjectSprint
                (SprintID,ProjectID,SprintName,StartDate,EndDate,CapacityHours,Status,CreatedAtUtc,CreatedBy)
            VALUES
                (:id,:project_id,:name,:start,:end,:capacity,'Planned',SYSUTCDATETIME(),:actor)
        """), {
            "id": sprint_id, "project_id": project_id, "name": sprint.name.strip(),
            "start": sprint.start_date, "end": sprint.end_date,
            "capacity": sprint.capacity_hours, "actor": actor["sub"],
        })

    created = {"epics": 0, "features": 0, "stories": 0, "tasks": 0, "sprints": len(sprint_ids)}
    for epic_index, epic in enumerate(body.epics, start=1):
        epic_id = uuid.uuid4()
        db.execute(text("""
            INSERT dbo.ProjectEpic
                (EpicID,ProjectID,Title,Description,SequenceNumber,Status,CreatedAtUtc,CreatedBy)
            VALUES
                (:id,:project_id,:title,:description,:sequence,'Proposed',SYSUTCDATETIME(),:actor)
        """), {
            "id": epic_id, "project_id": project_id, "title": epic.title.strip(),
            "description": epic.description.strip(), "sequence": epic_index, "actor": actor["sub"],
        })
        created["epics"] += 1
        for feature_index, feature in enumerate(epic.features, start=1):
            feature_id = uuid.uuid4()
            db.execute(text("""
                INSERT dbo.ProjectFeature
                    (FeatureID,EpicID,Title,Description,SequenceNumber,Status,CreatedAtUtc,CreatedBy)
                VALUES
                    (:id,:epic_id,:title,:description,:sequence,'Proposed',SYSUTCDATETIME(),:actor)
            """), {
                "id": feature_id, "epic_id": epic_id, "title": feature.title.strip(),
                "description": feature.description.strip(), "sequence": feature_index, "actor": actor["sub"],
            })
            created["features"] += 1
            for story in feature.stories:
                story_id = uuid.uuid4()
                sprint_id = sprint_ids.get(story.sprint_name.strip().casefold()) if story.sprint_name else None
                db.execute(text("""
                    INSERT dbo.ProjectStory
                        (StoryID,FeatureID,SprintID,Title,Description,AcceptanceCriteriaJson,
                         RequiredSkillsJson,RequiredCertificationsJson,StoryPoints,Status,CreatedAtUtc,CreatedBy)
                    VALUES
                        (:id,:feature_id,:sprint_id,:title,:description,:criteria,:skills,:certifications,
                         :points,'Backlog',SYSUTCDATETIME(),:actor)
                """), {
                    "id": story_id, "feature_id": feature_id, "sprint_id": sprint_id,
                    "title": story.title.strip(), "description": story.description.strip(),
                    "criteria": json.dumps(story.acceptance_criteria, ensure_ascii=True),
                    "skills": json.dumps([item.model_dump() for item in story.required_skills], ensure_ascii=True),
                    "certifications": json.dumps(story.required_certifications, ensure_ascii=True),
                    "points": story.story_points, "actor": actor["sub"],
                })
                created["stories"] += 1
                for task in story.tasks:
                    db.execute(text("""
                        INSERT dbo.ProjectDeliveryTask
                            (ProjectTaskID,StoryID,Title,Description,RequiredSkillsJson,
                             RequiredCertificationsJson,EstimatedEffortHours,Status,CreatedAtUtc,CreatedBy)
                        VALUES
                            (:id,:story_id,:title,:description,:skills,:certifications,:hours,
                             'Planned',SYSUTCDATETIME(),:actor)
                    """), {
                        "id": uuid.uuid4(), "story_id": story_id,
                        "title": task.title.strip(), "description": task.description.strip(),
                        "skills": json.dumps([item.model_dump() for item in task.required_skills], ensure_ascii=True),
                        "certifications": json.dumps(task.required_certifications, ensure_ascii=True),
                        "hours": task.estimated_effort_hours, "actor": actor["sub"],
                    })
                    created["tasks"] += 1
    _audit(db, actor, "ProjectBacklogCreated", "Project", str(project_id), {
        **created,
        "automatic_assignment_enabled": False,
    })
    db.commit()
    return {
        "project_id": str(project_id),
        **created,
        "automatic_assignment_enabled": False,
        "manager_approval_required_before_assignment": True,
    }
