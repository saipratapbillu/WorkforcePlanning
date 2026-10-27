import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import AppUser, Requirement, RequirementAssessment
from app.schemas.schemas import AssessmentRequest, AssessmentResponse, RequirementCreate, RequirementUpdate
from app.repositories.requirement_repository import RequirementRepository
from app.repositories.agent_repository import AgentRepository
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.audit_repository import AuditRepository
from app.services.assessment_provider import DeterministicAssessmentProvider
from app.services.policy_service import PolicyService
from app.services.ceo_orchestrator import CEOOrchestrator
from app.services.approval_service import ApprovalService
from app.services.project_factory import ProjectFactory
from app.security.dependencies import get_current_user
from app.security.roles import canonical_role
from app.services.security_service import SecurityService
from app.services.agent_factory import build_factory_blueprint, infer_technology_changes

router = APIRouter(prefix="/requirements", tags=["Requirements"])


def service():
    return CEOOrchestrator(
        RequirementRepository(), AgentRepository(), AssessmentRepository(),
        AuditRepository(), DeterministicAssessmentProvider(), PolicyService(),
        approval_service=ApprovalService(),
        project_factory=ProjectFactory(),
    )


def serialize_requirement(item: Requirement):
    if isinstance(item, dict):
        return {
            "requirement_id": str(item["RequirementID"]),
            "title": item["Title"],
            "description": item["Description"],
            "requested_by": item["RequestedBy"],
            "priority": item["Priority"],
            "risk_level": item["RiskLevel"],
            "status": item["Status"],
            "created_at_utc": item["CreatedAtUtc"],
            "created_by": str(item["CreatedByUserID"]) if item["CreatedByUserID"] else None,
            "modified_at_utc": item["ModifiedAtUtc"],
            "modified_by": item["ModifiedBy"],
        }
    return {
        "requirement_id": str(item.RequirementID),
        "title": item.Title,
        "description": item.Description,
        "requested_by": item.RequestedBy,
        "priority": item.Priority,
        "risk_level": item.RiskLevel,
        "status": item.Status,
        "created_at_utc": item.CreatedAtUtc,
        "created_by": item.CreatedBy,
        "modified_at_utc": item.ModifiedAtUtc,
        "modified_by": item.ModifiedBy,
    }


GLOBAL_REQUEST_ROLES = {"EXECUTIVE", "WORKFORCE_MANAGER", "PLATFORM_OWNER"}


def visible_requester_ids(db: Session, user: dict) -> set[str]:
    user_id = UUID(user["sub"])
    user_ids = [user_id]
    if canonical_role(user["role"]) == "WORKFORCE_MANAGER":
        direct_reports = db.execute(
            select(AppUser.UserID).where(
                AppUser.ManagerUserID == user_id,
                AppUser.IsActive == True,
            )
        ).scalars().all()
        user_ids.extend(direct_reports)
    return {str(user_id) for user_id in user_ids}


def can_access_requirement(item: Requirement, user: dict, db: Session) -> bool:
    if canonical_role(user["role"]) in GLOBAL_REQUEST_ROLES:
        return True
    owner_id = getattr(item, "CreatedByUserID", None)
    if owner_id is not None:
        return str(owner_id) == str(user["sub"])
    return item.CreatedBy in visible_requester_ids(db, user)


def _tracking_stage(status_value: str, has_assessment: bool, approvals: list, has_project: bool):
    normalized = (status_value or "Submitted").lower()
    if normalized in {"rejected", "notfeasible", "cancelled", "canceled"}:
        return "closed"
    if has_project:
        return "delivery"
    approval_statuses = [(approval.get("status") or "").lower() for approval in approvals]
    if "rejected" in approval_statuses:
        return "closed"
    if "pending" in approval_statuses:
        return "approval"
    if "approved" in approval_statuses or normalized == "approved":
        return "delivery"
    if normalized == "pendingapproval":
        return "approval"
    if has_assessment or normalized in {"assessed", "assessmentfailed", "approved", "informationrequired"}:
        return "assessment"
    return "intake"


