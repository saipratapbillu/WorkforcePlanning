import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import text


MAX_OUTPUT_CHARS = 500_000
LEASE_MINUTES = 10
MAX_ATTEMPTS = 3
REVIEW_LEASE_MINUTES = 5
MAX_REVIEW_ATTEMPTS = 3


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def can_retry(attempt_count: int, max_attempts: int) -> bool:
    return attempt_count < max_attempts


def structural_output_passes(name: str, content: str) -> bool:
    return bool(name.strip()) and bool(content.strip()) and len(content) <= MAX_OUTPUT_CHARS


def hash_worker_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def worker_token_matches(token: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_worker_token(token), expected_hash)


def make_worker_token() -> str:
    return secrets.token_urlsafe(48)


def retry_available(attempt_count: int, max_attempts: int) -> bool:
    return attempt_count < max_attempts


def _runtime_event(db, *, event_type, actor_type, actor_id, severity="Info", execution_id=None,
                   queue_id=None, task_id=None, agent_id=None, details=None):
    correlation_id = uuid.uuid4()
    payload = json.dumps(details or {}, ensure_ascii=True)
    db.execute(text("""
        INSERT AgentRuntimeEvent
            (RuntimeEventID,ExecutionID,QueueID,TaskID,AgentID,EventType,Severity,ActorType,ActorID,Details,CreatedAtUtc)
        VALUES(:event_id,:execution_id,:queue_id,:task_id,:agent_id,:event_type,:severity,
               :actor_type,:actor_id,:details,:created_at)
    """), {
        "event_id": uuid.uuid4(), "execution_id": execution_id, "queue_id": queue_id,
        "task_id": task_id, "agent_id": agent_id, "event_type": event_type,
        "severity": severity, "actor_type": actor_type, "actor_id": str(actor_id),
        "details": payload, "created_at": utcnow(),
    })
    db.execute(text("""
        INSERT AuditLog(CorrelationID,ActorType,ActorID,Action,ResourceType,ResourceID,Outcome,Details)
        VALUES(:correlation,'Runtime',:actor,:action,:resource_type,:resource_id,:outcome,:details)
    """), {
        "correlation": correlation_id, "actor": str(actor_id), "action": event_type,
        "resource_type": "AgentExecution" if execution_id else "AgentTaskQueue",
        "resource_id": str(execution_id or queue_id or task_id or agent_id),
        "outcome": severity, "details": payload,
    })


def _execution_gate(db, task_id, agent_id):
    agent = db.execute(text("""
        SELECT AgentID,Status,ModelProvider,Model,ModelVersion,CompanyID
        FROM Agent WHERE AgentID=:agent_id
    """), {"agent_id": agent_id}).mappings().first()
    if not agent or agent["Status"] != "Active":
        return None, ["Agent must be Active"]
    if any(not agent[field] or agent[field] == "UNCONFIGURED" for field in ("ModelProvider", "Model", "ModelVersion")):
        return agent, ["Approved provider/model/version must be configured"]
    capacity = db.execute(text("SELECT ConcurrentTaskLimit,CurrentWorkload FROM Agent WHERE AgentID=:agent_id"), {
        "agent_id": agent_id,
    }).mappings().first()
    active_assignments = db.execute(text("""
        SELECT COUNT(*) FROM TaskAssignment
        WHERE AgentID=:agent_id AND Status='Active' AND ReleasedAtUtc IS NULL
    """), {"agent_id": agent_id}).scalar_one()
    if int(active_assignments) > int(capacity["ConcurrentTaskLimit"] or 1):
        return agent, ["Agent concurrency capacity is exceeded"]
    if float(capacity["CurrentWorkload"] or 0) >= 100:
        return agent, ["Agent workload is at or above 100 percent"]

    from app.services.workforce_planner import WorkforcePlanner
    passed = WorkforcePlanner.latest_passed_evaluation_types(db, agent_id)
    missing = {"Capability", "Safety", "Security", "Governance"} - passed
    if missing:
        return agent, ["Required agent evaluations missing: " + ", ".join(sorted(missing))]

    blocker = db.execute(text("""
        SELECT TOP 1 BlockerCode FROM AgentActivationBlocker
        WHERE AgentID=:agent_id AND Status='Open'
    """), {"agent_id": agent_id}).first()
    if blocker:
        return agent, [f"Open activation blocker: {blocker[0]}"]

    task = db.execute(text("""
         SELECT t.TaskID,t.ProjectID,t.Status,t.AssignedAgentID,t.RiskLevel,t.RequiredRoleCode,
             p.Status AS ProjectStatus,p.RequirementID,r.Status AS RequirementStatus
        FROM Task t JOIN Project p ON p.ProjectID=t.ProjectID
        JOIN Requirement r ON r.RequirementID=p.RequirementID
        WHERE t.TaskID=:task_id
    """), {"task_id": task_id}).mappings().first()
    if not task:
        return agent, ["Task not found"]
    if task["AssignedAgentID"] != agent_id:
        return agent, ["Agent is not assigned to this task"]
    assignment = db.execute(text("""
        SELECT 1 FROM TaskAssignment
        WHERE TaskID=:task_id AND AgentID=:agent_id AND Status='Active' AND ReleasedAtUtc IS NULL
    """), {"task_id": task_id, "agent_id": agent_id}).first()
    if not assignment:
        return agent, ["Agent has no active assignment for this task"]
    if task["Status"] not in {"Planned", "Queued"}:
        return agent, [f"Task is not queueable from status {task['Status']}"]
    if task["RequirementStatus"] != "Approved":
        return agent, ["Requirement is not Approved"]
    approval_required = db.execute(text("""
        SELECT TOP 1 HumanApprovalRequired FROM RequirementAssessment
        WHERE RequirementID=:requirement_id ORDER BY AssessmentVersion DESC
    """), {"requirement_id": task["RequirementID"]}).scalar_one_or_none()
    if approval_required and not db.execute(text("""
        SELECT 1 FROM Approval WHERE RequirementID=:requirement_id AND Status='Approved'
    """), {"requirement_id": task["RequirementID"]}).first():
        return agent, ["Required human approval is not recorded as Approved"]
    if task["ProjectStatus"] not in {"Planned", "InProgress"}:
        return agent, [f"Project is not runnable from status {task['ProjectStatus']}"]

    incomplete_dependency = db.execute(text("""
        SELECT TOP 1 prerequisite.TaskID
        FROM TaskDependency d JOIN Task prerequisite ON prerequisite.TaskID=d.DependsOnTaskID
        WHERE d.TaskID=:task_id AND prerequisite.Status<>'Completed'
    """), {"task_id": task_id}).first()
    if incomplete_dependency:
        return agent, ["A task dependency is not Completed"]

    delivery_lead = db.execute(text("""
        SELECT TOP 1 a.AgentID FROM ProjectAgent pa JOIN Agent a ON a.AgentID=pa.AgentID
        WHERE pa.ProjectID=:project_id AND pa.ProjectRole='Delivery Lead' AND a.Status='Active'
    """), {"project_id": task["ProjectID"]}).first()
    if not delivery_lead:
        return agent, ["Project has no Active Delivery Lead"]

    role_profile = db.execute(text("""
        SELECT RequiredSkillsJson FROM WorkforceRoleProfile
        WHERE RoleCode=:role_code AND Status='Active'
    """), {"role_code": task["RequiredRoleCode"]}).mappings().first()
    if not role_profile:
        return agent, ["Task required role profile is missing"]
    active_skills = {
        row["Name"]: int(row["Proficiency"])
        for row in db.execute(text("""
            SELECT s.Name,MAX(ags.Proficiency) AS Proficiency
            FROM AgentSkill ags JOIN Skill s ON s.SkillID=ags.SkillID
            WHERE ags.AgentID=:agent_id AND ags.Status='Active'
            GROUP BY s.Name
        """), {"agent_id": agent_id}).mappings().all()
    }
    from app.services.workforce_planner import agent_meets_profile
    if not agent_meets_profile(dict(role_profile), active_skills):
        return agent, ["Agent does not meet the task role's active skill thresholds"]

    if task["RiskLevel"] in {"High", "Critical"}:
        security_eval = db.execute(text("""
                        SELECT TOP 1 EvaluationID FROM Evaluation
                        WHERE AgentID=:agent_id AND TaskID=:task_id AND EvaluationType='Security' AND Passed=1
                            AND NOT EXISTS (
                                    SELECT 1 FROM Evaluation newer
                                    WHERE newer.AgentID=Evaluation.AgentID AND newer.TaskID=Evaluation.TaskID
                                        AND newer.EvaluationType=Evaluation.EvaluationType
                                        AND (newer.CreatedAtUtc>Evaluation.CreatedAtUtc
                                                 OR (newer.CreatedAtUtc=Evaluation.CreatedAtUtc AND newer.EvaluationID>Evaluation.EvaluationID))
                            )
                        ORDER BY CreatedAtUtc DESC,EvaluationID DESC
        """), {"agent_id": agent_id, "task_id": task_id}).first()
        if not security_eval:
            return agent, ["High-risk task lacks task-scoped Security approval/evaluation"]

    return agent, []


