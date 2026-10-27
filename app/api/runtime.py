import uuid
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.security.permissions import require_roles
from app.services.agent_runtime import (
    _execution_gate,
    _runtime_event,
    claim_next_task,
    enqueue_ready_tasks,
    fail_execution,
    hash_worker_token,
    heartbeat_execution,
    make_worker_token,
    reap_expired_leases,
    review_execution,
    submit_output,
    worker_token_matches,
)

router = APIRouter(prefix="/runtime", tags=["Agent Runtime"])
ADMIN_ROLES = ("ADMIN", "OWNER", "SUPER_ADMIN")
OWNER_ROLES = ("OWNER", "SUPER_ADMIN")


class ReviewRequest(BaseModel):
    passed: bool
    reason: str = Field(min_length=5, max_length=2000)
    severity: Literal["Low", "Medium", "High", "Critical"] = "High"
    priority: Literal["Low", "Medium", "High", "Critical"] = "High"
    root_cause: str | None = Field(default=None, max_length=1000)
    business_impact: str | None = Field(default=None, max_length=1000)
    technical_impact: str | None = Field(default=None, max_length=1000)
    fix_recommendation: str | None = Field(default=None, max_length=1000)
    assigned_role_code: str | None = Field(default=None, max_length=60)


class EscalationResolution(BaseModel):
    action: Literal["resolve", "requeue"]
    reason: str = Field(min_length=5, max_length=2000)


class OutputRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    content_type: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=500_000)


class FailureRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


