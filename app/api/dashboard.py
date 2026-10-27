from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.security.dependencies import get_current_user
from app.services.security_service import SecurityService
from app.security.permissions import require_roles

from sqlalchemy import text

router = APIRouter(prefix="/dashboard/api", tags=["Dashboard"])


def _owned_dashboard_records(db: Session, owner_id):
    requirements = db.execute(
        text("SELECT * FROM Requirement WHERE CreatedByUserID=:owner_id"),
        {"owner_id": str(owner_id)},
    ).mappings().all()
    projects = db.execute(
        text("SELECT p.ProjectID FROM Project p JOIN Requirement r ON r.RequirementID=p.RequirementID WHERE p.CreatedByUserID=:owner_id AND r.CreatedByUserID=:owner_id"),
        {"owner_id": str(owner_id)},
    ).mappings().all()
    tasks = db.execute(
        text("SELECT t.TaskID FROM Task t JOIN Project p ON p.ProjectID=t.ProjectID JOIN Requirement r ON r.RequirementID=p.RequirementID WHERE t.CreatedByUserID=:owner_id AND p.CreatedByUserID=:owner_id AND r.CreatedByUserID=:owner_id"),
        {"owner_id": str(owner_id)},
    ).mappings().all()
    notifications = db.execute(
        text("SELECT * FROM Notification WHERE UserID=:user_id"),
        {"user_id": owner_id},
    ).mappings().all()
    approvals = db.execute(
        text("SELECT a.ApprovalID FROM Approval a JOIN Requirement r ON r.RequirementID=a.RequirementID WHERE a.AssignedToUserID=:user_id OR r.CreatedByUserID=:owner_id"),
        {"user_id": owner_id, "owner_id": str(owner_id)},
    ).mappings().all()
    assessments = db.execute(
        text("SELECT COUNT(*) AS total FROM RequirementAssessment x JOIN Requirement r ON r.RequirementID=x.RequirementID WHERE r.CreatedByUserID=:user_id"),
        {"user_id": owner_id},
    ).scalar_one()

    return {
        "my_requirements": requirements,
        "my_projects": projects,
        "my_tasks": tasks,
        "my_notifications": notifications,
        "my_approvals": approvals,
        "my_assessments": int(assessments or 0),
    }


def my_dashboard(db: Session, user: dict):
    owner_id = user["sub"]
    records = _owned_dashboard_records(db, owner_id)
    return {
        **records,
        "requirements": len(records["my_requirements"]),
        "projects": len(records["my_projects"]),
        "tasks": len(records["my_tasks"]),
        "notifications": len(records["my_notifications"]),
        "approvals": len(records["my_approvals"]),
        "assessments": records["my_assessments"],
        "visibility_scope": "personal" if user["role"] == "USER" else user["role"].lower(),
    }


@router.get("")
def dashboard(db: Session = Depends(get_db), user=Depends(get_current_user)):
    security = SecurityService(db)
    summary = security.GetVisibleSummary(user)
    notifications = security.GetVisibleNotifications(user)
    return {
        **summary,
        "notifications": len(notifications),
        "my_notifications": notifications,
        "visibility_scope": user["role"].lower(),
    }