def queue_pending_tasks(db, project_id, actor_id):
    rows = db.execute(text("""
        SELECT t.TaskID,t.AssignedAgentID,t.Status
        FROM Task t
        WHERE t.ProjectID=:project_id AND t.Status='Planned' AND t.AssignedAgentID IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM TaskDependency d JOIN Task prerequisite ON prerequisite.TaskID=d.DependsOnTaskID
              WHERE d.TaskID=t.TaskID AND prerequisite.Status<>'Completed'
          )
    """), {"project_id": project_id}).mappings().all()
    queued = 0
    blocked = 0
    for row in rows:
        _agent, blockers = _execution_gate(db, row["TaskID"], row["AssignedAgentID"])
        existing = db.execute(text("SELECT QueueID,Status FROM AgentTaskQueue WHERE TaskID=:task_id"), {
            "task_id": row["TaskID"],
        }).mappings().first()
        if blockers:
            blocked += 1
            now = utcnow()
            reason = "; ".join(blockers)[:2000]
            if existing:
                queue_id = existing["QueueID"]
                db.execute(text("""
                    UPDATE AgentTaskQueue SET Status='Escalated',LastFailure=:reason,LeaseOwner=NULL,
                        LeaseExpiresAtUtc=NULL,EscalatedAtUtc=:now,ModifiedAtUtc=:now WHERE QueueID=:queue_id
                """), {"reason": reason, "now": now, "queue_id": queue_id})
            else:
                queue_id = uuid.uuid4()
                db.execute(text("""
                    INSERT AgentTaskQueue
                        (QueueID,TaskID,AgentID,Status,AttemptCount,MaxAttempts,AvailableAtUtc,LastFailure,
                         EscalatedAtUtc,CreatedAtUtc,ModifiedAtUtc)
                    VALUES(:queue_id,:task_id,:agent_id,'Escalated',0,:max_attempts,:now,:reason,:now,:now,:now)
                """), {"queue_id": queue_id, "task_id": row["TaskID"],
                      "agent_id": row["AssignedAgentID"], "max_attempts": MAX_ATTEMPTS,
                      "reason": reason, "now": now})
            db.execute(text("UPDATE Task SET Status='Blocked',ModifiedAtUtc=:now WHERE TaskID=:task_id"), {
                "now": now, "task_id": row["TaskID"],
            })
            _create_escalation(db, {"QueueID": queue_id, "TaskID": row["TaskID"]},
                               row["AssignedAgentID"], "EXECUTION_GATE_BLOCKED", reason, actor_id)
            _runtime_event(db, event_type="ExecutionBlocked", actor_type="System", actor_id=actor_id,
                           severity="Blocked", queue_id=queue_id, task_id=row["TaskID"],
                           agent_id=row["AssignedAgentID"], details={"blockers": blockers})
            continue
        now = utcnow()
        if existing:
            if existing["Status"] not in {"Retry", "Failed"}:
                continue
            db.execute(text("""
                UPDATE AgentTaskQueue SET AgentID=:agent_id,Status='Queued',AvailableAtUtc=:now,
                    LeaseOwner=NULL,LeaseExpiresAtUtc=NULL,LastFailure=NULL,ModifiedAtUtc=:now
                WHERE QueueID=:queue_id
            """), {"agent_id": row["AssignedAgentID"], "now": now, "queue_id": existing["QueueID"]})
            queue_id = existing["QueueID"]
        else:
            queue_id = uuid.uuid4()
            db.execute(text("""
                INSERT AgentTaskQueue
                    (QueueID,TaskID,AgentID,Status,AttemptCount,MaxAttempts,AvailableAtUtc,CreatedAtUtc,ModifiedAtUtc)
                VALUES(:queue_id,:task_id,:agent_id,'Queued',0,:max_attempts,:now,:now,:now)
            """), {"queue_id": queue_id, "task_id": row["TaskID"], "agent_id": row["AssignedAgentID"], "max_attempts": MAX_ATTEMPTS, "now": now})
        db.execute(text("UPDATE Task SET Status='Queued' WHERE TaskID=:task_id AND Status='Planned'"), {"task_id": row["TaskID"]})
        _runtime_event(db, event_type="TaskQueued", actor_type="System", actor_id=actor_id,
                       severity="Info", queue_id=queue_id, task_id=row["TaskID"],
                       agent_id=row["AssignedAgentID"], details={"blockers": []})
        queued += 1
    return {"queued_count": queued, "blocked_count": blocked, "candidate_count": len(rows)}