def _worker_agent(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    scheme, separator, token = (authorization or "").partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Agent runtime bearer token required")
    token_hash = hash_worker_token(token)
    credential = db.execute(text("""
        SELECT c.AgentID,c.TokenHash
        FROM AgentRuntimeCredential c JOIN Agent a ON a.AgentID=c.AgentID
        WHERE c.TokenHash=:token_hash AND c.Status='Active' AND a.Status='Active'
    """), {"token_hash": token_hash}).mappings().first()
    if not credential or not worker_token_matches(token, credential["TokenHash"]):
        raise HTTPException(status_code=401, detail="Invalid or inactive agent runtime credential")
    db.execute(text("UPDATE AgentRuntimeCredential SET LastUsedAtUtc=:now WHERE AgentID=:agent_id"), {
        "now": datetime.now(timezone.utc).replace(tzinfo=None), "agent_id": credential["AgentID"],
    })
    return credential["AgentID"]


@router.post("/agents/{agent_id}/credential", dependencies=[Depends(require_roles(*OWNER_ROLES))])
def rotate_worker_credential(
    agent_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(require_roles(*OWNER_ROLES)),
):
    agent = db.execute(text("""
        SELECT AgentID,Status FROM Agent WITH (UPDLOCK,ROWLOCK) WHERE AgentID=:agent_id
    """), {"agent_id": agent_id}).mappings().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent["Status"] != "Active":
        raise HTTPException(status_code=409, detail="Only an Active agent may receive a runtime credential")
    token = make_worker_token()
    token_hash = hash_worker_token(token)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    existing = db.execute(text("SELECT AgentID FROM AgentRuntimeCredential WHERE AgentID=:agent_id"), {
        "agent_id": agent_id,
    }).first()
    if existing:
        db.execute(text("""
            UPDATE AgentRuntimeCredential SET TokenHash=:token_hash,Status='Active',RotatedAtUtc=:now,
                RevokedAtUtc=NULL,CreatedBy=:created_by
            WHERE AgentID=:agent_id
        """), {"token_hash": token_hash, "now": now, "created_by": user["sub"], "agent_id": agent_id})
    else:
        db.execute(text("""
            INSERT AgentRuntimeCredential(AgentID,TokenHash,Status,CreatedAtUtc,RotatedAtUtc,CreatedBy)
            VALUES(:agent_id,:token_hash,'Active',:now,:now,:created_by)
        """), {"agent_id": agent_id, "token_hash": token_hash, "now": now, "created_by": user["sub"]})
    _runtime_event(db, event_type="WorkerCredentialRotated", actor_type="User", actor_id=user["sub"],
                   severity="Warning", agent_id=agent_id, details={"one_time_secret_returned": True})
    db.commit()
    return {"agent_id": str(agent_id), "token": token, "warning": "Store this token securely; it is shown only once."}


@router.delete("/agents/{agent_id}/credential", dependencies=[Depends(require_roles(*OWNER_ROLES))])
def revoke_worker_credential(
    agent_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(require_roles(*OWNER_ROLES)),
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = db.execute(text("""
        UPDATE AgentRuntimeCredential SET Status='Revoked',RevokedAtUtc=:now
        WHERE AgentID=:agent_id AND Status='Active'
    """), {"now": now, "agent_id": agent_id})
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Active runtime credential not found")
    _runtime_event(db, event_type="WorkerCredentialRevoked", actor_type="User", actor_id=user["sub"],
                   severity="Warning", agent_id=agent_id, details={"credential_revoked": True})
    db.commit()
    return {"agent_id": str(agent_id), "credential_status": "Revoked"}


@router.post("/projects/{project_id}/enqueue", dependencies=[Depends(require_roles(*OWNER_ROLES))])
def enqueue_project_tasks(
    project_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(require_roles(*OWNER_ROLES)),
):
    if not db.execute(text("SELECT 1 FROM Project WHERE ProjectID=:project_id"), {
        "project_id": project_id,
    }).first():
        raise HTTPException(status_code=404, detail="Project not found")
    result = enqueue_ready_tasks(db, project_id, user["sub"])
    db.commit()
    return result


@router.get("/monitor", dependencies=[Depends(require_roles(*ADMIN_ROLES))])
def runtime_monitor(db: Session = Depends(get_db)):
    queue = db.execute(text("""
        SELECT Status,COUNT(*) AS Count FROM AgentTaskQueue GROUP BY Status ORDER BY Status
    """)).mappings().all()
    executions = db.execute(text("""
        SELECT Status,COUNT(*) AS Count FROM AgentExecution GROUP BY Status ORDER BY Status
    """)).mappings().all()
    open_escalations = db.execute(text("""
        SELECT COUNT(*) FROM AgentRuntimeEscalation WHERE Status='Open'
    """)).scalar_one()
    open_defects = db.execute(text("""
        SELECT COUNT(*) FROM AgentRuntimeDefect WHERE Status IN ('Open','InProgress','Retest','Escalated')
    """)).scalar_one()
    events = db.execute(text("""
        SELECT TOP 100 RuntimeEventID,ExecutionID,QueueID,TaskID,AgentID,EventType,Severity,
               ActorType,ActorID,Details,CreatedAtUtc
        FROM AgentRuntimeEvent ORDER BY CreatedAtUtc DESC
    """)).mappings().all()
    return {
        "queue": [dict(row) for row in queue],
        "executions": [dict(row) for row in executions],
        "open_escalations": int(open_escalations),
        "open_defects": int(open_defects),
        "recent_events": [dict(row) for row in events],
        "execution_adapter_configured": False,
    }


@router.get("/escalations", dependencies=[Depends(require_roles(*ADMIN_ROLES))])
def list_runtime_escalations(status: Literal["Open", "Resolved"] | None = None, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT e.EscalationID,e.QueueID,e.TaskID,e.AgentID,e.EscalationCode,e.Severity,e.Reason,
               e.Status,e.CreatedAtUtc,e.ResolvedAtUtc,e.ResolvedBy,e.Resolution,
               t.Description AS TaskDescription,a.AgentName
        FROM AgentRuntimeEscalation e JOIN Task t ON t.TaskID=e.TaskID
        JOIN Agent a ON a.AgentID=e.AgentID
        WHERE (:status IS NULL OR e.Status=:status)
        ORDER BY CASE WHEN e.Status='Open' THEN 0 ELSE 1 END,e.CreatedAtUtc DESC
    """), {"status": status}).mappings().all()
    return [dict(row) for row in rows]


@router.post("/escalations/{escalation_id}/resolve", dependencies=[Depends(require_roles(*OWNER_ROLES))])
def resolve_runtime_escalation(
    escalation_id: UUID,
    body: EscalationResolution,
    db: Session = Depends(get_db),
    user=Depends(require_roles(*OWNER_ROLES)),
):
    escalation = db.execute(text("""
        SELECT e.EscalationID,e.QueueID,e.TaskID,e.AgentID,e.Status
        FROM AgentRuntimeEscalation e WITH (UPDLOCK,ROWLOCK)
        WHERE e.EscalationID=:id
    """), {"id": escalation_id}).mappings().first()
    if not escalation:
        raise HTTPException(status_code=404, detail="Escalation not found")
    if escalation["Status"] != "Open":
        raise HTTPException(status_code=409, detail="Escalation is already resolved")
    if body.action == "requeue":
        db.execute(text("UPDATE Task SET Status='Planned' WHERE TaskID=:task_id AND Status='Blocked'"), {
            "task_id": escalation["TaskID"],
        })
        _agent, blockers = _execution_gate(db, escalation["TaskID"], escalation["AgentID"])
        if blockers:
            raise HTTPException(status_code=409, detail={"message": "Task remains gated", "blockers": blockers})
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.execute(text("""
            UPDATE AgentTaskQueue SET Status='Retry',AvailableAtUtc=:now,LastFailure=NULL,
                MaxAttempts=AttemptCount+3,EscalatedAtUtc=NULL,ModifiedAtUtc=:now WHERE QueueID=:queue_id
        """), {"now": now, "queue_id": escalation["QueueID"]})
        db.execute(text("UPDATE Task SET Status='Queued',ModifiedAtUtc=:now WHERE TaskID=:task_id"), {
            "now": now, "task_id": escalation["TaskID"],
        })
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.execute(text("""
        UPDATE AgentRuntimeEscalation SET Status='Resolved',ResolvedAtUtc=:now,
            ResolvedBy=:user_id,Resolution=:resolution WHERE EscalationID=:id
    """), {"now": now, "user_id": user["sub"], "resolution": body.reason.strip(), "id": escalation_id})
    _runtime_event(db, event_type="RuntimeEscalationResolved", actor_type="User", actor_id=user["sub"],
                   severity="Info", queue_id=escalation["QueueID"], task_id=escalation["TaskID"],
                   agent_id=escalation["AgentID"], details={"action": body.action, "reason": body.reason.strip()})
    db.commit()
    return {"escalation_id": str(escalation_id), "status": "Resolved", "action": body.action}


@router.get("/defects", dependencies=[Depends(require_roles(*ADMIN_ROLES))])
def list_runtime_defects(status: str | None = None, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT d.DefectID,d.ExecutionID,d.TaskID,d.AgentID,d.Severity,d.Priority,d.RootCause,
               d.BusinessImpact,d.TechnicalImpact,d.FixRecommendation,d.AssignedRoleCode,
               d.Status,d.CreatedAtUtc,d.ClosedAtUtc,t.Description AS TaskDescription,a.AgentName
        FROM AgentRuntimeDefect d JOIN Task t ON t.TaskID=d.TaskID JOIN Agent a ON a.AgentID=d.AgentID
        WHERE (:status IS NULL OR d.Status=:status)
        ORDER BY CASE WHEN d.Status IN ('Open','Escalated') THEN 0 ELSE 1 END,d.Priority DESC,d.CreatedAtUtc DESC
    """), {"status": status}).mappings().all()
    return [dict(row) for row in rows]


@router.post("/executions/{execution_id}/review", dependencies=[Depends(require_roles(*ADMIN_ROLES))])
def review_runtime_execution(
    execution_id: UUID,
    body: ReviewRequest,
    db: Session = Depends(get_db),
    user=Depends(require_roles(*ADMIN_ROLES)),
):
    defect = None
    if not body.passed:
        required = (body.root_cause, body.business_impact, body.technical_impact, body.fix_recommendation)
        if any(not value or not value.strip() for value in required):
            raise HTTPException(status_code=422, detail="Rejected output requires root cause, impacts, and fix recommendation")
        if body.assigned_role_code and not db.execute(text("""
            SELECT 1 FROM WorkforceRoleProfile WHERE RoleCode=:role_code AND Status='Active'
        """), {"role_code": body.assigned_role_code}).first():
            raise HTTPException(status_code=422, detail="Assigned remediation role is not an active role profile")
        defect = body.model_dump(exclude={"passed", "reason"})
    result = review_execution(db, execution_id, user["sub"], body.passed, body.reason, defect)
    db.commit()
    return result


@router.post("/worker/claim")
def worker_claim(agent_id: UUID = Depends(_worker_agent), db: Session = Depends(get_db)):
    result = claim_next_task(db, agent_id, agent_id)
    db.commit()
    return result


@router.post("/worker/executions/{execution_id}/heartbeat")
def worker_heartbeat(execution_id: UUID, agent_id: UUID = Depends(_worker_agent), db: Session = Depends(get_db)):
    result = heartbeat_execution(db, execution_id, agent_id)
    db.commit()
    return result


@router.post("/worker/executions/{execution_id}/output")
def worker_output(
    execution_id: UUID,
    body: OutputRequest,
    agent_id: UUID = Depends(_worker_agent),
    db: Session = Depends(get_db),
):
    result = submit_output(db, execution_id, agent_id, body.name, body.content_type,
                           body.content, agent_id)
    db.commit()
    return result


@router.post("/worker/executions/{execution_id}/failure")
def worker_failure(
    execution_id: UUID,
    body: FailureRequest,
    agent_id: UUID = Depends(_worker_agent),
    db: Session = Depends(get_db),
):
    result = fail_execution(db, execution_id, agent_id, body.reason)
    db.commit()
    return {"execution_id": str(execution_id), "status": result}


@router.post("/reap-expired-leases", dependencies=[Depends(require_roles(*OWNER_ROLES))])
def reap_leases(db: Session = Depends(get_db), user=Depends(require_roles(*OWNER_ROLES))):
    result = reap_expired_leases(db, user["sub"])
    db.commit()
    return result