def _planning_summary(required_skills: list[dict], projects: list[dict]) -> dict:
    total_effort = sum(float(skill["estimated_effort_hours"] or 0) for skill in required_skills)
    matched_skills = sum(1 for skill in required_skills if skill["qualified_active_agents"] > 0)
    task_count = sum(project["task_count"] for project in projects)
    assigned_task_count = sum(project["assigned_task_count"] for project in projects)
    open_workforce_requests = sum(project.get("open_workforce_request_count", 0) for project in projects)
    all_planned = bool(projects) and all(project["status"].lower() == "planned" for project in projects)

    if not projects:
        delivery_state = "not_created"
    elif all_planned and assigned_task_count == 0:
        delivery_state = "planned_unstaffed"
    elif all_planned:
        delivery_state = "planned_staffed"
    else:
        delivery_state = "active_or_mixed"

    return {
        "delivery_state": delivery_state,
        "estimated_skill_hours": total_effort,
        "indicative_person_days_at_8h": round(total_effort / 8, 1) if total_effort else None,
        "effort_estimate_basis": "Sum of persisted assessment effort only; task roles without an assessment estimate are excluded. 8 hours per person-day. Not a complete delivery-duration estimate.",
        "required_skill_count": len(required_skills),
        "skills_with_active_agent_coverage": matched_skills,
        "task_count": task_count,
        "assigned_task_count": assigned_task_count,
        "unestimated_task_count": sum(project.get("unestimated_task_count", 0) for project in projects),
        "open_workforce_request_count": open_workforce_requests,
        "skills": required_skills,
        "calendar_estimate_days": None,
    }


def _requirement_audit_history(db: Session, requirement_id: UUID):
        return db.execute(text("""
                SELECT audit.Action, audit.Outcome, audit.CreatedAtUtc
                FROM AuditLog audit
                WHERE audit.ResourceType = 'Requirement' AND audit.ResourceID = :requirement_id
                UNION ALL
                SELECT audit.Action, audit.Outcome, audit.CreatedAtUtc
                FROM AuditLog audit
                JOIN Approval approval
                    ON TRY_CONVERT(uniqueidentifier, audit.ResourceID) = approval.ApprovalID
                WHERE audit.ResourceType = 'Approval' AND approval.RequirementID = :requirement_id
                ORDER BY CreatedAtUtc ASC
        """), {"requirement_id": str(requirement_id)}).mappings().all()