def enqueue_ready_tasks(db, project_id, actor_id):
    return queue_pending_tasks(db, project_id, actor_id)


def claim_next_task(db, agent_id, actor_id):
    now = utcnow()
    row = db.execute(text("""
        SELECT TOP 1 q.QueueID,q.TaskID,q.AttemptCount,q.MaxAttempts,t.ProjectID,t.Description,t.Priority,t.RiskLevel,t.RequiredRoleCode
        FROM AgentTaskQueue q WITH (UPDLOCK,READPAST,ROWLOCK)
        JOIN Task t ON t.TaskID=q.TaskID
        WHERE q.AgentID=:agent_id AND q.AvailableAtUtc<=:now
          AND q.Status IN ('Queued','Retry')
        ORDER BY q.AvailableAtUtc,t.PlannedSequence,t.CreatedAtUtc
    """), {"agent_id": agent_id, "now": now}).mappings().first()
    if not row:
        return None
    agent, blockers = _execution_gate(db, row["TaskID"], agent_id)
    if blockers:
        db.execute(text("""
            UPDATE AgentTaskQueue SET Status='Escalated',LastFailure=:reason,LeaseOwner=NULL,
                LeaseExpiresAtUtc=NULL,EscalatedAtUtc=:now,ModifiedAtUtc=:now
            WHERE QueueID=:queue_id
        """), {"reason": "; ".join(blockers), "now": now, "queue_id": row["QueueID"]})
        db.execute(text("UPDATE Task SET Status='Blocked',ModifiedAtUtc=:now WHERE TaskID=:task_id"), {
            "now": now, "task_id": row["TaskID"],
        })
        _create_escalation(db, row, agent_id, "EXECUTION_GATE_BLOCKED", "; ".join(blockers), actor_id)
        _runtime_event(db, event_type="ExecutionBlocked", actor_type="System", actor_id=actor_id,
                       severity="Blocked", queue_id=row["QueueID"], task_id=row["TaskID"], agent_id=agent_id,
                       details={"blockers": blockers})
        return {"blocked": True, "blockers": blockers}

    attempt = int(row["AttemptCount"]) + 1
    execution_id = uuid.uuid4()
    lease_expiry = now + timedelta(minutes=LEASE_MINUTES)
    context = _task_context(db, row["TaskID"], row["QueueID"], attempt)
    db.execute(text("""
        UPDATE AgentTaskQueue SET Status='Executing',AttemptCount=:attempt,LeaseOwner=:agent,
            LeaseExpiresAtUtc=:expires,ModifiedAtUtc=:now
        WHERE QueueID=:queue_id
    """), {"attempt": attempt, "agent": str(agent_id), "expires": lease_expiry, "now": now, "queue_id": row["QueueID"]})
    db.execute(text("UPDATE Task SET Status='InProgress',ModifiedAtUtc=:now WHERE TaskID=:task_id"), {
        "now": now, "task_id": row["TaskID"],
    })
    db.execute(text("""
        INSERT AgentExecution
            (ExecutionID,QueueID,TaskID,AgentID,AttemptNumber,Status,CorrelationID,InputSnapshot,StartedAtUtc,HeartbeatAtUtc)
        VALUES(:execution_id,:queue_id,:task_id,:agent_id,:attempt,'Executing',:correlation,:input,:now,:now)
    """), {
        "execution_id": execution_id, "queue_id": row["QueueID"], "task_id": row["TaskID"],
        "agent_id": agent_id, "attempt": attempt, "correlation": uuid.uuid4(),
        "input": json.dumps({"description": row["Description"], "required_role": row["RequiredRoleCode"],
                              "priority": row["Priority"], "risk_level": row["RiskLevel"],
                              "correction_context": context}, default=str),
        "now": now,
    })
    if context["open_defects"]:
        db.execute(text("""
            UPDATE AgentRuntimeDefect SET Status='InProgress'
            WHERE TaskID=:task_id AND Status='Open'
        """), {"task_id": row["TaskID"]})
    _runtime_event(db, event_type="TaskClaimed", actor_type="Agent", actor_id=agent_id,
                   severity="Info", execution_id=execution_id, queue_id=row["QueueID"],
                   task_id=row["TaskID"], agent_id=agent_id, details={"attempt": attempt})
    return {"execution_id": str(execution_id), "queue_id": str(row["QueueID"]), "task_id": str(row["TaskID"]),
            "attempt": attempt, "lease_expires_at_utc": lease_expiry.isoformat(),
            "task": {"description": row["Description"], "required_role": row["RequiredRoleCode"],
                     "priority": row["Priority"], "risk_level": row["RiskLevel"]},
            "context": context}


def _task_context(db, task_id, queue_id, attempt):
    """Requirement, previous-attempt reference and open defects for one task (read only)."""
    requirement = db.execute(text("""
        SELECT r.RequirementID,r.Title,r.Description
        FROM Task t JOIN Project p ON p.ProjectID=t.ProjectID
        JOIN Requirement r ON r.RequirementID=p.RequirementID
        WHERE t.TaskID=:task_id
    """), {"task_id": task_id}).mappings().first()
    previous = db.execute(text("""
        SELECT TOP 1 e.ExecutionID,e.AttemptNumber,o.OutputID,o.Sha256
        FROM AgentExecution e
        LEFT JOIN AgentExecutionOutput o ON o.ExecutionID=e.ExecutionID
        WHERE e.QueueID=:queue_id AND e.AttemptNumber<:attempt
        ORDER BY e.AttemptNumber DESC,o.CreatedAtUtc DESC
    """), {"queue_id": queue_id, "attempt": attempt}).mappings().first()
    defects = db.execute(text("""
        SELECT DefectID,ExecutionID,Severity,RootCause,BusinessImpact,TechnicalImpact,FixRecommendation
        FROM AgentRuntimeDefect
        WHERE TaskID=:task_id AND Status IN ('Open','InProgress','Retest')
        ORDER BY CreatedAtUtc
    """), {"task_id": task_id}).mappings().all()
    return {
        "requirement": {"id": str(requirement["RequirementID"]), "title": requirement["Title"],
                        "description": requirement["Description"]} if requirement else None,
        "previous_attempt": {"attempt": int(previous["AttemptNumber"]), "execution_id": str(previous["ExecutionID"]),
                             "output_id": str(previous["OutputID"]) if previous["OutputID"] else None,
                             "sha256": previous["Sha256"]} if previous else None,
        "open_defects": [{k: str(v) for k, v in d.items()} for d in defects],
    }