@router.get("/me")
def my_dashboard_route(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return my_dashboard(db, user)


def _grouped_rows(db, query, params):
    return [dict(row) for row in db.execute(text(query), params).mappings().all()]


@router.get("/executive/{view}")
def executive_dashboard(
    view: str,
    db: Session = Depends(get_db),
    user=Depends(require_roles("EXECUTIVE", "PLATFORM_OWNER")),
):
    view = view.lower()
    if view not in {"ceo", "coo", "cio"}:
        raise HTTPException(status_code=404, detail="Executive dashboard view not found")

    params = {}
    owner_scope = "1=1"

    if view == "ceo":
        sections = {
            "projects": _grouped_rows(db, f"""
                SELECT p.Status,COUNT(*) AS RecordCount FROM dbo.Project p
                JOIN dbo.Requirement r ON r.RequirementID=p.RequirementID
                WHERE {owner_scope} GROUP BY p.Status ORDER BY p.Status
            """, params),
            "approvals": _grouped_rows(db, f"""
                SELECT a.Status,COUNT(*) AS RecordCount FROM dbo.Approval a
                JOIN dbo.Requirement r ON r.RequirementID=a.RequirementID
                WHERE {owner_scope} GROUP BY a.Status ORDER BY a.Status
            """, params),
            "budgets": _grouped_rows(db, """
                SELECT b.Currency,SUM(b.Amount) AS ApprovedAmount,SUM(b.ConsumedAmount) AS ConsumedAmount
                FROM dbo.Budget b
                WHERE b.ProjectID IN (SELECT p.ProjectID FROM dbo.Project p JOIN dbo.Requirement r ON r.RequirementID=p.RequirementID WHERE """ + owner_scope + """)
                GROUP BY b.Currency ORDER BY b.Currency
            """, params),
            "risks": _grouped_rows(db, f"""
                SELECT x.RiskLevel,x.Status,COUNT(*) AS RecordCount FROM dbo.Risk x
                JOIN dbo.Project p ON p.ProjectID=x.ProjectID
                JOIN dbo.Requirement r ON r.RequirementID=p.RequirementID
                WHERE {owner_scope} GROUP BY x.RiskLevel,x.Status ORDER BY x.RiskLevel,x.Status
            """, params),
            "delivery_status": _grouped_rows(db, f"""
                SELECT t.Status,COUNT(*) AS RecordCount FROM dbo.Task t
                JOIN dbo.Project p ON p.ProjectID=t.ProjectID
                JOIN dbo.Requirement r ON r.RequirementID=p.RequirementID
                WHERE {owner_scope} GROUP BY t.Status ORDER BY t.Status
            """, params),
        }
    elif view == "coo":
        sections = {
            "tasks": _grouped_rows(db, f"""
                SELECT t.Status,COUNT(*) AS RecordCount FROM dbo.Task t
                JOIN dbo.Project p ON p.ProjectID=t.ProjectID
                JOIN dbo.Requirement r ON r.RequirementID=p.RequirementID
                WHERE {owner_scope} GROUP BY t.Status ORDER BY t.Status
            """, params),
            "assignments": _grouped_rows(db, f"""
                SELECT ta.Status,COUNT(*) AS RecordCount FROM dbo.TaskAssignment ta
                JOIN dbo.Task t ON t.TaskID=ta.TaskID
                JOIN dbo.Project p ON p.ProjectID=t.ProjectID
                JOIN dbo.Requirement r ON r.RequirementID=p.RequirementID
                WHERE {owner_scope} GROUP BY ta.Status ORDER BY ta.Status
            """, params),
            "queue": _grouped_rows(db, f"""
                SELECT q.Status,COUNT(*) AS RecordCount FROM dbo.AgentTaskQueue q
                JOIN dbo.Agent a ON a.AgentID=q.AgentID
                JOIN dbo.Task t ON t.TaskID=q.TaskID
                JOIN dbo.Project p ON p.ProjectID=t.ProjectID
                JOIN dbo.Requirement r ON r.RequirementID=p.RequirementID
                WHERE {owner_scope} GROUP BY q.Status ORDER BY q.Status
            """, params),
            "executions": _grouped_rows(db, f"""
                SELECT e.Status,COUNT(*) AS RecordCount FROM dbo.AgentExecution e
                JOIN dbo.Agent a ON a.AgentID=e.AgentID
                JOIN dbo.Task t ON t.TaskID=e.TaskID
                JOIN dbo.Project p ON p.ProjectID=t.ProjectID
                JOIN dbo.Requirement r ON r.RequirementID=p.RequirementID
                WHERE {owner_scope} GROUP BY e.Status ORDER BY e.Status
            """, params),
            "capacity": _grouped_rows(db, """
                SELECT a.Status,COUNT(*) AS AgentCount,AVG(CONVERT(float,a.CurrentWorkload)) AS AverageWorkload
                FROM dbo.Agent a GROUP BY a.Status ORDER BY a.Status
            """, params),
        }
    else:
        sections = {
            "agents": _grouped_rows(db, """
                SELECT a.Status,a.ModelProvider,a.Model,COUNT(*) AS RecordCount
                FROM dbo.Agent a
                GROUP BY a.Status,a.ModelProvider,a.Model ORDER BY a.Status,a.ModelProvider,a.Model
            """, params),
            "runtime_queue": _grouped_rows(db, """
                SELECT q.Status,COUNT(*) AS RecordCount FROM dbo.AgentTaskQueue q
                JOIN dbo.Agent a ON a.AgentID=q.AgentID
                GROUP BY q.Status ORDER BY q.Status
            """, params),
            "runtime_executions": _grouped_rows(db, """
                SELECT e.Status,COUNT(*) AS RecordCount FROM dbo.AgentExecution e
                JOIN dbo.Agent a ON a.AgentID=e.AgentID
                GROUP BY e.Status ORDER BY e.Status
            """, params),
            "costs": _grouped_rows(db, """
                SELECT c.Currency,SUM(c.TotalCost) AS TotalCost,COUNT(*) AS RecordCount
                FROM dbo.AgentCost c JOIN dbo.Agent a ON a.AgentID=c.AgentID
                GROUP BY c.Currency ORDER BY c.Currency
            """, params),
            "incidents": _grouped_rows(db, """
                SELECT i.Severity,i.Status,COUNT(*) AS RecordCount FROM dbo.SecurityIncident i
                LEFT JOIN dbo.Agent a ON a.AgentID=i.AgentID
                LEFT JOIN dbo.Project p ON p.ProjectID=i.ProjectID
                LEFT JOIN dbo.Requirement r ON r.RequirementID=p.RequirementID
                WHERE """ + owner_scope + """
                GROUP BY i.Severity,i.Status ORDER BY i.Severity,i.Status
            """, params),
            "evaluations": _grouped_rows(db, """
                SELECT e.EvaluationType,e.Passed,COUNT(*) AS RecordCount
                FROM dbo.Evaluation e JOIN dbo.Agent a ON a.AgentID=e.AgentID
                GROUP BY e.EvaluationType,e.Passed
                ORDER BY e.EvaluationType,e.Passed
            """, params),
        }

    return {
        "view": view,
        "organization_scope": "single_organization",
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "sections": sections,
    }