@router.get("/{requirement_id}/tracking")
def track_requirement(
    requirement_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    item = db.get(Requirement, requirement_id)
    if not item or not can_access_requirement(item, user, db):
        raise HTTPException(status_code=404, detail="Requirement not found")

    assessment_rows = db.execute(
        select(RequirementAssessment)
        .where(RequirementAssessment.RequirementID == requirement_id)
        .order_by(RequirementAssessment.AssessmentVersion.desc())
    ).scalars().all()
    latest_assessment = assessment_rows[0] if assessment_rows else None

    approvals = db.execute(
        text("""
            SELECT ApprovalID, ApprovalStage, Status, Comments, CreatedAtUtc, ApprovedAtUtc
            FROM Approval
            WHERE RequirementID = :requirement_id
            ORDER BY CreatedAtUtc ASC
        """),
        {"requirement_id": requirement_id},
    ).mappings().all()
    approval_items = [
        {
            "approval_id": str(row["ApprovalID"]),
            "stage": row["ApprovalStage"],
            "status": row["Status"],
            "created_at_utc": row["CreatedAtUtc"],
            "decided_at_utc": row["ApprovedAtUtc"],
        }
        for row in approvals
    ]

    projects = db.execute(
        text("""
            SELECT p.ProjectID, p.ProjectName, p.Status, p.CreatedAtUtc,
                   (SELECT COUNT(*) FROM Task t WHERE t.ProjectID = p.ProjectID) AS TaskCount,
                     (SELECT COUNT(*) FROM Task t WHERE t.ProjectID = p.ProjectID AND t.AssignedAgentID IS NOT NULL) AS AssignedTaskCount,
                   (SELECT COUNT(*) FROM Task t WHERE t.ProjectID = p.ProjectID AND t.EstimatedEffortHours IS NULL) AS UnestimatedTaskCount,
                     (SELECT COUNT(*) FROM WorkforceRequest wr WHERE wr.ProjectID = p.ProjectID AND wr.Status IN ('PendingApproval','Recruiting','CandidateReady')) AS OpenWorkforceRequestCount
            FROM Project p
            WHERE p.RequirementID = :requirement_id
            ORDER BY p.CreatedAtUtc ASC
        """),
        {"requirement_id": requirement_id},
    ).mappings().all()

    project_tasks = {}
    for project in projects:
        task_rows = db.execute(text("""
            SELECT t.TaskID, t.PlannedSequence, t.Description, t.RequiredRoleCode,
                   t.EstimatedEffortHours, t.Status, a.AgentName
            FROM Task t LEFT JOIN Agent a ON a.AgentID=t.AssignedAgentID
            WHERE t.ProjectID=:project_id
            ORDER BY t.PlannedSequence, t.CreatedAtUtc
        """), {"project_id": project["ProjectID"]}).mappings().all()
        project_tasks[project["ProjectID"]] = [
            {
                "task_id": str(task["TaskID"]),
                "sequence": task["PlannedSequence"],
                "description": task["Description"],
                "required_role": task["RequiredRoleCode"],
                "estimated_effort_hours": float(task["EstimatedEffortHours"]) if task["EstimatedEffortHours"] is not None else None,
                "status": task["Status"],
                "assigned_agent": task["AgentName"],
            }
            for task in task_rows
        ]

    required_skills = db.execute(
        text("""
            SELECT s.Name AS SkillName, rs.EstimatedEffortHours,
                   COUNT(DISTINCT a.AgentID) AS QualifiedActiveAgents
            FROM RequirementSkill rs
            JOIN Skill s ON s.SkillID = rs.SkillID
            LEFT JOIN AgentSkill ags ON ags.SkillID = rs.SkillID AND ags.Status = 'Active'
                AND ags.Proficiency >= COALESCE(rs.MinimumProficiency, 1)
            LEFT JOIN Agent a ON a.AgentID = ags.AgentID AND a.Status = 'Active'
            WHERE rs.RequirementID = :requirement_id
            GROUP BY s.Name, rs.EstimatedEffortHours
            ORDER BY s.Name
        """),
        {"requirement_id": requirement_id},
    ).mappings().all()
    planning_summary = _planning_summary(
        [
            {
                "skill": row["SkillName"],
                "estimated_effort_hours": float(row["EstimatedEffortHours"] or 0),
                "qualified_active_agents": int(row["QualifiedActiveAgents"] or 0),
            }
            for row in required_skills
        ],
        [
            {
                "status": project["Status"],
                "task_count": int(project["TaskCount"] or 0),
                "assigned_task_count": int(project["AssignedTaskCount"] or 0),
                "unestimated_task_count": int(project["UnestimatedTaskCount"] or 0),
                "open_workforce_request_count": int(project["OpenWorkforceRequestCount"] or 0),
            }
            for project in projects
        ],
    )

    audit_rows = _requirement_audit_history(db, requirement_id)

    stage = _tracking_stage(item.Status, latest_assessment is not None, approval_items, bool(projects))
    approval_required = bool(latest_assessment and latest_assessment.HumanApprovalRequired)
    approved = any((approval["status"] or "").lower() == "approved" for approval in approval_items)
    if item.Status == "PendingApproval" and not approval_items:
        approval_state = "required_not_assigned"
    elif approval_items:
        approval_state = approval_items[-1]["status"].lower()
    elif approval_required and not approved:
        approval_state = "required_not_assigned"
    elif approved:
        approval_state = "approved"
    else:
        approval_state = "not_required_or_not_started"

    next_actions = {
        "intake": "Requirement submitted. Assessment has not been recorded yet.",
        "assessment": "Review the latest AI CEO assessment and any open questions.",
        "approval": "A human approval decision is required before delivery can start.",
        "delivery": "Project delivery is in progress. Follow project milestones for execution details.",
        "closed": "This request is closed. Review its final status and history.",
    }
    if item.Status == "PendingApproval" and not approval_items:
        next_action = "Approval is required, but no approval record is assigned yet. Contact the platform administrator."
    elif item.Status == "Approved" and not projects:
        next_action = "Approved, but project creation is not connected yet. Contact the platform administrator."
    elif planning_summary["delivery_state"] == "planned_unstaffed":
        uncovered_skills = [skill["skill"] for skill in planning_summary["skills"] if not skill["qualified_active_agents"]]
        coverage = (
            f"No active agents match these required skills: {', '.join(uncovered_skills)}. "
            if uncovered_skills else "No tasks have an assigned agent. "
        )
        next_action = (
            f"The project is Planned; development has not started. {coverage}"
            "A calendar timeline needs qualified resource availability, a target start date, and task-level estimates."
        )
        if planning_summary["open_workforce_request_count"]:
            next_action += f" {planning_summary['open_workforce_request_count']} role request(s) are awaiting governance review in Workforce Planning."
    elif planning_summary["delivery_state"] == "planned_staffed":
        next_action = "Qualified agents are assigned, but project work has not started. The Delivery Lead must confirm the plan and start date."
    else:
        next_action = next_actions[stage]

    stages = [
        {"key": "intake", "label": "Request submitted", "state": "completed", "at_utc": item.CreatedAtUtc},
        {
            "key": "assessment", "label": "AI CEO assessment",
            "state": "completed" if latest_assessment else ("current" if stage == "assessment" else "upcoming"),
            "at_utc": latest_assessment.CreatedAtUtc if latest_assessment else None,
            "summary": latest_assessment.ExecutiveSummary if latest_assessment else None,
            "version": latest_assessment.AssessmentVersion if latest_assessment else None,
        },
        {
            "key": "approval", "label": "Human approval",
            "state": "completed" if approval_state == "approved" else ("blocked" if approval_state == "rejected" else ("current" if stage == "approval" else ("not_assigned" if approval_state == "required_not_assigned" else "upcoming"))),
            "approval_status": approval_state,
            "items": approval_items,
        },
        {
            "key": "delivery",
            "label": "Project planning" if planning_summary["delivery_state"] in {"planned_unstaffed", "planned_staffed"} else "Project delivery",
            "state": "completed" if projects and all(project["Status"].lower() in {"completed", "closed"} for project in projects) else ("current" if stage == "delivery" else "upcoming"),
            "projects": [{"project_id": str(project["ProjectID"]), "name": project["ProjectName"], "status": project["Status"], "created_at_utc": project["CreatedAtUtc"], "task_count": int(project["TaskCount"] or 0), "assigned_task_count": int(project["AssignedTaskCount"] or 0), "unestimated_task_count": int(project["UnestimatedTaskCount"] or 0), "open_workforce_request_count": int(project["OpenWorkforceRequestCount"] or 0), "tasks": project_tasks[project["ProjectID"]]} for project in projects],
        },
    ]

    return {
        "requirement": serialize_requirement(item),
        "current_stage": stage,
        "next_action": next_action,
        "approval_required": approval_required,
        "planning": planning_summary,
        "latest_assessment": {
            "assessment_id": str(latest_assessment.RequirementAssessmentID),
            "status": latest_assessment.AssessmentStatus,
            "risk_level": latest_assessment.RiskLevel,
            "feasibility": latest_assessment.Feasibility,
            "created_at_utc": latest_assessment.CreatedAtUtc,
            "version": latest_assessment.AssessmentVersion,
        } if latest_assessment else None,
        "stages": stages,
        "history": [
            {"action": row["Action"], "outcome": row["Outcome"], "at_utc": row["CreatedAtUtc"]}
            for row in audit_rows
        ],
    }


@router.get("")
def list_requirements(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return [serialize_requirement(row) for row in SecurityService(db).GetVisibleRequirements(user)]


@router.get("/{requirement_id}")
def get_requirement(requirement_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    visible = SecurityService(db).GetVisibleRequirements(user, requirement_id)
    if not visible:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return serialize_requirement(visible[0])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_requirement(body: RequirementCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    item = Requirement(
        RequirementID=uuid.uuid4(),
        Title=body.title.strip(),
        Description=body.description.strip(),
        RequestedBy=user["name"],
        Priority=body.priority,
        RiskLevel="Low",
        Status="Submitted",
        CreatedAtUtc=now,
        CreatedBy=user["sub"],
        CreatedByUserID=UUID(user["sub"]),
        ModifiedAtUtc=now,
        ModifiedBy=user["sub"],
    )
    technology_changes = infer_technology_changes(f"{item.Title}\n{item.Description}")
    workforce_blueprint = build_factory_blueprint(
        title=item.Title,
        description=item.Description,
        technology_changes=technology_changes,
        priority=item.Priority,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    response = serialize_requirement(item)
    response["workforce_blueprint"] = workforce_blueprint
    return response


@router.put("/{requirement_id}")
def update_requirement(
    requirement_id: UUID,
    body: RequirementUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if not SecurityService(db).GetVisibleRequirements(user, requirement_id):
        raise HTTPException(status_code=404, detail="Requirement not found")
    item = db.get(Requirement, requirement_id)
    if not item:
        raise HTTPException(status_code=404, detail="Requirement not found")
    if item.Status not in {"Submitted", "Assessed", "AssessmentFailed", "InformationRequired"}:
        raise HTTPException(
            status_code=409,
            detail=f"Requirement cannot be edited while status is {item.Status}",
        )
    changes = body.model_dump(exclude_unset=True)
    field_map = {
        "title": "Title", "description": "Description", "requested_by": "RequestedBy",
        "priority": "Priority"
    }
    for source, target in field_map.items():
        if source in changes:
            value = changes[source]
            setattr(item, target, value.strip() if isinstance(value, str) else value)
    item.ModifiedAtUtc = datetime.now(timezone.utc)
    item.ModifiedBy = user["sub"]
    db.commit()
    db.refresh(item)
    return serialize_requirement(item)


@router.post("/{requirement_id}/assess", response_model=AssessmentResponse)
def assess_requirement(
    requirement_id: UUID,
    body: AssessmentRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if not SecurityService(db).GetVisibleRequirements(user, requirement_id):
        raise HTTPException(status_code=404, detail="Requirement not found")
    requirement = db.get(Requirement, requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")
    row, result = service().assess(
        db, requirement_id, user["name"], body.force_reassessment
    )
    return AssessmentResponse(
        requirement_id=requirement_id,
        assessment_id=row.RequirementAssessmentID,
        correlation_id=row.CorrelationID,
        status="Assessed",
        assessment=result,
    )