def get_worker_context(db, execution_id, agent_id):
    """Context only for the execution this agent currently holds a valid lease on."""
    row = db.execute(text("""
        SELECT e.QueueID,e.TaskID,e.AttemptNumber,q.LeaseExpiresAtUtc
        FROM AgentExecution e
        JOIN AgentTaskQueue q ON q.QueueID=e.QueueID
        JOIN Task t ON t.TaskID=e.TaskID
        WHERE e.ExecutionID=:id AND e.AgentID=:agent AND e.Status='Executing'
          AND q.Status='Executing' AND q.LeaseOwner=:agent_text
          AND q.LeaseExpiresAtUtc>:now AND t.AssignedAgentID=:agent
    """), {"id": execution_id, "agent": agent_id, "agent_text": str(agent_id), "now": utcnow()}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Execution not found for this agent lease")
    return _task_context(db, row["TaskID"], row["QueueID"], int(row["AttemptNumber"]))


def _create_escalation(db, queue_row, agent_id, code, reason, actor_id):
    existing = db.execute(text("""
        SELECT EscalationID FROM AgentRuntimeEscalation
        WHERE QueueID=:queue_id AND EscalationCode=:code AND Status='Open'
    """), {"queue_id": queue_row["QueueID"], "code": code}).scalar_one_or_none()
    if existing:
        return existing
    escalation_id = uuid.uuid4()
    db.execute(text("""
        INSERT AgentRuntimeEscalation
            (EscalationID,QueueID,TaskID,AgentID,EscalationCode,Severity,Reason,Status,CreatedAtUtc)
        VALUES(:id,:queue_id,:task_id,:agent_id,:code,'High',:reason,'Open',:now)
    """), {"id": escalation_id, "queue_id": queue_row["QueueID"], "task_id": queue_row["TaskID"],
          "agent_id": agent_id, "code": code, "reason": reason, "now": utcnow()})
    recipients = db.execute(text("""
        SELECT u.UserID FROM AppUser u JOIN Role r ON r.RoleID=u.RoleID
        WHERE u.IsActive=1 AND r.IsActive=1 AND r.RoleCode IN ('APPROVER','PLATFORM_OWNER','OWNER','SUPER_ADMIN')
    """)).scalars().all()
    for user_id in recipients:
        db.execute(text("""
            INSERT Notification
                (NotificationID,UserID,NotificationType,Title,Body,ResourceType,ResourceID,CorrelationID,IsRead,CreatedAtUtc)
            VALUES(:id,:user_id,'RUNTIME_ESCALATION','Agent runtime escalation','A governed runtime task is blocked and requires Owner review.',
                   'AgentRuntimeEscalation',:resource,:correlation,0,:now)
        """), {"id": uuid.uuid4(), "user_id": user_id, "resource": str(escalation_id),
              "correlation": uuid.uuid4(), "now": utcnow()})
    return escalation_id


class AgentRuntime:
    """Persistence/orchestration boundary. A trusted execution adapter must be injected to run work."""

    def __init__(self, executor=None):
        self.executor = executor

    def execute(self, task_payload):
        if self.executor is None:
            raise RuntimeError("No trusted agent execution adapter is configured")
        return self.executor.execute(task_payload)


def submit_output(db, execution_id, agent_id, name, content_type, content, actor_id):
    execution = db.execute(text("""
        SELECT e.ExecutionID,e.QueueID,e.TaskID,e.AgentID,e.Status,q.Status AS QueueStatus,
               q.LeaseExpiresAtUtc
        FROM AgentExecution e WITH (UPDLOCK,ROWLOCK)
        JOIN AgentTaskQueue q WITH (UPDLOCK,ROWLOCK) ON q.QueueID=e.QueueID
        WHERE e.ExecutionID=:execution_id
    """), {"execution_id": execution_id}).mappings().first()
    if not execution or execution["AgentID"] != agent_id:
        raise HTTPException(status_code=404, detail="Execution not found for this agent")
    if execution["Status"] != "Executing":
        raise HTTPException(status_code=409, detail="Execution is not accepting output")
    if execution["QueueStatus"] != "Executing" or (execution["LeaseExpiresAtUtc"] and execution["LeaseExpiresAtUtc"] < utcnow()):
        raise HTTPException(status_code=409, detail="Execution lease is no longer valid")
    if not name.strip() or not content.strip() or len(content) > MAX_OUTPUT_CHARS:
        raise HTTPException(status_code=422, detail=f"Output must be non-empty and at most {MAX_OUTPUT_CHARS} characters")

    output_id = uuid.uuid4()
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    now = utcnow()
    db.execute(text("""
        INSERT AgentExecutionOutput(OutputID,ExecutionID,OutputName,ContentType,Content,Sha256,CreatedAtUtc)
        VALUES(:output_id,:execution_id,:name,:content_type,:content,:hash,:created_at)
    """), {"output_id": output_id, "execution_id": execution_id, "name": name.strip(),
          "content_type": content_type, "content": content, "hash": digest, "created_at": now})

    structural_pass = structural_output_passes(name, content)
    qa_type = "RuntimeStructuralQA"
    db.execute(text("""
        INSERT Evaluation(EvaluationID,AgentID,TaskID,EvaluationType,Score,Passed,Evidence,CreatedAtUtc)
        VALUES(:id,:agent_id,:task_id,:type,:score,:passed,:evidence,:created_at)
    """), {"id": uuid.uuid4(), "agent_id": agent_id, "task_id": execution["TaskID"],
          "type": qa_type, "score": 100 if structural_pass else 0, "passed": structural_pass,
          "evidence": json.dumps({"output_id": str(output_id), "sha256": digest,
                                  "scope": "structural only; independent QA still required"}), "created_at": now})
    db.execute(text("""
        UPDATE AgentRuntimeDefect SET Status='Retest'
        WHERE TaskID=:task_id AND Status='InProgress'
    """), {"task_id": execution["TaskID"]})
    db.execute(text("""
        UPDATE AgentExecution SET Status='Review',CompletedAtUtc=:now,HeartbeatAtUtc=:now
        WHERE ExecutionID=:execution_id
    """), {"now": now, "execution_id": execution_id})
    db.execute(text("UPDATE AgentTaskQueue SET Status='Review',LeaseExpiresAtUtc=NULL,ModifiedAtUtc=:now WHERE QueueID=:queue_id"), {
        "now": now, "queue_id": execution["QueueID"],
    })
    db.execute(text("UPDATE Task SET Status='Review',ModifiedAtUtc=:now WHERE TaskID=:task_id"), {
        "now": now, "task_id": execution["TaskID"],
    })
    _runtime_event(db, event_type="OutputSubmitted", actor_type="Agent", actor_id=actor_id,
                   severity="Info", execution_id=execution_id, queue_id=execution["QueueID"],
                   task_id=execution["TaskID"], agent_id=agent_id,
                   details={"output_id": str(output_id), "sha256": digest, "structural_qa": "passed", "independent_qa": "pending"})
    return {"output_id": str(output_id), "sha256": digest, "status": "Review", "structural_qa": "passed", "independent_qa": "pending"}


def _assert_independent(db, task_id, reviewer_id):
    """Reviewer must hold RUNTIME_REVIEWER and must not be a recorded creator of the work.

    Fails closed when creator identity is unknown (NULL). Agent IDs are never compared with user IDs.
    """
    role = db.execute(text("""
        SELECT r.RoleCode FROM AppUser u JOIN Role r ON r.RoleID=u.RoleID
        WHERE u.UserID=:id AND u.IsActive=1 AND r.IsActive=1
    """), {"id": reviewer_id}).scalar_one_or_none()
    if str(role or "").upper() != "RUNTIME_REVIEWER":
        raise HTTPException(status_code=403, detail="Active RUNTIME_REVIEWER role required")
    creators = db.execute(text("""
        SELECT t.CreatedByUserID AS TaskCreator,p.CreatedByUserID AS ProjectCreator,
               r.CreatedByUserID AS RequirementCreator
        FROM Task t JOIN Project p ON p.ProjectID=t.ProjectID
        LEFT JOIN Requirement r ON r.RequirementID=p.RequirementID
        WHERE t.TaskID=:task_id
    """), {"task_id": task_id}).mappings().first()
    if not creators:
        raise HTTPException(status_code=403, detail="Work provenance cannot be established; review denied")
    values = [creators["TaskCreator"], creators["ProjectCreator"], creators["RequirementCreator"]]
    if any(v is None for v in values):
        raise HTTPException(status_code=403, detail="Creator identity is unknown; independent review denied (fail closed)")
    if any(str(v).lower() == str(reviewer_id).lower() for v in values):
        raise HTTPException(status_code=403, detail="Reviewer created this work and cannot review it")


def claim_review(db, reviewer_id):
    """Atomically lease the next execution awaiting review (UPDLOCK,READPAST on the execution row)."""
    now = utcnow()
    row = db.execute(text("""
        SELECT TOP 1 e.ExecutionID,e.TaskID,e.ReviewAttempt
        FROM AgentExecution e WITH (UPDLOCK,READPAST,ROWLOCK)
        JOIN Task t ON t.TaskID=e.TaskID
        JOIN Project p ON p.ProjectID=t.ProjectID
        LEFT JOIN Requirement r ON r.RequirementID=p.RequirementID
        WHERE e.Status='Review' AND e.ReviewDecision IS NULL
          AND (e.ReviewOwnerUserID IS NULL OR e.ReviewLeaseExpiresAtUtc<:now)
          AND t.CreatedByUserID IS NOT NULL AND p.CreatedByUserID IS NOT NULL
          AND r.CreatedByUserID IS NOT NULL
          AND t.CreatedByUserID<>:reviewer_id
          AND p.CreatedByUserID<>:reviewer_id
          AND r.CreatedByUserID<>:reviewer_id
        ORDER BY e.CompletedAtUtc
    """), {"now": now, "reviewer_id": reviewer_id}).mappings().first()
    if not row:
        return None
    expires = now + timedelta(minutes=REVIEW_LEASE_MINUTES)
    db.execute(text("""
        UPDATE AgentExecution SET ReviewOwnerUserID=:owner,ReviewLeaseExpiresAtUtc=:expires,
            ReviewAttempt=ReviewAttempt+1
        WHERE ExecutionID=:id
    """), {"owner": reviewer_id, "expires": expires, "id": row["ExecutionID"]})
    _assert_independent(db, row["TaskID"], reviewer_id)
    _runtime_event(db, event_type="ReviewLeaseClaimed", actor_type="User", actor_id=reviewer_id,
                   execution_id=row["ExecutionID"], task_id=row["TaskID"],
                   details={"review_attempt": int(row["ReviewAttempt"]) + 1, "lease_expires_at": expires.isoformat()})
    return {"execution_id": str(row["ExecutionID"]), "review_lease_expires_at_utc": expires.isoformat()}


def get_review_package(db, execution_id, reviewer_id):
    """Review material, only for the current lease owner."""
    row = db.execute(text("""
        SELECT e.ExecutionID,e.TaskID,e.AttemptNumber,e.QueueID
        FROM AgentExecution e
        WHERE e.ExecutionID=:id AND e.Status='Review' AND e.ReviewOwnerUserID=:reviewer
          AND e.ReviewLeaseExpiresAtUtc>:now
    """), {"id": execution_id, "reviewer": reviewer_id, "now": utcnow()}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="No active review lease for this execution")
    outputs = db.execute(text("""
        SELECT OutputID,OutputName,ContentType,Content,Sha256 FROM AgentExecutionOutput WHERE ExecutionID=:id
    """), {"id": execution_id}).mappings().all()
    context = _task_context(db, row["TaskID"], row["QueueID"], int(row["AttemptNumber"]))
    return {"execution_id": str(execution_id), "attempt": int(row["AttemptNumber"]),
            "outputs": [{"output_id": str(o["OutputID"]), "name": o["OutputName"], "content_type": o["ContentType"],
                         "content": o["Content"], "sha256": o["Sha256"]} for o in outputs],
            "context": context}


def review_execution(db, execution_id, reviewer_id, passed, reason, defect=None, review_key=None, require_lease=False):
    execution = db.execute(text("""
         SELECT e.ExecutionID,e.QueueID,e.TaskID,e.AgentID,e.Status,q.AttemptCount,q.MaxAttempts,
               q.Status AS QueueStatus,t.ProjectID,t.RequiredRoleCode,t.RiskLevel,
               e.ReviewKey,e.ReviewDecision,e.ReviewOwnerUserID,e.ReviewLeaseExpiresAtUtc
        FROM AgentExecution e WITH (UPDLOCK,ROWLOCK)
        JOIN AgentTaskQueue q ON q.QueueID=e.QueueID JOIN Task t ON t.TaskID=e.TaskID
        WHERE e.ExecutionID=:execution_id
    """), {"execution_id": execution_id}).mappings().first()
    if (execution and review_key and execution["ReviewKey"] == review_key
            and execution["ReviewDecision"] is not None):
        if (execution["ReviewDecision"] == "Approved") != bool(passed):
            raise HTTPException(status_code=409, detail="Review key already used with a different decision")
        return {"execution_id": str(execution_id), "passed": execution["ReviewDecision"] == "Approved",
                "status": execution["Status"], "idempotent_replay": True}
    if not execution or execution["Status"] != "Review" or execution["QueueStatus"] != "Review":
        raise HTTPException(status_code=409, detail="Execution is not awaiting independent QA review")
    if require_lease:
        if (not execution["ReviewOwnerUserID"] or str(execution["ReviewOwnerUserID"]).lower() != str(reviewer_id).lower()
                or not execution["ReviewLeaseExpiresAtUtc"] or execution["ReviewLeaseExpiresAtUtc"] < utcnow()):
            raise HTTPException(status_code=409, detail="Review lease is not held by this reviewer or has expired")
        _assert_independent(db, execution["TaskID"], reviewer_id)
        if not review_key:
            raise HTTPException(status_code=422, detail="review_key is required")
    if not reason or not reason.strip():
        raise HTTPException(status_code=422, detail="A review rationale is required")
    enqueue_result = {"queued_count": 0, "blocked_count": 0}
    now = utcnow()
    db.execute(text("""
        UPDATE AgentExecution SET ReviewDecision=:decision,ReviewKey=:key,ReviewOwnerUserID=:owner,
            ReviewLeaseExpiresAtUtc=NULL
        WHERE ExecutionID=:id
    """), {"decision": "Approved" if passed else "Rejected", "key": review_key,
           "owner": reviewer_id if require_lease else execution["ReviewOwnerUserID"], "id": execution_id})
    db.execute(text("""
        INSERT Evaluation(EvaluationID,AgentID,TaskID,EvaluationType,Score,Passed,Evidence,CreatedAtUtc)
        VALUES(:id,:agent_id,:task_id,'IndependentQA',:score,:passed,:evidence,:now)
    """), {"id": uuid.uuid4(), "agent_id": execution["AgentID"], "task_id": execution["TaskID"],
          "score": 100 if passed else 0, "passed": passed,
          "evidence": json.dumps({"reviewer": str(reviewer_id), "reason": reason.strip()}), "now": now})
    if passed:
        outputs = db.execute(text("""
            SELECT OutputID,OutputName,Content,Sha256
            FROM AgentExecutionOutput
            WHERE ExecutionID=:execution_id
        """), {"execution_id": execution_id}).mappings().all()
        if not outputs:
            raise HTTPException(status_code=409, detail="Execution has no stored output to accept as a deliverable")
        if len(outputs) != 1:
            raise HTTPException(status_code=409, detail="Exactly one output is required for approval")
        output = outputs[0]
        if hashlib.sha256((output["Content"] or "").encode("utf-8")).hexdigest() != output["Sha256"]:
            raise HTTPException(status_code=409, detail="Stored output hash does not match its content")
        artifact_uri = f"agent-execution-output:{output['OutputID']}"
        if db.execute(text("SELECT 1 FROM Deliverable WHERE ArtifactUri=:uri"), {"uri": artifact_uri}).first():
            raise HTTPException(status_code=409, detail="A deliverable already exists for this output")
        db.execute(text("""
            INSERT Deliverable(DeliverableID,ProjectID,TaskID,Name,ArtifactUri,ArtifactHash,Status)
            VALUES(:deliverable_id,:project_id,:task_id,:name,:artifact_uri,:artifact_hash,'Accepted')
        """), {
            "deliverable_id": uuid.uuid4(),
            "project_id": execution["ProjectID"],
            "task_id": execution["TaskID"],
            "name": output["OutputName"],
            "artifact_uri": artifact_uri,
            "artifact_hash": output["Sha256"],
        })
        db.execute(text("UPDATE AgentExecution SET Status='Completed' WHERE ExecutionID=:id"), {"id": execution_id})
        db.execute(text("UPDATE AgentTaskQueue SET Status='Completed',ModifiedAtUtc=:now WHERE QueueID=:id"), {
            "now": now, "id": execution["QueueID"],
        })
        db.execute(text("""
            UPDATE AgentRuntimeDefect SET Status='Closed',ClosedAtUtc=:now
            WHERE TaskID=:task_id AND Status IN ('Open','InProgress','Retest')
        """), {"now": now, "task_id": execution["TaskID"]})
        db.execute(text("""
            UPDATE Task SET Status='Completed',CompletedAtUtc=:now,ModifiedAtUtc=:now,ModifiedBy=:reviewer
            WHERE TaskID=:task_id
        """), {"now": now, "reviewer": str(reviewer_id), "task_id": execution["TaskID"]})
        db.execute(text("UPDATE TaskAssignment SET Status='Released',ReleasedAtUtc=:now WHERE TaskID=:task_id AND ReleasedAtUtc IS NULL"), {
            "now": now, "task_id": execution["TaskID"],
        })
        remaining = db.execute(text("SELECT 1 FROM Task WHERE ProjectID=:project AND Status<>'Completed'"), {
            "project": execution["ProjectID"],
        }).first()
        project_status = "Completed" if not remaining else "InProgress"
        db.execute(text("UPDATE Project SET Status=:status WHERE ProjectID=:project"), {
            "status": project_status, "project": execution["ProjectID"],
        })
        if remaining:
            from app.services.workforce_planner import WorkforcePlanner
            project = db.execute(text("""
                SELECT r.RequirementID,r.CreatedBy,r.Priority,r.RiskLevel,r.Title,r.Description,r.RequestedBy
                FROM Project p JOIN Requirement r ON r.RequirementID=p.RequirementID
                WHERE p.ProjectID=:project_id
            """), {"project_id": execution["ProjectID"]}).mappings().first()
            if project:
                WorkforcePlanner().plan_project(db, execution["ProjectID"], project)
                enqueue_result = enqueue_ready_tasks(db, execution["ProjectID"], reviewer_id)
            else:
                enqueue_result = {"queued_count": 0, "blocked_count": 0}
        else:
            enqueue_result = {"queued_count": 0, "blocked_count": 0}
    else:
        failure = reason.strip()
        defect = defect or {}
        defect_id = uuid.uuid4()
        db.execute(text("""
            INSERT AgentRuntimeDefect
                (DefectID,ExecutionID,TaskID,AgentID,Severity,Priority,RootCause,BusinessImpact,
                 TechnicalImpact,FixRecommendation,AssignedRoleCode,Status,CreatedAtUtc)
            VALUES(:id,:execution_id,:task_id,:agent_id,:severity,:priority,:root_cause,:business_impact,
                   :technical_impact,:recommendation,:role_code,'Open',:now)
        """), {"id": defect_id, "execution_id": execution_id, "task_id": execution["TaskID"],
              "agent_id": execution["AgentID"], "severity": defect.get("severity", "High"),
              "priority": defect.get("priority", "High"),
              "root_cause": defect.get("root_cause", failure)[:1000],
              "business_impact": defect.get("business_impact", "Deliverable did not pass independent quality review.")[:1000],
              "technical_impact": defect.get("technical_impact", "Output requires correction and retest before task completion.")[:1000],
              "recommendation": defect.get("fix_recommendation", "Address reviewer findings, resubmit output, and repeat independent QA.")[:1000],
              "role_code": defect.get("assigned_role_code") or execution["RequiredRoleCode"], "now": now})
        next_attempt = int(execution["AttemptCount"])
        if can_retry(next_attempt, int(execution["MaxAttempts"])):
            db.execute(text("""
                UPDATE AgentExecution SET Status='QARejected',FailureReason=:reason,CompletedAtUtc=:now
                WHERE ExecutionID=:id
            """), {"reason": failure, "now": now, "id": execution_id})
            db.execute(text("""
                UPDATE AgentTaskQueue SET Status='Retry',LastFailure=:reason,AvailableAtUtc=:now,
                    LeaseOwner=NULL,LeaseExpiresAtUtc=NULL,ModifiedAtUtc=:now
                WHERE QueueID=:id
            """), {"reason": failure, "now": now, "id": execution["QueueID"]})
            db.execute(text("UPDATE Task SET Status='Queued' WHERE TaskID=:task_id"), {"task_id": execution["TaskID"]})
            _runtime_event(db, event_type="QARejectedRetryQueued", actor_type="User", actor_id=reviewer_id,
                           severity="Warning", execution_id=execution_id, queue_id=execution["QueueID"],
                           task_id=execution["TaskID"], agent_id=execution["AgentID"], details={"reason": failure})
        else:
            db.execute(text("""
                UPDATE AgentExecution SET Status='Escalated',FailureReason=:reason,CompletedAtUtc=:now
                WHERE ExecutionID=:id
            """), {"reason": failure, "now": now, "id": execution_id})
            db.execute(text("""
                UPDATE AgentTaskQueue SET Status='Escalated',LastFailure=:reason,LeaseExpiresAtUtc=NULL,
                    ModifiedAtUtc=:now WHERE QueueID=:id
            """), {"reason": failure, "now": now, "id": execution["QueueID"]})
            db.execute(text("UPDATE Task SET Status='Blocked' WHERE TaskID=:task_id"), {"task_id": execution["TaskID"]})
            _create_escalation(db, execution, execution["AgentID"], "QA_RETRY_LIMIT", failure, reviewer_id)
            db.execute(text("""
                UPDATE AgentRuntimeDefect SET Status='Escalated'
                WHERE TaskID=:task_id AND Status IN ('Open','InProgress','Retest')
            """), {"task_id": execution["TaskID"]})
    _runtime_event(db, event_type="IndependentQAReview", actor_type="User", actor_id=reviewer_id,
                   severity="Info" if passed else "Warning", execution_id=execution_id,
                   queue_id=execution["QueueID"], task_id=execution["TaskID"], agent_id=execution["AgentID"],
                   details={"passed": passed, "reason": reason.strip()})
    return {"execution_id": str(execution_id), "passed": passed,
            "status": "Completed" if passed else ("Retry" if can_retry(int(execution["AttemptCount"]), int(execution["MaxAttempts"])) else "Escalated"),
            "next_tasks": enqueue_result}


def heartbeat_execution(db, execution_id, agent_id):
    execution = db.execute(text("""
        SELECT e.ExecutionID,e.QueueID,e.AgentID,e.Status,q.LeaseExpiresAtUtc,q.Status AS QueueStatus
        FROM AgentExecution e WITH (UPDLOCK,ROWLOCK)
        JOIN AgentTaskQueue q ON q.QueueID=e.QueueID
        WHERE e.ExecutionID=:execution_id
    """), {"execution_id": execution_id}).mappings().first()
    if not execution or execution["AgentID"] != agent_id:
        raise HTTPException(status_code=404, detail="Execution not found for agent")
    now = utcnow()
    if execution["Status"] != "Executing" or execution["QueueStatus"] != "Executing":
        raise HTTPException(status_code=409, detail="Execution is not active")
    if execution["LeaseExpiresAtUtc"] and execution["LeaseExpiresAtUtc"] < now:
        raise HTTPException(status_code=409, detail="Execution lease expired")
    expires = now + timedelta(minutes=LEASE_MINUTES)
    db.execute(text("UPDATE AgentExecution SET HeartbeatAtUtc=:now WHERE ExecutionID=:id"), {
        "now": now, "id": execution_id,
    })
    db.execute(text("UPDATE AgentTaskQueue SET LeaseExpiresAtUtc=:expires,ModifiedAtUtc=:now WHERE QueueID=:id"), {
        "expires": expires, "now": now, "id": execution["QueueID"],
    })
    _runtime_event(db, "ExecutionHeartbeat", "Agent", agent_id, execution_id=execution_id,
                   queue_id=execution["QueueID"], agent_id=agent_id, details={"lease_expires_at": expires.isoformat()})
    return {"execution_id": str(execution_id), "lease_expires_at_utc": expires.isoformat()}


def fail_execution(db, execution_id, agent_id, reason):
    execution = db.execute(text("""
        SELECT e.ExecutionID,e.QueueID,e.TaskID,e.AgentID,e.Status,q.AttemptCount,q.MaxAttempts,
               q.Status AS QueueStatus,q.LeaseExpiresAtUtc
        FROM AgentExecution e WITH (UPDLOCK,ROWLOCK) JOIN AgentTaskQueue q ON q.QueueID=e.QueueID
        WHERE e.ExecutionID=:execution_id
    """), {"execution_id": execution_id}).mappings().first()
    if not execution or execution["AgentID"] != agent_id:
        raise HTTPException(status_code=404, detail="Execution not found for agent")
    if execution["Status"] != "Executing":
        raise HTTPException(status_code=409, detail="Execution is not active")
    if execution["QueueStatus"] != "Executing" or (execution["LeaseExpiresAtUtc"] and execution["LeaseExpiresAtUtc"] < utcnow()):
        raise HTTPException(status_code=409, detail="Execution lease is no longer valid")
    if not reason or not reason.strip():
        raise HTTPException(status_code=422, detail="Failure reason is required")
    return _retry_or_escalate(db, execution, reason.strip(), "Agent", agent_id)


def reap_expired_leases(db, actor_id="runtime-reaper"):
    now = utcnow()
    expired = db.execute(text("""
        SELECT e.ExecutionID,e.QueueID,e.TaskID,e.AgentID,e.Status,q.AttemptCount,q.MaxAttempts
        FROM AgentExecution e WITH (UPDLOCK,READPAST,ROWLOCK)
        JOIN AgentTaskQueue q ON q.QueueID=e.QueueID
        WHERE e.Status='Executing' AND q.Status='Executing' AND q.LeaseExpiresAtUtc<:now
    """), {"now": now}).mappings().all()
    for execution in expired:
        _retry_or_escalate(db, execution, "Execution heartbeat lease expired", "System", actor_id)
    stale = db.execute(text("""
        SELECT e.ExecutionID,e.QueueID,e.TaskID,e.AgentID,e.ReviewAttempt,q.AttemptCount,q.MaxAttempts
        FROM AgentExecution e WITH (UPDLOCK,READPAST,ROWLOCK)
        JOIN AgentTaskQueue q ON q.QueueID=e.QueueID
        WHERE e.Status='Review' AND e.ReviewDecision IS NULL AND e.ReviewOwnerUserID IS NOT NULL
          AND e.ReviewLeaseExpiresAtUtc<:now
    """), {"now": now}).mappings().all()
    for execution in stale:
        db.execute(text("""
            UPDATE AgentExecution SET ReviewOwnerUserID=NULL,ReviewLeaseExpiresAtUtc=NULL WHERE ExecutionID=:id
        """), {"id": execution["ExecutionID"]})
        _runtime_event(db, event_type="ReviewLeaseExpired", actor_type="System", actor_id=actor_id,
                       severity="Warning", execution_id=execution["ExecutionID"], queue_id=execution["QueueID"],
                       task_id=execution["TaskID"], agent_id=execution["AgentID"],
                       details={"review_attempt": int(execution["ReviewAttempt"])})
        if int(execution["ReviewAttempt"]) >= MAX_REVIEW_ATTEMPTS:
            db.execute(text("""
                UPDATE AgentExecution SET Status='Escalated',FailureReason='Review lease timeout' WHERE ExecutionID=:id
            """), {"id": execution["ExecutionID"]})
            db.execute(text("""
                UPDATE AgentTaskQueue SET Status='Escalated',LastFailure='Review lease timeout',
                    EscalatedAtUtc=:now,ModifiedAtUtc=:now WHERE QueueID=:id
            """), {"now": now, "id": execution["QueueID"]})
            db.execute(text("UPDATE Task SET Status='Blocked' WHERE TaskID=:id"), {"id": execution["TaskID"]})
            db.execute(text("""
                UPDATE AgentRuntimeDefect SET Status='Escalated'
                WHERE TaskID=:id AND Status IN ('Open','InProgress','Retest')
            """), {"id": execution["TaskID"]})
            _create_escalation(db, execution, execution["AgentID"], "REVIEW_TIMEOUT",
                               "Independent review lease expired repeatedly", actor_id)
    return {"expired_lease_count": len(expired), "expired_review_lease_count": len(stale)}


def _retry_or_escalate(db, execution, reason, actor_type, actor_id):
    now = utcnow()
    if can_retry(int(execution["AttemptCount"]), int(execution["MaxAttempts"])):
        db.execute(text("""
            UPDATE AgentExecution SET Status='Failed',FailureReason=:reason,CompletedAtUtc=:now
            WHERE ExecutionID=:id
        """), {"reason": reason[:2000], "now": now, "id": execution["ExecutionID"]})
        db.execute(text("""
            UPDATE AgentTaskQueue SET Status='Retry',LastFailure=:reason,AvailableAtUtc=:now,
                LeaseOwner=NULL,LeaseExpiresAtUtc=NULL,ModifiedAtUtc=:now
            WHERE QueueID=:id
        """), {"reason": reason[:2000], "now": now, "id": execution["QueueID"]})
        db.execute(text("UPDATE Task SET Status='Queued' WHERE TaskID=:id"), {"id": execution["TaskID"]})
        result = "Retry"
    else:
        db.execute(text("""
            UPDATE AgentExecution SET Status='Escalated',FailureReason=:reason,CompletedAtUtc=:now
            WHERE ExecutionID=:id
        """), {"reason": reason[:2000], "now": now, "id": execution["ExecutionID"]})
        db.execute(text("""
            UPDATE AgentTaskQueue SET Status='Escalated',LastFailure=:reason,LeaseOwner=NULL,
                LeaseExpiresAtUtc=NULL,EscalatedAtUtc=:now,ModifiedAtUtc=:now
            WHERE QueueID=:id
        """), {"reason": reason[:2000], "now": now, "id": execution["QueueID"]})
        db.execute(text("UPDATE Task SET Status='Blocked' WHERE TaskID=:id"), {"id": execution["TaskID"]})
        _create_escalation(db, execution, execution["AgentID"], "RETRY_LIMIT", reason, actor_id)
        result = "Escalated"
    _runtime_event(db, "ExecutionFailure" if actor_type == "Agent" else "ExecutionLeaseExpired",
                   actor_type, actor_id, severity="Warning", execution_id=execution["ExecutionID"],
                   queue_id=execution["QueueID"], task_id=execution["TaskID"], agent_id=execution["AgentID"],
                   details={"reason": reason, "result": result})
    return result
