import uuid
import json
import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.security.dependencies import get_current_user
from app.security.permissions import require_roles
from app.services.workforce_planner import REQUIRED_AGENT_CERTIFICATIONS, WorkforcePlanner, agent_meets_profile
from app.services.agent_runtime import queue_pending_tasks
from app.services.organization_orchestrator import OrganizationOrchestrator
from app.services.agent_factory import build_factory_blueprint, rank_assignment_candidates
from app.services.code_factory import build_code_package
from app.services.delivery_factory import build_delivery_execution_package
from app.services.assignment_factory import build_assignment_package
from app.services.testing_execution_factory import build_testing_execution_package
from app.services.build_factory import build_release_artifact_package
from app.services.deployment_factory import build_deployment_package
from app.services.hosting_factory import build_hosting_package
from app.services.operations_factory import build_operations_package
from app.services.blueprint_explorer import analyze_impact, search_packages
from app.services.copilot_agents import build_copilot_agents_package
from app.services.diagram_factory import build_diagram_package

router = APIRouter(prefix="/workforce", tags=["Workforce"])


class WorkforceDecision(BaseModel):
    action: Literal["approve_recruiting", "reject"]
    reason: str = Field(min_length=5, max_length=2000)


class WorkforceFill(BaseModel):
    agent_id: UUID
    reason: str = Field(min_length=5, max_length=2000)


class WorkforceActivation(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class WorkforceReuseDecision(BaseModel):
    action: Literal["approve", "reject"]
    reason: str = Field(min_length=5, max_length=2000)


class WorkforceUpskillCompletion(BaseModel):
    evidence: str = Field(min_length=20, max_length=4000)


class WorkforceReuseAssignment(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class AgentSkillChange(BaseModel):
    skill_id: UUID
    proficiency: int = Field(ge=1, le=5)
    action: Literal["assign", "approve", "revoke"]
    evidence: str = Field(min_length=20, max_length=4000)
    reason: str = Field(min_length=5, max_length=2000)


class AgentStatusChange(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class AgentModelConfiguration(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_catalog_id: UUID
    reason: str = Field(min_length=5, max_length=2000)


class EvaluationCriterionResult(BaseModel):
    criterion_code: str = Field(min_length=1, max_length=60)
    score: float = Field(ge=0, le=100)
    evidence: str = Field(min_length=20, max_length=2000)


class AgentEvaluationRecord(BaseModel):
    template_code: Literal["CAPABILITY", "SAFETY", "SECURITY", "GOVERNANCE"]
    criteria: list[EvaluationCriterionResult] = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=5, max_length=2000)


class OrganizationBootstrapRequest(BaseModel):
    approval_id: UUID


class TaskStatusChange(BaseModel):
    status: Literal["InProgress", "Completed", "Blocked", "Planned"]
    reason: str = Field(min_length=5, max_length=2000)


class FactoryBlueprintRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=20, max_length=12000)
    technology_changes: list[str] = Field(default_factory=list, max_length=20)
    domain: str | None = Field(default=None, max_length=120)
    priority: Literal["Low", "Medium", "High", "Critical"] | None = None

    @field_validator("technology_changes")
    @classmethod
    def bound_technology_inputs(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if any(len(value) > 100 for value in normalized):
            raise ValueError("Technology entries must be at most 100 characters")
        return normalized


class FactoryCandidatePreviewRequest(BaseModel):
    role_code: str = Field(min_length=2, max_length=60)
    exclude_agent_id: UUID | None = None


class FactoryCodePackageRequest(FactoryBlueprintRequest):
    backend_language: Literal["dotnet", "python", "node"] = "python"


class BuildPlanRequest(FactoryCodePackageRequest):
    semantic_version: str = Field(default="0.1.0", min_length=5, max_length=32)

    @field_validator("semantic_version")
    @classmethod
    def validate_semantic_version(cls, value: str) -> str:
        if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?", value):
            raise ValueError("semantic_version must follow MAJOR.MINOR.PATCH[-PRERELEASE]")
        return value


class AssignmentCandidateEvidence(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=80)
    agent_role: str = Field(min_length=2, max_length=120)
    skills: dict[str, int] = Field(default_factory=dict, max_length=100)
    certifications_current: list[str] = Field(default_factory=list, max_length=20)
    available: bool | None = None
    available_capacity_hours: float | None = Field(default=None, ge=0, le=10000)
    reserved_capacity_hours: float | None = Field(default=None, ge=0, le=10000)
    project_fit_tags: list[str] = Field(default_factory=list, max_length=40)
    technology_experience: list[str] = Field(default_factory=list, max_length=40)
    performance_score: float | None = Field(default=None, ge=0, le=100)
    performance_evidence_reference: str | None = Field(default=None, max_length=200)

    @field_validator("skills")
    @classmethod
    def validate_candidate_skills(cls, values: dict[str, int]) -> dict[str, int]:
        if any(not name.strip() or len(name) > 100 for name in values):
            raise ValueError("Skill names must contain 1 to 100 characters")
        if any(not isinstance(level, int) or level < 0 or level > 5 for level in values.values()):
            raise ValueError("Skill levels must be integers between 0 and 5")
        return {name.strip(): level for name, level in values.items()}


class AssignmentPlanRequest(FactoryBlueprintRequest):
    candidate_evidence: list[AssignmentCandidateEvidence] = Field(default_factory=list, max_length=100)


def _audit(db, user, action, resource_type, resource_id, reason, metadata=None):
    details = {"reason": reason.strip()}
    if metadata:
        details.update(metadata)
    db.execute(text("""
        INSERT INTO AuditLog
            (CorrelationID, ActorType, ActorID, Action, ResourceType, ResourceID, Outcome, Details)
        VALUES
            (:correlation_id, 'User', :actor_id, :action, :resource_type, :resource_id, 'Success', :details)
    """), {
        "correlation_id": uuid.uuid4(),
        "actor_id": user["sub"],
        "action": action,
        "resource_type": resource_type,
        "resource_id": str(resource_id),
        "details": json.dumps(details, ensure_ascii=True),
    })


@router.get("/roles", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER", "ADMIN", "OWNER", "SUPER_ADMIN"))])
def list_role_profiles(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT RoleCode, PositionName, DepartmentName, Grade, JobDescription,
             ResponsibilitiesJson, RequiredSkillsJson, ProfileVersion,
             ReportsToRoleCode, OrgLayer, ApprovalScope, QualityGatesJson,
             MaxRecommendedAutonomy
        FROM WorkforceRoleProfile WHERE Status = 'Active' ORDER BY DepartmentName, PositionName
    """)).mappings().all()
    return [dict(row) for row in rows]


@router.post("/factory/blueprint", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_agent_factory_blueprint(body: FactoryBlueprintRequest):
    return build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )


@router.post("/factory/project-blueprint", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_project_delivery_blueprint(body: FactoryBlueprintRequest):
    blueprint = build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )
    return blueprint["project_delivery_package"]


@router.post("/factory/agent-lifecycle-plan", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_agent_lifecycle_plan(body: FactoryBlueprintRequest):
    blueprint = build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )
    return blueprint["agent_lifecycle_package"]


@router.post("/factory/assignment-plan", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_agent_assignment_plan(body: AssignmentPlanRequest):
    blueprint = build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )
    candidates = [candidate.model_dump() for candidate in body.candidate_evidence]
    return build_assignment_package(blueprint, candidates)


@router.post("/factory/delivery-plan", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_delivery_execution_plan(body: FactoryBlueprintRequest):
    blueprint = build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )
    return build_delivery_execution_package(blueprint["project_delivery_package"])


@router.post("/factory/code-package", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_agent_code_package(body: FactoryCodePackageRequest):
    blueprint = build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )
    return build_code_package(blueprint["technical_delivery_package"], body.backend_language)


@router.post("/factory/build-plan", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_build_release_plan(body: BuildPlanRequest):
    blueprint = build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )
    code_package = build_code_package(blueprint["technical_delivery_package"], body.backend_language)
    testing_package = build_testing_execution_package(
        blueprint["technical_delivery_package"], blueprint["project_delivery_package"],
        blueprint["delivery_execution_package"], code_package,
    )
    return build_release_artifact_package(
        code_package, testing_package, blueprint["project_delivery_package"], body.semantic_version,
    )


@router.post("/factory/deployment-plan", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_deployment_plan(body: BuildPlanRequest):
    blueprint = build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )
    code_package = build_code_package(blueprint["technical_delivery_package"], body.backend_language)
    testing_package = build_testing_execution_package(
        blueprint["technical_delivery_package"], blueprint["project_delivery_package"],
        blueprint["delivery_execution_package"], code_package,
    )
    build_package = build_release_artifact_package(
        code_package, testing_package, blueprint["project_delivery_package"], body.semantic_version,
    )
    return build_deployment_package(
        build_package, testing_package, blueprint["project_delivery_package"],
    )


@router.post("/factory/hosting-plan", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_hosting_plan(body: BuildPlanRequest):
    blueprint = build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )
    code_package = build_code_package(blueprint["technical_delivery_package"], body.backend_language)
    testing_package = build_testing_execution_package(
        blueprint["technical_delivery_package"], blueprint["project_delivery_package"],
        blueprint["delivery_execution_package"], code_package,
    )
    build_package = build_release_artifact_package(
        code_package, testing_package, blueprint["project_delivery_package"], body.semantic_version,
    )
    deployment_package = build_deployment_package(
        build_package, testing_package, blueprint["project_delivery_package"],
    )
    return build_hosting_package(deployment_package, blueprint["technical_delivery_package"])


@router.post("/factory/operations-plan", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_operations_plan(body: BuildPlanRequest):
    blueprint = build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )
    return build_operations_package(
        blueprint["hosting_execution_package"],
        blueprint["delivery_execution_package"],
    )




@router.post("/factory/autonomy-plan", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_autonomy_plan(body: FactoryBlueprintRequest):
    blueprint = build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )
    return blueprint["autonomy_execution_package"]


@router.post("/factory/enterprise-architecture", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_enterprise_architecture(body: FactoryBlueprintRequest):
    blueprint = build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )
    return blueprint["autonomous_enterprise_package"]


@router.post("/factory/executive-command-center", dependencies=[Depends(require_roles("EXECUTIVE", "WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_executive_command_center(body: FactoryBlueprintRequest):
    blueprint = build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )
    return blueprint["executive_command_center"]


class BlueprintExplorerRequest(FactoryBlueprintRequest):
    query: str | None = Field(default=None, max_length=100)
    impact_of: str | None = Field(default=None, max_length=60)


@router.post("/factory/blueprint-explorer", dependencies=[Depends(require_roles("EXECUTIVE", "WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_blueprint_explorer(body: BlueprintExplorerRequest):
    blueprint = build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )
    explorer = dict(blueprint["blueprint_explorer"])
    if body.query:
        explorer["search_results"] = search_packages(explorer, body.query)
    if body.impact_of:
        impact = analyze_impact(explorer, body.impact_of)
        if impact is None:
            raise HTTPException(status_code=404, detail="Unknown package id")
        explorer["requested_impact"] = impact
    return explorer


@router.post("/factory/diagram-plan", dependencies=[Depends(require_roles("EXECUTIVE", "WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_diagram_plan(body: FactoryBlueprintRequest):
    blueprint = build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )
    return build_diagram_package(blueprint)


@router.get("/factory/copilot-agents", dependencies=[Depends(require_roles("EXECUTIVE", "WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def get_copilot_agents_design():
    return build_copilot_agents_package()


@router.post("/factory/approval-sandbox", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_approval_sandbox_preview(body: FactoryBlueprintRequest):
    blueprint = build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )
    return blueprint["approval_sandbox_package"]


@router.post("/factory/test-simulation", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def create_test_execution_simulation(body: FactoryCodePackageRequest):
    blueprint = build_factory_blueprint(
        title=body.title, description=body.description,
        technology_changes=body.technology_changes, domain=body.domain, priority=body.priority,
    )
    source_package = build_code_package(blueprint["technical_delivery_package"], body.backend_language)
    return build_testing_execution_package(
        blueprint["technical_delivery_package"],
        blueprint["project_delivery_package"],
        blueprint["delivery_execution_package"],
        source_package,
    )


@router.get("/factory/dashboard", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def workforce_factory_dashboard(db: Session = Depends(get_db), user=Depends(get_current_user)):
    readiness = agent_readiness(db, user)
    agents = readiness["agents"]
    active_agents = [agent for agent in agents if agent["status"] == "Active"]
    ready_agents = [agent for agent in active_agents
                    if not agent["skill_gaps"] and not agent["certification_gaps"]
                    and agent["model_provider"] not in (None, "UNCONFIGURED")
                    and agent["model"] not in (None, "UNCONFIGURED")
                    and agent["model_version"] not in (None, "UNCONFIGURED")]
    skill_items = readiness["required_skills"]
    covered_skills = sum(item["qualified_agent_count"] > 0 for item in skill_items)
    utilization_values = [agent["current_workload_percent"] for agent in active_agents]
    ready_percent = round(100 * len(ready_agents) / len(agents), 1) if agents else None
    return {
        "organization_scope": "single_organization",
        "total_agents": len(agents),
        "active_agents": len(active_agents),
        "available_agents": readiness["available_agents"],
        "assigned_agents": sum(agent["active_assignments"] > 0 for agent in active_agents),
        "certification_coverage_percent": round(
            100 * sum(not agent["certification_gaps"] for agent in active_agents) / len(active_agents), 1
        ) if active_agents else None,
        "skill_coverage_percent": round(100 * covered_skills / len(skill_items), 1) if skill_items else None,
        "capacity_utilization_percent": round(sum(utilization_values) / len(utilization_values), 1)
            if utilization_values else None,
        "skills_gap_count": len(readiness["skill_gaps"]),
        "workforce_readiness_percent": ready_percent,
        "ready_agents": len(ready_agents),
        "retirement_review": {"candidates": "Unavailable",
            "basis": "No approved obsolescence, usage-retention, or retirement evidence is evaluated by this dashboard."},
        "readiness_basis": "Active agents with no recorded skill/certification gaps and configured provider/model/version divided by all registered agents. This is not authorization to assign or activate.",
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "lifecycle_mutations_enabled": False,
    }


def _factory_candidate_preview(db: Session, body: FactoryCandidatePreviewRequest, user: dict):
    profile = db.execute(text("""
        SELECT RoleCode,PositionName,RequiredSkillsJson FROM dbo.WorkforceRoleProfile
        WHERE RoleCode=:role_code AND Status='Active'
    """), {"role_code": body.role_code}).mappings().first()
    if not profile:
        raise HTTPException(status_code=404, detail="Active workforce role profile not found")
    required_skills = {
        item["name"]: int(item["minimum_proficiency"])
        for item in json.loads(profile["RequiredSkillsJson"] or "[]")
    }
    readiness = agent_readiness(db, user)
    history = db.execute(text("""
        SELECT ta.AgentID,COUNT(DISTINCT t.ProjectID) AS CompletedProjects
        FROM dbo.TaskAssignment ta JOIN dbo.Task t ON t.TaskID=ta.TaskID
        WHERE ta.Status='Released' AND t.Status='Completed'
        GROUP BY ta.AgentID
    """)).mappings().all()
    completed_projects = {row["AgentID"]: int(row["CompletedProjects"] or 0) for row in history}
    candidates = []
    agent_names = {}
    for agent in readiness["agents"]:
        agent_id = UUID(agent["agent_id"])
        if (agent["status"] != "Active" or agent["agent_type"] == "Executive"
                or (body.exclude_agent_id and agent_id == body.exclude_agent_id)):
            continue
        skill_levels = {item["name"]: item["proficiency"] for item in agent["skills"]
                        if item["status"] == "Active"}
        certifications = [name for name, result in agent["certifications"].items()
                          if result.get("passed")]
        candidates.append({
            "agent_id": agent["agent_id"], "skills": skill_levels,
            "certifications": certifications,
            "available": agent["available_task_slots"] > 0 and agent["current_workload_percent"] < 100,
            "capacity_percent": agent["current_workload_percent"],
            "completed_projects": completed_projects.get(agent_id, 0),
            "performance_score": None,
        })
        agent_names[agent["agent_id"]] = agent["name"]
    ranked = rank_assignment_candidates(candidates, required_skills)
    for item in ranked:
        item["agent_name"] = agent_names.get(item["agent_id"])
    return {
        "role_code": profile["RoleCode"], "role_name": profile["PositionName"],
        "recommendations": ranked, "recommendation_only": True,
        "assignment_performed": False,
        "performance_score": "Unavailable: no approved normalization for stored performance rates",
        "decision": "Use the existing governed assignment workflow after reviewer validation.",
    }


@router.post("/factory/assignment-preview", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def workforce_assignment_preview(body: FactoryCandidatePreviewRequest, db: Session = Depends(get_db),
                                 user=Depends(get_current_user)):
    return _factory_candidate_preview(db, body, user)


@router.post("/factory/replacement-preview", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def workforce_replacement_preview(body: FactoryCandidatePreviewRequest, db: Session = Depends(get_db),
                                  user=Depends(get_current_user)):
    result = _factory_candidate_preview(db, body, user)
    result["preview_type"] = "replacement"
    result["decision"] = "Replacement is a recommendation only; preserve task approvals and use the governed assignment workflow."
    return result


@router.get("/governance-catalog", dependencies=[Depends(require_roles("PLATFORM_OWNER", "ADMIN", "OWNER", "SUPER_ADMIN"))])
def list_governance_catalog(db: Session = Depends(get_db)):
    gates = db.execute(text("""
        SELECT GateCode, SequenceNumber, GateName, OwnerRoleCode, AppliesTo,
               BlocksProgress, RequiresHumanApproval, RequiredEvidenceJson, Status
        FROM GovernanceGateProfile ORDER BY SequenceNumber
    """)).mappings().all()
    escalations = db.execute(text("""
        SELECT EscalationCode, SequenceNumber, TargetRoleCode, TriggerDescription,
               TargetResponseMinutes, RequiresNotification, Status
        FROM EscalationPolicyProfile ORDER BY SequenceNumber
    """)).mappings().all()
    return {
        "runtime_enforced": False,
        "notice": "These are configured target policies. Runtime workflow enforcement is being implemented separately.",
        "gates": [dict(row) for row in gates],
        "escalations": [dict(row) for row in escalations],
    }


@router.get("/organization/status", dependencies=[Depends(require_roles("PLATFORM_OWNER", "ADMIN", "OWNER", "SUPER_ADMIN"))])
def organization_bootstrap_status(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT b.BootstrapRunID,b.CompanyID,b.TriggerRequirementID,b.TriggerApprovalID,
               b.Status,b.RoleCount,b.CreatedAgentCount,b.ReusedAgentCount,b.CreatedAtUtc,b.CompletedAtUtc
        FROM OrganizationBootstrapRun b ORDER BY b.CreatedAtUtc DESC
    """)).mappings().all()
    return [dict(row) for row in rows]


@router.post("/organization/bootstrap/{requirement_id}", dependencies=[Depends(require_roles("OWNER", "SUPER_ADMIN"))])
def bootstrap_approved_organization(
    requirement_id: UUID,
    body: OrganizationBootstrapRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    requirement = db.execute(text("""
        SELECT RequirementID,Status FROM Requirement WHERE RequirementID=:requirement_id
    """), {"requirement_id": requirement_id}).mappings().first()
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")
    if requirement["Status"] != "Approved":
        raise HTTPException(status_code=409, detail="Requirement must be Approved before organization bootstrap")
    result = OrganizationOrchestrator().bootstrap_approved_company(
        db, requirement_id, body.approval_id
    )
    _audit(db, user, "OrganizationBootstrapRequested", "Requirement", requirement_id, "Explicit Owner/Super Admin retry for approved organization bootstrap")
    db.commit()
    return result


@router.get("/requests", dependencies=[Depends(require_roles("PLATFORM_OWNER", "ADMIN", "OWNER", "SUPER_ADMIN"))])
def list_workforce_requests(db: Session = Depends(get_db)):
    rows = db.execute(text("""
         SELECT wr.WorkforceRequestID, wr.ProjectID, wr.TaskID, wr.RoleCode,
             p.ProjectName,
               rp.PositionName, rp.DepartmentName, rp.JobDescription, rp.RequiredSkillsJson,
               wr.RequestReason, wr.Status, wr.RequestedBy, wr.RequestedAtUtc,
             wr.DecisionBy, wr.DecisionReason, wr.DecisionAtUtc, wr.FilledAgentID,
             wr.ProvisionedAgentID, agent.AgentName AS ProvisionedAgentName,
               agent.Status AS AgentStatus, agent.ModelProvider, agent.Model, agent.ModelVersion,
               CASE WHEN (SELECT TOP 1 e.Passed FROM Evaluation e WHERE e.AgentID=agent.AgentID AND e.EvaluationType='Capability' ORDER BY e.CreatedAtUtc DESC,e.EvaluationID DESC)=1 THEN 1 ELSE 0 END AS CapabilityEvaluationPassed,
               CASE WHEN (SELECT TOP 1 e.Passed FROM Evaluation e WHERE e.AgentID=agent.AgentID AND e.EvaluationType='Safety' ORDER BY e.CreatedAtUtc DESC,e.EvaluationID DESC)=1 THEN 1 ELSE 0 END AS SafetyEvaluationPassed,
               CASE WHEN (SELECT TOP 1 e.Passed FROM Evaluation e WHERE e.AgentID=agent.AgentID AND e.EvaluationType='Security' ORDER BY e.CreatedAtUtc DESC,e.EvaluationID DESC)=1 THEN 1 ELSE 0 END AS SecurityEvaluationPassed,
               CASE WHEN (SELECT TOP 1 e.Passed FROM Evaluation e WHERE e.AgentID=agent.AgentID AND e.EvaluationType='Governance' ORDER BY e.CreatedAtUtc DESC,e.EvaluationID DESC)=1 THEN 1 ELSE 0 END AS GovernanceEvaluationPassed,
               (SELECT COUNT(*) FROM AgentActivationBlocker b WHERE b.AgentID=agent.AgentID AND b.Status='Open') AS OpenActivationBlockerCount,
               (SELECT COUNT(*) FROM AgentSkill s WHERE s.AgentID=agent.AgentID AND s.Status='Pending') AS PendingSkillCount,
               (SELECT b.BlockerCode AS code,b.Description AS description FROM AgentActivationBlocker b WHERE b.AgentID=agent.AgentID AND b.Status='Open' FOR JSON PATH) AS ActivationBlockersJson
        FROM WorkforceRequest wr
        JOIN Project p ON p.ProjectID = wr.ProjectID
        JOIN WorkforceRoleProfile rp ON rp.RoleCode = wr.RoleCode
         LEFT JOIN Agent agent ON agent.AgentID=wr.ProvisionedAgentID
        ORDER BY wr.RequestedAtUtc DESC
    """)).mappings().all()
    return [dict(row) for row in rows]


@router.get("/reuse-assessments", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def list_workforce_reuse_assessments(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT assessment.AssessmentID,assessment.ProjectID,assessment.TaskID,assessment.RoleCode,
               assessment.AgentID,assessment.MatchScore,assessment.Classification,assessment.SkillPlanJson,
               assessment.MissingCertificationsJson,assessment.CapacityAvailable,
               assessment.EstimatedReadinessDays,assessment.AssessmentStatus,assessment.AssessedAtUtc,
               assessment.DecisionBy,assessment.DecisionAtUtc,assessment.DecisionReason,
               project.ProjectName,profile.PositionName,agent.AgentName,agent.Status AS AgentStatus,
               agent.CurrentWorkload,agent.ConcurrentTaskLimit
        FROM dbo.WorkforceReuseAssessment assessment
        JOIN dbo.Project project ON project.ProjectID=assessment.ProjectID
        JOIN dbo.WorkforceRoleProfile profile ON profile.RoleCode=assessment.RoleCode
        JOIN dbo.Agent agent ON agent.AgentID=assessment.AgentID
        WHERE assessment.AssessmentStatus IN ('PendingApproval','Approved','Completed','Assigned')
        ORDER BY CASE assessment.AssessmentStatus WHEN 'PendingApproval' THEN 0 ELSE 1 END,
                 assessment.MatchScore DESC,assessment.AssessedAtUtc DESC
    """)).mappings().all()
    return [dict(row) for row in rows]


@router.get("/reuse-metrics", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def workforce_reuse_metrics(db: Session = Depends(get_db), user=Depends(get_current_user)):
    counts = db.execute(text("""
        SELECT COUNT(DISTINCT CASE WHEN AssessmentStatus IN ('Approved','Completed','Assigned') AND MatchScore>=50
                                   THEN CONCAT(CONVERT(varchar(36),ProjectID),':',RoleCode) END) AS RequestsPrevented,
               COUNT(DISTINCT CASE WHEN Classification='Upskill Candidate'
                                   THEN CONCAT(CONVERT(varchar(36),ProjectID),':',RoleCode,':',CONVERT(varchar(36),AgentID)) END) AS UpskillCandidates,
               COUNT(DISTINCT CASE WHEN AssessmentStatus='Assigned'
                                   THEN AgentID END) AS ReusedAgents,
               SUM(CASE WHEN CompletedAtUtc IS NOT NULL AND Classification='Upskill Candidate' THEN 1 ELSE 0 END) AS UpskillSuccesses,
               SUM(CASE WHEN AssessmentStatus IN ('Approved','Completed','Assigned') AND Classification='Upskill Candidate' THEN 1 ELSE 0 END) AS ApprovedUpskillPlans
        FROM dbo.WorkforceReuseAssessment
    """)).mappings().one()
    request_count = db.execute(text("SELECT COUNT(*) FROM dbo.WorkforceRequest")).scalar_one()
    utilization = db.execute(text("""
        SELECT AVG(CAST(CASE WHEN CurrentWorkload<0 THEN 0 WHEN CurrentWorkload>100 THEN 100
                             ELSE CurrentWorkload END AS float))
        FROM dbo.Agent WHERE Status='Active'
    """)).scalar_one()
    prevented = int(counts["RequestsPrevented"] or 0)
    total_demand_decisions = prevented + int(request_count or 0)
    approved_plans = int(counts["ApprovedUpskillPlans"] or 0)
    return {
        "workforce_requests_prevented": prevented,
        "reused_agents": int(counts["ReusedAgents"] or 0),
        "upskill_candidates": int(counts["UpskillCandidates"] or 0),
        "upskill_success_rate_percent": round(100 * int(counts["UpskillSuccesses"] or 0) / approved_plans, 1) if approved_plans else 0.0,
        "workforce_utilization_percent": round(float(utilization or 0), 1),
        "workforce_reuse_percent": round(100 * prevented / total_demand_decisions, 1) if total_demand_decisions else 0.0,
        "workforce_savings": {
            "estimated_amount": None,
            "currency": None,
            "basis": "Not monetized: no approved role cost or provisioning cost basis is recorded.",
        },
    }


@router.post("/reuse-assessments/{assessment_id}/decision", dependencies=[Depends(require_roles("WORKFORCE_MANAGER"))])
def decide_workforce_reuse_assessment(
    assessment_id: UUID,
    body: WorkforceReuseDecision,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    assessment = db.execute(text("""
        SELECT AssessmentID,MatchScore,AssessmentStatus FROM dbo.WorkforceReuseAssessment WITH (UPDLOCK,ROWLOCK)
        WHERE AssessmentID=:assessment_id
    """), {"assessment_id": assessment_id}).mappings().first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Workforce reuse assessment not found")
    if assessment["AssessmentStatus"] != "PendingApproval":
        raise HTTPException(status_code=409, detail="Reuse assessment is no longer awaiting Workforce Manager review")
    if int(assessment["MatchScore"]) < 50:
        raise HTTPException(status_code=409, detail="Assessments below 50% must follow the new workforce request path")

    status = "Approved" if body.action == "approve" else "Rejected"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.execute(text("""
        UPDATE dbo.WorkforceReuseAssessment
        SET AssessmentStatus=:status,DecisionBy=:decision_by,DecisionAtUtc=:decided_at,DecisionReason=:reason
        WHERE AssessmentID=:assessment_id
    """), {
        "status": status, "decision_by": user["sub"], "decided_at": now,
        "reason": body.reason.strip(), "assessment_id": assessment_id,
    })
    _audit(db, user, f"WorkforceReuse{body.action.title()}", "WorkforceReuseAssessment", assessment_id, body.reason,
           {"match_score": int(assessment["MatchScore"]), "status": status})
    db.commit()
    return {"assessment_id": str(assessment_id), "status": status, "agent_changed": False}


@router.post("/reuse-assessments/{assessment_id}/complete", dependencies=[Depends(require_roles("WORKFORCE_MANAGER"))])
def complete_workforce_upskill_plan(
    assessment_id: UUID,
    body: WorkforceUpskillCompletion,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    assessment = db.execute(text("""
        SELECT AssessmentID,AgentID,RoleCode,AssessmentStatus,Classification
        FROM dbo.WorkforceReuseAssessment WITH (UPDLOCK,ROWLOCK) WHERE AssessmentID=:assessment_id
    """), {"assessment_id": assessment_id}).mappings().first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Workforce reuse assessment not found")
    if assessment["AssessmentStatus"] != "Approved" or assessment["Classification"] != "Upskill Candidate":
        raise HTTPException(status_code=409, detail="Only an approved upskill plan can be completed")
    profile = db.execute(text("""
        SELECT RequiredSkillsJson FROM dbo.WorkforceRoleProfile
        WHERE RoleCode=:role_code AND Status='Active'
    """), {"role_code": assessment["RoleCode"]}).mappings().first()
    skills = {
        row["Name"]: int(row["Proficiency"])
        for row in db.execute(text("""
            SELECT s.Name,MAX(ags.Proficiency) AS Proficiency
            FROM dbo.AgentSkill ags JOIN dbo.Skill s ON s.SkillID=ags.SkillID
            WHERE ags.AgentID=:agent_id AND ags.Status='Active' GROUP BY s.Name
        """), {"agent_id": assessment["AgentID"]}).mappings().all()
    }
    if not profile or not agent_meets_profile(dict(profile), skills):
        raise HTTPException(status_code=409, detail="Required skill proficiency must be actively verified before marking the plan successful")
    if not REQUIRED_AGENT_CERTIFICATIONS.issubset(WorkforcePlanner.latest_passed_evaluation_types(db, assessment["AgentID"])):
        raise HTTPException(status_code=409, detail="Current required certifications must pass before marking the plan successful")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.execute(text("""
        UPDATE dbo.WorkforceReuseAssessment
        SET AssessmentStatus='Completed',CompletedAtUtc=:completed_at,CompletionEvidence=:evidence
        WHERE AssessmentID=:assessment_id
    """), {"completed_at": now, "evidence": body.evidence.strip(), "assessment_id": assessment_id})
    _audit(db, user, "WorkforceUpskillPlanCompleted", "WorkforceReuseAssessment", assessment_id, body.evidence)
    db.commit()
    return {"assessment_id": str(assessment_id), "status": "Completed", "agent_changed": False}


@router.post("/reuse-assessments/{assessment_id}/assign", dependencies=[Depends(require_roles("WORKFORCE_MANAGER"))])
def assign_approved_reuse_candidate(
    assessment_id: UUID,
    body: WorkforceReuseAssignment,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    assessment = db.execute(text("""
        SELECT AssessmentID,ProjectID,TaskID,RoleCode,AgentID,AssessmentStatus,Classification
        FROM dbo.WorkforceReuseAssessment WITH (UPDLOCK,ROWLOCK) WHERE AssessmentID=:assessment_id
    """), {"assessment_id": assessment_id}).mappings().first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Workforce reuse assessment not found")
    allowed_status = "Completed" if assessment["Classification"] == "Upskill Candidate" else "Approved"
    if assessment["AssessmentStatus"] != allowed_status:
        raise HTTPException(status_code=409, detail="The reuse plan must be approved, and upskill plans must be verified complete, before assignment")
    agent = db.execute(text("""
        SELECT AgentID,AgentType,Status,CurrentWorkload,ConcurrentTaskLimit
        FROM dbo.Agent WITH (UPDLOCK,ROWLOCK) WHERE AgentID=:agent_id
    """), {"agent_id": assessment["AgentID"]}).mappings().first()
    if not agent or agent["Status"] != "Active" or agent["AgentType"] == "Executive":
        raise HTTPException(status_code=409, detail="Only a non-executive Active agent can be assigned")
    if float(agent["CurrentWorkload"] or 0) >= 100:
        raise HTTPException(status_code=409, detail="Agent has no available workload capacity")
    active_assignments = db.execute(text("""
        SELECT COUNT(*) FROM dbo.TaskAssignment
        WHERE AgentID=:agent_id AND Status='Active' AND ReleasedAtUtc IS NULL
    """), {"agent_id": agent["AgentID"]}).scalar_one()
    if int(active_assignments or 0) >= int(agent["ConcurrentTaskLimit"] or 1):
        raise HTTPException(status_code=409, detail="Agent has no available concurrent task capacity")
    profile = db.execute(text("""
        SELECT RequiredSkillsJson FROM dbo.WorkforceRoleProfile
        WHERE RoleCode=:role_code AND Status='Active'
    """), {"role_code": assessment["RoleCode"]}).mappings().first()
    skills = {
        row["Name"]: int(row["Proficiency"])
        for row in db.execute(text("""
            SELECT s.Name,MAX(ags.Proficiency) AS Proficiency
            FROM dbo.AgentSkill ags JOIN dbo.Skill s ON s.SkillID=ags.SkillID
            WHERE ags.AgentID=:agent_id AND ags.Status='Active' GROUP BY s.Name
        """), {"agent_id": agent["AgentID"]}).mappings().all()
    }
    if not profile or not agent_meets_profile(dict(profile), skills):
        raise HTTPException(status_code=409, detail="Agent does not have every required skill active at the role proficiency")
    if not REQUIRED_AGENT_CERTIFICATIONS.issubset(WorkforcePlanner.latest_passed_evaluation_types(db, agent["AgentID"])):
        raise HTTPException(status_code=409, detail="Agent does not have all current required certifications")
    task = None
    if assessment["TaskID"]:
        task = db.execute(text("""
            SELECT TaskID,ProjectID,AssignedAgentID FROM dbo.Task WITH (UPDLOCK,ROWLOCK)
            WHERE TaskID=:task_id AND ProjectID=:project_id
        """), {"task_id": assessment["TaskID"], "project_id": assessment["ProjectID"]}).mappings().first()
        if not task or task["AssignedAgentID"]:
            raise HTTPException(status_code=409, detail="The assessed task is missing or already assigned")
    elif assessment["RoleCode"] != "DELIVERY_LEAD":
        raise HTTPException(status_code=409, detail="The assessed role has no assignable task")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if task:
        db.execute(text("UPDATE dbo.Task SET AssignedAgentID=:agent_id WHERE TaskID=:task_id"), {
            "agent_id": agent["AgentID"], "task_id": task["TaskID"],
        })
        db.execute(text("""
            INSERT dbo.TaskAssignment(TaskAssignmentID,TaskID,AgentID,AssignedAtUtc,Status)
            VALUES(:assignment_id,:task_id,:agent_id,:assigned_at,'Active')
        """), {
            "assignment_id": uuid.uuid4(), "task_id": task["TaskID"],
            "agent_id": agent["AgentID"], "assigned_at": now,
        })
    if assessment["RoleCode"] == "DELIVERY_LEAD":
        db.execute(text("""
            IF NOT EXISTS (SELECT 1 FROM dbo.ProjectAgent WHERE ProjectID=:project_id AND AgentID=:agent_id)
                INSERT dbo.ProjectAgent(ProjectID,AgentID,ProjectRole,AssignedAtUtc)
                VALUES(:project_id,:agent_id,'Delivery Lead',:assigned_at)
        """), {"project_id": assessment["ProjectID"], "agent_id": agent["AgentID"], "assigned_at": now})
    db.execute(text("""
        UPDATE dbo.WorkforceReuseAssessment SET AssessmentStatus='Assigned'
        WHERE AssessmentID=:assessment_id
    """), {"assessment_id": assessment_id})
    _audit(db, user, "WorkforceReuseAgentAssigned", "WorkforceReuseAssessment", assessment_id, body.reason,
           {"agent_id": str(agent["AgentID"]), "task_id": str(task["TaskID"]) if task else None})
    db.commit()
    return {
        "assessment_id": str(assessment_id), "agent_id": str(agent["AgentID"]),
        "task_id": str(task["TaskID"]) if task else None, "status": "Assigned", "activated": False,
    }


@router.get("/activation-blockers", dependencies=[Depends(require_roles("ADMIN", "OWNER", "SUPER_ADMIN"))])
def list_activation_blockers(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT b.BlockerID,b.AgentID,a.AgentName,a.WorkforceRoleCode,b.BlockerCode,
               b.Description,b.Status,b.FirstDetectedAtUtc,b.LastDetectedAtUtc,b.ResolvedAtUtc
        FROM AgentActivationBlocker b JOIN Agent a ON a.AgentID=b.AgentID
        WHERE b.Status='Open'
        ORDER BY b.LastDetectedAtUtc DESC
    """)).mappings().all()
    return [dict(row) for row in rows]


@router.get("/candidates", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def list_role_candidates(
    role_code: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    profile = db.execute(text("""
        SELECT RoleCode, RequiredSkillsJson FROM WorkforceRoleProfile
        WHERE RoleCode=:role_code AND Status='Active'
    """), {"role_code": role_code}).mappings().first()
    if not profile:
        raise HTTPException(status_code=404, detail="Workforce role profile not found")
    agents = db.execute(text("""
        SELECT a.AgentID, a.AgentName, a.AgentType, a.WorkforceRoleCode,
               a.CurrentWorkload, a.ConcurrentTaskLimit,
               COUNT(CASE WHEN ta.ReleasedAtUtc IS NULL AND ta.Status='Active' THEN 1 END) AS ActiveAssignments
        FROM Agent a LEFT JOIN TaskAssignment ta ON ta.AgentID=a.AgentID
        WHERE a.Status='Active'
        GROUP BY a.AgentID, a.AgentName, a.AgentType, a.WorkforceRoleCode,
                 a.CurrentWorkload, a.ConcurrentTaskLimit
        ORDER BY a.CurrentWorkload, a.AgentName
    """)).mappings().all()
    skills_by_agent = {}
    for row in db.execute(text("""
        SELECT ags.AgentID, s.Name AS SkillName, MAX(ags.Proficiency) AS Proficiency
        FROM AgentSkill ags JOIN Skill s ON s.SkillID=ags.SkillID
        WHERE ags.Status='Active' GROUP BY ags.AgentID, s.Name
    """)).mappings().all():
        skills_by_agent.setdefault(row["AgentID"], {})[row["SkillName"]] = int(row["Proficiency"])

    from app.services.workforce_planner import WorkforcePlanner, agent_meets_profile
    certified_agents = WorkforcePlanner.certified_agent_ids(db)
    eligible = []
    for agent in agents:
        if (agent["AgentType"] == "Executive"
                or agent["WorkforceRoleCode"] != role_code
                or agent["AgentID"] not in certified_agents
                or int(agent["ActiveAssignments"] or 0) >= int(agent["ConcurrentTaskLimit"] or 1)
                or float(agent["CurrentWorkload"] or 0) >= 100
                or not agent_meets_profile(dict(profile), skills_by_agent.get(agent["AgentID"], {}))):
            continue
        eligible.append({
            "agent_id": str(agent["AgentID"]),
            "agent_name": agent["AgentName"],
            "current_workload": float(agent["CurrentWorkload"] or 0),
            "active_assignments": int(agent["ActiveAssignments"] or 0),
            "concurrent_task_limit": int(agent["ConcurrentTaskLimit"] or 1),
        })
    return eligible


@router.post("/requests/{request_id}/decision", dependencies=[Depends(require_roles("APPROVER", "PLATFORM_OWNER"))])
def decide_workforce_request(
    request_id: UUID,
    body: WorkforceDecision,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    request_row = db.execute(text("""
        SELECT WorkforceRequestID, ProjectID, TaskID, RoleCode, Status, ProvisionedAgentID
        FROM WorkforceRequest WITH (UPDLOCK, ROWLOCK)
        WHERE WorkforceRequestID = :request_id
    """), {"request_id": request_id}).mappings().first()
    if not request_row:
        raise HTTPException(status_code=404, detail="Workforce request not found")
    if request_row["Status"] != "PendingApproval":
        raise HTTPException(status_code=409, detail="Workforce request is no longer awaiting a decision")

    status = "Recruiting" if body.action == "approve_recruiting" else "Rejected"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.execute(text("""
        UPDATE WorkforceRequest SET Status=:status, DecisionBy=:decision_by,
            DecisionReason=:reason, DecisionAtUtc=:decided_at
        WHERE WorkforceRequestID=:request_id
    """), {
        "status": status, "decision_by": user["sub"], "reason": body.reason.strip(),
        "decided_at": now, "request_id": request_id,
    })
    provisioned_agent_id = None
    if body.action == "approve_recruiting":
        workforce_request = dict(request_row)
        workforce_request["Status"] = "Recruiting"
        provisioned_agent_id = WorkforcePlanner.provision_agent(db, workforce_request, user["sub"])
        status = "Provisioning"
        _audit(db, user, "WorkforceAgentProvisioned", "Agent", provisioned_agent_id, "Created from approved role profile in non-active Provisioning state")
    _audit(db, user, f"WorkforceRequest{body.action.title()}", "WorkforceRequest", request_id, body.reason)
    db.commit()
    return {
        "request_id": str(request_id),
        "status": status,
        "agent_id": str(provisioned_agent_id) if provisioned_agent_id else None,
        "message": "A non-active agent record was created in Provisioning. Configure its approved provider and pass capability/safety evaluations before activation." if provisioned_agent_id else "Workforce request rejected.",
    }


@router.post("/requests/{request_id}/provision", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def provision_approved_role(
    request_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    request_row = db.execute(text("""
        SELECT WorkforceRequestID, ProjectID, TaskID, RoleCode, Status, ProvisionedAgentID
        FROM WorkforceRequest WITH (UPDLOCK, ROWLOCK)
        WHERE WorkforceRequestID=:request_id
    """), {"request_id": request_id}).mappings().first()
    if not request_row:
        raise HTTPException(status_code=404, detail="Workforce request not found")
    if request_row["ProvisionedAgentID"]:
        return {"request_id": str(request_id), "agent_id": str(request_row["ProvisionedAgentID"]), "status": request_row["Status"], "idempotent": True}
    agent_id = WorkforcePlanner.provision_agent(db, request_row, user["sub"])
    _audit(db, user, "WorkforceAgentProvisioned", "Agent", agent_id, "Agent created in non-active Provisioning state from approved role profile")
    db.commit()
    return {"request_id": str(request_id), "agent_id": str(agent_id), "status": "Provisioning", "active": False}


@router.post("/requests/{request_id}/activate", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def activate_provisioned_role(
    request_id: UUID,
    body: WorkforceActivation,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    request_row = db.execute(text("""
        SELECT WorkforceRequestID, ProjectID, TaskID, RoleCode, Status, ProvisionedAgentID
        FROM WorkforceRequest WITH (UPDLOCK, ROWLOCK)
        WHERE WorkforceRequestID=:request_id
    """), {"request_id": request_id}).mappings().first()
    if not request_row:
        raise HTTPException(status_code=404, detail="Workforce request not found")
    agent = db.execute(text("""
        SELECT AgentID, ModelProvider, Model, ModelVersion, Status, WorkforceRoleCode
        FROM Agent WHERE AgentID=:agent_id
    """), {"agent_id": request_row["ProvisionedAgentID"]}).mappings().first()
    if not agent:
        raise HTTPException(status_code=409, detail="No provisioned Agent record is linked to this role request")
    blocker_messages = WorkforcePlanner.agent_readiness_blockers(db, dict(agent))
    if blocker_messages:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        blocker_codes = []
        for description in blocker_messages:
            code = re.sub(r"[^A-Z0-9]+", "_", description.split(":", 1)[0].strip().upper()).strip("_")
            blocker_codes.append(code)
            existing = db.execute(text("""
                SELECT BlockerID FROM AgentActivationBlocker
                WHERE AgentID=:agent_id AND BlockerCode=:code AND Status='Open'
            """), {"agent_id": agent["AgentID"], "code": code}).scalar_one_or_none()
            if existing:
                db.execute(text("UPDATE AgentActivationBlocker SET LastDetectedAtUtc=:now WHERE BlockerID=:id"), {
                    "now": now, "id": existing,
                })
                continue
            blocker_id = uuid.uuid4()
            db.execute(text("""
                INSERT AgentActivationBlocker
                    (BlockerID,AgentID,BlockerCode,Description,Status,FirstDetectedAtUtc,LastDetectedAtUtc)
                VALUES(:id,:agent_id,:code,:description,'Open',:now,:now)
            """), {"id": blocker_id, "agent_id": agent["AgentID"], "code": code, "description": description, "now": now})
            for recipient_id in db.execute(text("""
                SELECT u.UserID FROM AppUser u JOIN Role r ON r.RoleID=u.RoleID
                WHERE u.IsActive=1 AND r.IsActive=1 AND r.RoleCode IN ('OWNER','SUPER_ADMIN')
            """)).scalars().all():
                db.execute(text("""
                    INSERT Notification
                        (NotificationID,UserID,NotificationType,Title,Body,ResourceType,ResourceID,CorrelationID,IsRead,CreatedAtUtc)
                    VALUES(:notification_id,:user_id,'AGENT_ACTIVATION_BLOCKED','Agent activation blocked',
                           'An agent is not activation-ready. Review the activation blocker record.',
                           'Agent',:resource_id,:correlation_id,0,:created_at)
                """), {
                    "notification_id": uuid.uuid4(), "user_id": recipient_id,
                    "resource_id": str(agent["AgentID"]), "correlation_id": uuid.uuid4(), "created_at": now,
                })
        _audit(db, user, "AgentActivationBlocked", "Agent", agent["AgentID"], body.reason)
        db.commit()
        raise HTTPException(
            status_code=409,
            detail={"message": "Agent activation is blocked; Owner notifications and blocker records were created.", "blockers": blocker_messages, "blocker_codes": blocker_codes},
        )

    agent_id, plan = WorkforcePlanner.activate_provisioned_agent(
        db, request_row, user["sub"], body.reason
    )
    _audit(db, user, "WorkforceAgentActivated", "Agent", agent_id, body.reason)
    db.commit()
    return {
        "request_id": str(request_id),
        "agent_id": str(agent_id),
        "status": "AgentActive",
        "project_plan": plan,
        "execution_started": False,
        "message": "Qualified role tasks were queued. This application has no agent execution runtime yet.",
    }


@router.post("/requests/{request_id}/fill", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def fill_workforce_request(
    request_id: UUID,
    body: WorkforceFill,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    request_row = db.execute(text("""
        SELECT WorkforceRequestID, ProjectID, TaskID, RoleCode, Status
        FROM WorkforceRequest WITH (UPDLOCK, ROWLOCK)
        WHERE WorkforceRequestID = :request_id
    """), {"request_id": request_id}).mappings().first()
    if not request_row:
        raise HTTPException(status_code=404, detail="Workforce request not found")
    if request_row["Status"] not in {"Recruiting", "CandidateReady"}:
        raise HTTPException(status_code=409, detail="Authorize recruiting and complete agent validation before filling this role")

    task_count = WorkforcePlanner.assign_request_to_agent(
        db, request_row, body.agent_id, user["sub"], body.reason.strip()
    )
    _audit(db, user, "WorkforceRequestFilled", "WorkforceRequest", request_id, body.reason)
    db.commit()
    return {"request_id": str(request_id), "status": "Filled", "agent_id": str(body.agent_id), "tasks_assigned": task_count}


@router.post("/projects/{project_id}/plan", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def plan_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    project = db.execute(text("""
        SELECT p.ProjectID, p.RequirementID, p.Status, r.RequirementID AS ExistingRequirementID,
               r.CreatedBy, r.Priority, r.RiskLevel, r.Title, r.Description, r.RequestedBy
        FROM Project p WITH (UPDLOCK, HOLDLOCK)
        JOIN Requirement r ON r.RequirementID = p.RequirementID
        WHERE p.ProjectID = :project_id
    """), {"project_id": project_id}).mappings().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project["Status"] not in {"Planned", "InProgress"}:
        raise HTTPException(status_code=409, detail="Only planned or in-progress projects can be replanned")

    result = WorkforcePlanner().auto_assign_agents(db, project_id, project)
    result["queue"] = queue_pending_tasks(db, project_id, user["sub"])
    _audit(db, user, "ProjectWorkforcePlanned", "Project", project_id, "Planning run; no dates or unqualified assignments invented")
    db.commit()
    return result


@router.patch("/tasks/{task_id}/status", dependencies=[Depends(require_roles("ADMIN", "OWNER", "SUPER_ADMIN"))])
def change_task_status(
    task_id: UUID,
    body: TaskStatusChange,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    task = db.execute(text("""
        SELECT t.TaskID, t.ProjectID, t.Status, t.AssignedAgentID,
               p.Status AS ProjectStatus, p.RequirementID
        FROM Task t WITH (UPDLOCK, ROWLOCK)
        JOIN Project p ON p.ProjectID = t.ProjectID
        WHERE t.TaskID = :task_id
    """), {"task_id": task_id}).mappings().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    current = task["Status"]
    allowed = {
        "Planned": {"InProgress", "Blocked"},
        "InProgress": {"Completed", "Blocked", "Planned"},
        "Blocked": {"Planned", "InProgress"},
        "Completed": set(),
    }
    if body.status not in allowed.get(current, set()):
        raise HTTPException(status_code=409, detail=f"Cannot move task from {current} to {body.status}")
    if body.status == "InProgress":
        if not task["AssignedAgentID"]:
            raise HTTPException(status_code=409, detail="Task must have a qualified active agent before it can start")
        incomplete_dependency = db.execute(text("""
            SELECT 1 FROM TaskDependency d JOIN Task prerequisite ON prerequisite.TaskID=d.DependsOnTaskID
            WHERE d.TaskID=:task_id AND prerequisite.Status <> 'Completed'
        """), {"task_id": task_id}).first()
        if incomplete_dependency:
            raise HTTPException(status_code=409, detail="Complete prerequisite tasks before starting this task")
        active_agent = db.execute(text("SELECT 1 FROM Agent WHERE AgentID=:agent_id AND Status='Active'"), {
            "agent_id": task["AssignedAgentID"],
        }).first()
        if not active_agent:
            raise HTTPException(status_code=409, detail="Assigned agent is not active")
        delivery_lead = db.execute(text("""
            SELECT 1 FROM ProjectAgent pa JOIN Agent a ON a.AgentID=pa.AgentID
            WHERE pa.ProjectID=:project_id AND pa.ProjectRole='Delivery Lead' AND a.Status='Active'
        """), {"project_id": task["ProjectID"]}).first()
        if not delivery_lead:
            raise HTTPException(status_code=409, detail="A qualified active Delivery Lead must be assigned before project work starts")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.execute(text("""
        UPDATE Task SET Status=:status,
            CompletedAtUtc=CASE WHEN :status='Completed' THEN :now ELSE NULL END,
            ModifiedAtUtc=:now, ModifiedBy=:actor
        WHERE TaskID=:task_id
    """), {"status": body.status, "now": now, "actor": user["sub"], "task_id": task_id})
    if body.status == "Completed":
        db.execute(text("""
            UPDATE TaskAssignment SET Status='Released', ReleasedAtUtc=:released_at
            WHERE TaskID=:task_id AND ReleasedAtUtc IS NULL
        """), {"released_at": now, "task_id": task_id})
    elif body.status == "Planned":
        db.execute(text("""
            UPDATE TaskAssignment SET Status='Released', ReleasedAtUtc=:released_at
            WHERE TaskID=:task_id AND ReleasedAtUtc IS NULL
        """), {"released_at": now, "task_id": task_id})
        db.execute(text("UPDATE Task SET AssignedAgentID=NULL WHERE TaskID=:task_id"), {"task_id": task_id})

    project_status = "InProgress" if body.status == "InProgress" else task["ProjectStatus"]
    if body.status == "Completed":
        remaining = db.execute(text("SELECT 1 FROM Task WHERE ProjectID=:project_id AND Status <> 'Completed'"), {
            "project_id": task["ProjectID"],
        }).first()
        project_status = "InProgress" if remaining else "Completed"
    db.execute(text("UPDATE Project SET Status=:status WHERE ProjectID=:project_id"), {
        "status": project_status, "project_id": task["ProjectID"],
    })
    _audit(db, user, f"Task{body.status}", "Task", task_id, body.reason)

    if body.status == "Completed" and project_status != "Completed":
        from app.models.entities import Requirement
        requirement = db.get(Requirement, task["RequirementID"])
        WorkforcePlanner().plan_project(db, task["ProjectID"], requirement)

    db.commit()
    return {"task_id": str(task_id), "status": body.status, "project_status": project_status}


@router.get("/agent-readiness", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def agent_readiness(db: Session = Depends(get_db), user=Depends(get_current_user)):
    roles = db.execute(text("""
        SELECT RoleCode,PositionName,RequiredSkillsJson
        FROM WorkforceRoleProfile WHERE Status='Active' ORDER BY PositionName
    """)).mappings().all()
    agent_rows = db.execute(text("""
         SELECT a.AgentID,a.AgentName,a.AgentType,a.WorkforceRoleCode,a.Status,a.ModelProvider,a.Model,a.ModelVersion,
               a.CurrentWorkload,a.ConcurrentTaskLimit,a.DepartmentID,a.PositionID,
             rp.Status AS RoleProfileStatus,rp.RequiredSkillsJson,
               (SELECT COUNT(*) FROM dbo.TaskAssignment ta WHERE ta.AgentID=a.AgentID
                    AND ta.Status='Active' AND ta.ReleasedAtUtc IS NULL) AS ActiveAssignments,
               (SELECT COUNT(*) FROM dbo.AgentExecution e WHERE e.AgentID=a.AgentID AND e.Status='Executing') AS RunningExecutions,
               (SELECT TOP 1 wr.WorkforceRequestID FROM dbo.WorkforceRequest wr
                    WHERE wr.ProvisionedAgentID=a.AgentID AND wr.Status='Provisioning'
                    ORDER BY wr.RequestedAtUtc DESC) AS ProvisioningRequestID
        FROM dbo.Agent a
        LEFT JOIN dbo.WorkforceRoleProfile rp ON rp.RoleCode=a.WorkforceRoleCode
        ORDER BY a.Status,a.AgentName
    """)).mappings().all()
    skill_rows = db.execute(text("""
        SELECT ags.AgentID,s.SkillID,s.Name,ags.Proficiency,ags.Status
        FROM dbo.AgentSkill ags JOIN dbo.Skill s ON s.SkillID=ags.SkillID
        ORDER BY s.Name
    """)).mappings().all()
    evaluation_rows = db.execute(text("""
        SELECT e.AgentID,e.EvaluationType,e.Passed,MAX(e.CreatedAtUtc) AS EvaluatedAtUtc
        FROM dbo.Evaluation e
        GROUP BY e.AgentID,e.EvaluationType,e.Passed
    """)).mappings().all()
    skills_catalog = db.execute(text("""
        SELECT SkillID,Name,Description,RiskLevel FROM dbo.Skill
        WHERE Status='Approved' ORDER BY Name
    """)).mappings().all()
    skills_by_agent = {}
    for row in skill_rows:
        skills_by_agent.setdefault(row["AgentID"], []).append({
            "skill_id": str(row["SkillID"]), "name": row["Name"],
            "proficiency": int(row["Proficiency"]), "status": row["Status"],
        })
    evaluations_by_agent = {}
    for row in evaluation_rows:
        prior = evaluations_by_agent.setdefault(row["AgentID"], {})
        current = prior.get(row["EvaluationType"])
        if current is None or row["EvaluatedAtUtc"] > current["evaluated_at_utc"]:
            prior[row["EvaluationType"]] = {
                "passed": bool(row["Passed"]), "evaluated_at_utc": row["EvaluatedAtUtc"]
            }
    agents = []
    for row in agent_rows:
        current_skills = skills_by_agent.get(row["AgentID"], [])
        certifications = evaluations_by_agent.get(row["AgentID"], {})
        active_skill_levels = {item["name"]: item["proficiency"] for item in current_skills if item["status"] == "Active"}
        required_skills = json.loads(row["RequiredSkillsJson"] or "[]") if row["RoleProfileStatus"] == "Active" else []
        skill_gaps = [
            {"skill": item["name"], "required_proficiency": int(item["minimum_proficiency"]),
             "active_proficiency": active_skill_levels.get(item["name"], 0)}
            for item in required_skills
            if active_skill_levels.get(item["name"], 0) < int(item["minimum_proficiency"])
        ]
        missing_certifications = [
            name for name in ("Capability", "Safety", "Security", "Governance")
            if not certifications.get(name, {}).get("passed", False)
        ]
        limit = int(row["ConcurrentTaskLimit"] or 1)
        active_assignments = int(row["ActiveAssignments"] or 0)
        workload = min(max(float(row["CurrentWorkload"] or 0), 0), 100)
        agents.append({
            "agent_id": str(row["AgentID"]), "name": row["AgentName"],
            "agent_type": row["AgentType"], "role_code": row["WorkforceRoleCode"],
            "role_profile_status": row["RoleProfileStatus"], "status": row["Status"],
            "model_provider": row["ModelProvider"], "model": row["Model"],
            "model_version": row["ModelVersion"], "current_workload_percent": workload,
            "concurrent_task_limit": limit, "active_assignments": active_assignments,
            "available_task_slots": max(limit-active_assignments, 0) if row["Status"] == "Active" else 0,
            "available_hours_estimate": round(40 * (100-workload) / 100, 1) if row["Status"] == "Active" else 0,
            "capacity_basis": "Estimated from CurrentWorkload assuming 40 hours per work week; confirm with workforce owner.",
            "running_executions": int(row["RunningExecutions"] or 0),
            "skills": current_skills, "certifications": certifications,
            "required_skills": required_skills, "skill_gaps": skill_gaps,
            "certification_gaps": missing_certifications,
            "provisioning_request_id": str(row["ProvisioningRequestID"]) if row["ProvisioningRequestID"] else None,
        })
    skills_index = {}
    for agent in agents:
        active = {item["name"]: item["proficiency"] for item in agent["skills"] if item["status"] == "Active"}
        if agent["status"] != "Active":
            continue
        for role in roles:
            for required in json.loads(role["RequiredSkillsJson"] or "[]"):
                skill = required["name"]
                entry = skills_index.setdefault(skill, {"skill": skill, "required_roles": set(), "qualified_agents": []})
                entry["required_roles"].add(role["RoleCode"])
                if active.get(skill, 0) >= int(required.get("minimum_proficiency", 1)) and agent["available_task_slots"] > 0:
                    entry["qualified_agents"].append(agent["name"])
    skill_gaps = [
        {"skill": item["skill"], "required_roles": sorted(item["required_roles"]),
         "qualified_agent_count": len(item["qualified_agents"]), "available_agents": item["qualified_agents"]}
        for item in skills_index.values()
    ]
    return {
        "organization_scope": "single_organization",
        "agents": agents,
        "skills_catalog": [dict(row) for row in skills_catalog],
        "required_skills": skill_gaps,
        "available_agents": sum(row["status"] == "Active" and row["available_task_slots"] > 0 for row in agents),
        "skill_gaps": [row for row in skill_gaps if row["qualified_agent_count"] == 0],
        "certification_gap_count": sum(bool(row["certification_gaps"]) for row in agents),
    }


@router.get("/capacity", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def agent_capacity(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT a.AgentID,a.AgentName,a.Status,a.CurrentWorkload,a.ConcurrentTaskLimit,
               COUNT(CASE WHEN ta.Status='Active' AND ta.ReleasedAtUtc IS NULL THEN 1 END) AS ActiveAssignments,
               COALESCE(SUM(CASE WHEN t.Status IN ('Planned','Queued','InProgress') THEN t.EstimatedEffortHours ELSE 0 END),0) AS OpenEstimatedHours,
               COALESCE(SUM(CASE WHEN t.Status='InProgress' THEN t.EstimatedEffortHours ELSE 0 END),0) AS InProgressEstimatedHours
        FROM dbo.Agent a
        LEFT JOIN dbo.TaskAssignment ta ON ta.AgentID=a.AgentID AND ta.Status='Active' AND ta.ReleasedAtUtc IS NULL
        LEFT JOIN dbo.Task t ON t.TaskID=ta.TaskID
        GROUP BY a.AgentID,a.AgentName,a.Status,a.CurrentWorkload,a.ConcurrentTaskLimit
        ORDER BY a.AgentName
    """)).mappings().all()
    result = []
    for row in rows:
        workload = min(max(float(row["CurrentWorkload"] or 0), 0), 100)
        capacity_limit = int(row["ConcurrentTaskLimit"] or 1)
        assignments = int(row["ActiveAssignments"] or 0)
        result.append({
            "agent_id": str(row["AgentID"]), "agent_name": row["AgentName"],
            "status": row["Status"], "utilization_percent": workload,
            "active_assignments": assignments,
            "available_task_slots": max(capacity_limit-assignments, 0) if row["Status"] == "Active" else 0,
            "weekly_capacity_hours": 40,
            "estimated_available_hours": round(40*(100-workload)/100, 1) if row["Status"] == "Active" else 0,
            "open_estimated_task_hours": float(row["OpenEstimatedHours"] or 0),
            "in_progress_estimated_task_hours": float(row["InProgressEstimatedHours"] or 0),
            "forecast_basis": "Available hours assume 40 hours/week scaled by CurrentWorkload; task forecasts include persisted estimates only.",
        })
    return {"organization_scope": "single_organization", "agents": result}


@router.put("/agents/{agent_id}/model", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def configure_agent_model(
    agent_id: UUID,
    body: AgentModelConfiguration,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    agent = db.execute(text("""
        SELECT AgentID,Status FROM dbo.Agent WITH (UPDLOCK,ROWLOCK)
        WHERE AgentID=:agent_id
    """), {"agent_id": agent_id}).mappings().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent["Status"] != "Provisioning":
        raise HTTPException(status_code=409, detail="Model configuration is only editable while the agent is Provisioning")
    catalog = db.execute(text("""
        SELECT m.ModelName,m.ModelVersion,p.ProviderName
        FROM dbo.AIModelCatalog m JOIN dbo.AIModelProvider p ON p.ProviderID=m.ProviderID
        WHERE m.ModelCatalogID=:catalog_id AND m.Status='Approved' AND p.Status='Active'
    """), {"catalog_id": body.model_catalog_id}).mappings().first()
    if not catalog:
        raise HTTPException(status_code=422, detail="Select an Approved model from the AI model catalog")
    db.execute(text("""
        UPDATE dbo.Agent SET ModelProvider=:provider,Model=:model,ModelVersion=:version,
            ModifiedBy=:actor,ModifiedDate=SYSUTCDATETIME()
        WHERE AgentID=:agent_id
    """), {
        "provider": catalog["ProviderName"],
        "model": catalog["ModelName"],
        "version": catalog["ModelVersion"],
        "actor": user["sub"],
        "agent_id": agent_id,
    })
    _audit(db, user, "AgentModelConfigured", "Agent", agent_id, body.reason,
           {"model_catalog_id": str(body.model_catalog_id)})
    db.commit()
    return {
        "agent_id": str(agent_id), "provider": catalog["ProviderName"],
        "model": catalog["ModelName"], "model_version": catalog["ModelVersion"],
        "status": agent["Status"],
    }


@router.post("/agents/{agent_id}/evaluations", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def record_agent_evaluation(
    agent_id: UUID,
    body: AgentEvaluationRecord,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    agent = db.execute(text("""
        SELECT AgentID,Status,WorkforceRoleCode FROM dbo.Agent WITH (UPDLOCK,ROWLOCK)
        WHERE AgentID=:agent_id
    """), {"agent_id": agent_id}).mappings().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent["Status"] != "Provisioning":
        raise HTTPException(status_code=409, detail="Certification evaluations can only be recorded before activation")
    template = db.execute(text("""
        SELECT TemplateID,TemplateCode,TemplateName,Version
        FROM dbo.EvaluationTemplate WHERE TemplateCode=:code AND Status='Active'
    """), {"code": body.template_code}).mappings().first()
    if not template:
        raise HTTPException(status_code=404, detail="Active evaluation template not found")
    required_criteria = db.execute(text("""
        SELECT CriterionCode,CriterionName,IsRequired FROM dbo.EvaluationTemplateCriterion
        WHERE TemplateID=:template_id ORDER BY SequenceNumber
    """), {"template_id": template["TemplateID"]}).mappings().all()
    supplied = {criterion.criterion_code: criterion for criterion in body.criteria}
    required_codes = {row["CriterionCode"] for row in required_criteria if row["IsRequired"]}
    if len(supplied) != len(body.criteria) or set(supplied) != required_codes:
        raise HTTPException(status_code=422, detail={
            "message": "Submit exactly one result for every required template criterion.",
            "required_criteria": sorted(required_codes),
        })
    score = sum(item.score for item in supplied.values()) / len(supplied)
    passed = score >= 70 and all(item.score >= 70 for item in supplied.values())
    evidence = json.dumps({
        "template_id": str(template["TemplateID"]), "template_code": template["TemplateCode"],
        "template_name": template["TemplateName"], "template_version": template["Version"],
        "reviewer_user_id": user["sub"], "reason": body.reason.strip(),
        "criteria": [item.model_dump() for item in body.criteria],
        "pass_threshold": 70,
    }, ensure_ascii=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.execute(text("""
        INSERT INTO dbo.Evaluation
            (EvaluationID,AgentID,TaskID,EvaluationType,Score,Passed,Evidence,CreatedAtUtc)
        VALUES(:evaluation_id,:agent_id,NULL,:evaluation_type,:score,:passed,:evidence,:created_at)
    """), {
        "evaluation_id": uuid.uuid4(), "agent_id": agent_id,
        "evaluation_type": template["TemplateName"].replace(" Review", ""), "score": score,
        "passed": passed, "evidence": evidence, "created_at": now,
    })
    _audit(db, user, f"Agent{template['TemplateCode']}EvaluationRecorded", "Agent", agent_id, body.reason,
           {"template_id": str(template["TemplateID"]), "score": score, "passed": passed})
    db.commit()
    return {
        "agent_id": str(agent_id), "evaluation_type": template["TemplateName"].replace(" Review", ""),
        "template_code": template["TemplateCode"], "score": score, "passed": passed,
        "reviewer_user_id": user["sub"], "created_at_utc": now.isoformat(),
    }


@router.post("/agents/{agent_id}/skills", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def change_agent_skill(
    agent_id: UUID,
    body: AgentSkillChange,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    agent_id = db.execute(text("""
        SELECT AgentID FROM dbo.Agent WHERE AgentID=:agent_id
    """), {"agent_id": agent_id}).scalar_one_or_none()
    if not agent_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    skill = db.execute(text("""
        SELECT SkillID,Name FROM dbo.Skill WHERE SkillID=:skill_id AND Status='Approved'
    """), {"skill_id": body.skill_id}).mappings().first()
    if not skill:
        raise HTTPException(status_code=404, detail="Approved skill not found")
    existing = db.execute(text("""
        SELECT Status FROM dbo.AgentSkill WHERE AgentID=:agent_id AND SkillID=:skill_id
    """), {"agent_id": agent_id, "skill_id": body.skill_id}).mappings().first()
    if body.action == "assign":
        if existing:
            db.execute(text("""
                UPDATE dbo.AgentSkill SET Proficiency=:proficiency,Status='Pending'
                WHERE AgentID=:agent_id AND SkillID=:skill_id
            """), {"proficiency": body.proficiency, "agent_id": agent_id, "skill_id": body.skill_id})
        else:
            db.execute(text("""
                INSERT dbo.AgentSkill(AgentID,SkillID,Proficiency,Status)
                VALUES(:agent_id,:skill_id,:proficiency,'Pending')
            """), {"agent_id": agent_id, "skill_id": body.skill_id, "proficiency": body.proficiency})
        next_status = "Pending"
    elif body.action == "approve":
        if not existing or existing["Status"] != "Pending":
            raise HTTPException(status_code=409, detail="Only a Pending skill assignment can be approved")
        db.execute(text("""
            UPDATE dbo.AgentSkill SET Proficiency=:proficiency,Status='Active'
            WHERE AgentID=:agent_id AND SkillID=:skill_id
        """), {"proficiency": body.proficiency, "agent_id": agent_id, "skill_id": body.skill_id})
        next_status = "Active"
    else:
        if not existing:
            raise HTTPException(status_code=404, detail="Agent skill assignment not found")
        db.execute(text("""
            UPDATE dbo.AgentSkill SET Status='Revoked'
            WHERE AgentID=:agent_id AND SkillID=:skill_id
        """), {"agent_id": agent_id, "skill_id": body.skill_id})
        next_status = "Revoked"
    _audit(db, user, f"AgentSkill{body.action.title()}", "Agent", agent_id, body.reason, {
        "evidence": body.evidence.strip(), "skill_id": str(body.skill_id),
        "proficiency": body.proficiency,
    })
    db.commit()
    return {"agent_id": str(agent_id), "skill_id": str(body.skill_id), "skill": skill["Name"], "status": next_status}


@router.post("/agents/{agent_id}/deactivate", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def deactivate_agent(
    agent_id: UUID,
    body: AgentStatusChange,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    agent = db.execute(text("""
        SELECT AgentID,Status FROM dbo.Agent WITH (UPDLOCK,ROWLOCK)
        WHERE AgentID=:agent_id
    """), {"agent_id": agent_id}).mappings().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    active_work = db.execute(text("""
        SELECT 1
        WHERE EXISTS (
            SELECT 1 FROM dbo.TaskAssignment ta
            WHERE ta.AgentID=:agent_id AND ta.Status='Active' AND ta.ReleasedAtUtc IS NULL
        ) OR EXISTS (
            SELECT 1 FROM dbo.AgentExecution e WHERE e.AgentID=:agent_id AND e.Status='Executing'
        )
    """), {"agent_id": agent_id}).first()
    if active_work:
        raise HTTPException(status_code=409, detail="Agent has active assignments or executions; release or resolve them before deactivation")
    db.execute(text("UPDATE dbo.Agent SET Status='Inactive',ModifiedBy=:actor WHERE AgentID=:agent_id"), {
        "actor": user["sub"], "agent_id": agent_id,
    })
    db.execute(text("""
        UPDATE dbo.AgentRuntimeCredential SET Status='Revoked',RevokedAtUtc=SYSUTCDATETIME()
        WHERE AgentID=:agent_id AND Status='Active'
    """), {"agent_id": agent_id})
    _audit(db, user, "AgentDeactivated", "Agent", agent_id, body.reason)
    db.commit()
    return {"agent_id": str(agent_id), "status": "Inactive"}


@router.post("/agents/{agent_id}/activate", dependencies=[Depends(require_roles("WORKFORCE_MANAGER", "PLATFORM_OWNER"))])
def activate_ready_agent(
    agent_id: UUID,
    body: AgentStatusChange,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    agent = db.execute(text("""
        SELECT AgentID,Status,WorkforceRoleCode,ModelProvider,Model,ModelVersion
        FROM dbo.Agent WITH (UPDLOCK,ROWLOCK)
        WHERE AgentID=:agent_id
    """), {"agent_id": agent_id}).mappings().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent["Status"] != "Provisioning":
        raise HTTPException(status_code=409, detail="Only Provisioning agents can be activated through certification review")
    blockers = WorkforcePlanner.agent_readiness_blockers(db, dict(agent))
    if blockers:
        _audit(db, user, "AgentActivationBlocked", "Agent", agent_id, body.reason)
        db.commit()
        raise HTTPException(status_code=409, detail={"message": "Agent is not execution-ready.", "blockers": blockers})
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.execute(text("""
        UPDATE dbo.Agent SET Status='Active',LastEvaluationDate=:now,ModifiedDate=:now,ModifiedBy=:actor
        WHERE AgentID=:agent_id AND Status='Provisioning'
    """), {"now": now, "actor": user["sub"], "agent_id": agent_id})
    _audit(db, user, "AgentActivated", "Agent", agent_id, body.reason)
    db.commit()
    return {"agent_id": str(agent_id), "status": "Active", "activated_at_utc": now.isoformat()}