"""Deterministic project delivery planning artifacts; no persistence or assignments."""

from __future__ import annotations

import math
import re
from typing import Any


EPIC_TEMPLATES = (
    {
        "key": "discovery",
        "name": "Discovery and delivery foundations",
        "description": "Confirm stakeholders, scope, success measures, dependencies, and delivery controls.",
        "priority": "High",
        "feature": "Approved scope and delivery baseline",
        "story": "As a business stakeholder, I want an agreed scope and measurable outcomes so that delivery can be evaluated against the intended value.",
        "points": 5,
        "role": "Business Analyst",
    },
    {
        "key": "architecture",
        "name": "Architecture and data foundations",
        "description": "Define reviewed service boundaries, data structures, integration contracts, and operational constraints.",
        "priority": "High",
        "feature": "Reviewed solution and data design",
        "story": "As a delivery team, we want reviewed architecture and data contracts so that implementation has explicit boundaries and dependencies.",
        "points": 8,
        "role": "Architect",
    },
    {
        "key": "core",
        "name": "Core user capabilities",
        "description": "Deliver the primary user-facing capability and supporting API/data behavior described by the requirement.",
        "priority": "High",
        "feature": "Primary user workflow",
        "story": "As an authorized user, I want to complete the primary workflow so that I can achieve the stated business outcome.",
        "points": 8,
        "role": "Developers",
    },
    {
        "key": "assurance",
        "name": "Quality, security, and audit assurance",
        "description": "Verify acceptance, authorization, privacy, auditability, resilience, and quality requirements.",
        "priority": "High",
        "feature": "Verified quality and security controls",
        "story": "As an accountable owner, I want evidence that quality and security controls pass so that risks are visible before release review.",
        "points": 8,
        "role": "QA",
    },
    {
        "key": "release",
        "name": "Release readiness and handover",
        "description": "Prepare operational documentation, support readiness, rollback evidence, and release review materials.",
        "priority": "Medium",
        "feature": "Reviewed release and support package",
        "story": "As an operations owner, I want a reviewed release and support package so that a separately authorized release can be assessed.",
        "points": 5,
        "role": "DevOps",
    },
)

TASK_TYPES = (
    ("DEVELOPMENT", "Implement the approved feature contract and record review evidence."),
    ("TESTING", "Add and review unit, integration, and acceptance coverage for the story."),
    ("SECURITY", "Review authorization, data handling, threat controls, and audit evidence."),
    ("DEPLOYMENT", "Prepare a deployment-readiness checklist; do not deploy from this plan."),
    ("DOCUMENTATION", "Update design, user, operational, and traceability documentation."),
)

ROLE_DISCIPLINES = (
    ("Architect", "AI Solution Architect", "Architecture, interfaces, and data design"),
    ("Developer", "AI Backend Developer", "Backend and integration implementation planning"),
    ("QA", "AI QA Engineer", "Verification, acceptance, and defect evidence"),
    ("Security", "AI Security Engineer", "Threat, authorization, privacy, and audit review"),
    ("DevOps", "AI DevOps Engineer", "Release, monitoring, recovery, and support readiness"),
    ("Business Analyst", "AI Business Analyst", "Scope, acceptance criteria, traceability, and stakeholder validation"),
)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def build_project_delivery_package(
    *, title: str, description: str, priority: str | None = None,
    technical_delivery_package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build stable project planning artifacts with no DB, filesystem, or runtime calls."""
    clean_title = title.strip()
    clean_description = description.strip()
    context = _slug(f"{clean_title} {clean_description}")
    tech_artifacts = (technical_delivery_package or {}).get("artifacts", {})
    executive = tech_artifacts.get("executive_assessment", {}) if isinstance(tech_artifacts, dict) else {}
    business_domain = executive.get("business_domain", "Unconfirmed business domain")
    complexity = executive.get("complexity", "Unassessed")
    chosen_priority = priority or executive.get("priority", "Unconfirmed")
    sensitive = any(term in context.split() for term in ("customer", "employee", "patient", "financial", "health", "personal", "sensitive"))
    integration = any(term in context.split() for term in ("integration", "integrate", "external", "api", "connector", "payment"))

    charter = {
        "project_name": clean_title[:250],
        "vision": f"Enable the intended {business_domain} outcome described by the requirement while preserving explicit security, quality, and governance controls.",
        "business_domain": business_domain,
        "solution_type": executive.get("solution_type", "Unassessed solution type"),
        "complexity": complexity,
        "priority": chosen_priority,
        "priority_basis": "Requester-selected" if priority else "Inherited planning assessment; validate",
        "problem_statement": clean_description,
        "goals": [
            "Deliver the validated primary user/business outcome.",
            "Provide traceable acceptance, quality, security, and audit evidence.",
            "Prepare operational handover and release materials for separate review.",
        ],
        "objectives": [
            {"objective": "Approve scope and acceptance criteria", "measure": "All in-scope features have reviewed acceptance criteria"},
            {"objective": "Deliver the planned solution capabilities", "measure": "Each accepted feature maps to a completed, reviewed story"},
            {"objective": "Verify governance controls", "measure": "No unresolved critical security or approval blockers at release review"},
        ],
        "business_outcomes": [
            {"outcome": "Improved completion of the target business workflow", "measure": "Baseline and target to be supplied by business owner"},
            {"outcome": "Reduced operational uncertainty", "measure": "Operational owner accepts monitoring and support evidence"},
        ],
        "success_metrics": [
            {"metric": "Acceptance coverage", "target": "100% of approved acceptance criteria verified", "owner": "Product Owner"},
            {"metric": "Critical control findings", "target": "0 open critical findings at release review", "owner": "Security and Governance"},
            {"metric": "Delivery predictability", "target": "Baseline after at least two observed sprints", "owner": "Project Manager"},
        ],
        "assumptions": ["Business owner confirms measurable outcome and scope.", "Technology and data assumptions in the technical blueprint are reviewed before implementation."],
    }

    epics = []
    features = []
    stories = []
    tasks = []
    for epic_index, template in enumerate(EPIC_TEMPLATES, start=1):
        epic_id = f"EP-{epic_index:02d}"
        dependencies = [] if epic_index == 1 else [f"EP-{epic_index - 1:02d}"]
        if template["key"] == "core" and integration:
            dependencies = ["EP-02"]
        if template["key"] == "assurance":
            dependencies = ["EP-02", "EP-03"]
        if template["key"] == "release":
            dependencies = ["EP-04"]
        epics.append({
            "epic_id": epic_id, "name": template["name"],
            "description": template["description"], "priority": template["priority"],
            "dependencies": dependencies, "status": "PROPOSED_NOT_CREATED",
        })
        feature_id = f"FE-{epic_index:02d}-01"
        feature_name = template["feature"]
        features.append({
            "feature_id": feature_id, "epic_id": epic_id, "name": feature_name,
            "description": f"Provide {feature_name.lower()} for {clean_title} within approved scope.",
            "priority": template["priority"],
            "acceptance_criteria": [
                "Behavior is demonstrated against reviewed acceptance criteria.",
                "Authorization and error states are verified for the relevant user/resource context.",
                "Evidence and documentation are traceable to the requirement.",
            ],
            "status": "PROPOSED_NOT_CREATED",
        })
        story_id = f"US-{epic_index:02d}-01"
        stories.append({
            "story_id": story_id, "epic_id": epic_id, "feature_id": feature_id,
            "title": feature_name, "description": template["story"],
            "story_points": template["points"], "business_value": "High" if template["priority"] == "High" else "Medium",
            "acceptance_criteria": [
                "Given an authorized user, when the agreed workflow is completed, then the expected outcome is observable.",
                "Given invalid or unauthorized input, when the operation is attempted, then it is rejected without unauthorized state change.",
                "Given the acceptance evidence, when independently reviewed, then the result is traceable to this story.",
            ],
            "dependencies": dependencies, "status": "PROPOSED_NOT_CREATED",
        })
        for task_index, (task_type, task_description) in enumerate(TASK_TYPES, start=1):
            task_id = f"TK-{epic_index:02d}-{task_index:02d}"
            tasks.append({
                "task_id": task_id, "epic_id": epic_id, "feature_id": feature_id,
                "story_id": story_id, "task_type": task_type,
                "title": f"{task_type.title()} · {feature_name}",
                "description": task_description,
                "role_discipline": ("Security" if task_type == "SECURITY" else
                                    "QA" if task_type == "TESTING" else
                                    "DevOps" if task_type == "DEPLOYMENT" else
                                    "Business Analyst" if task_type == "DOCUMENTATION" else template["role"]),
                "dependencies": [f"TK-{epic_index:02d}-01"] if task_index > 1 else [],
                "status": "PROPOSED_NOT_CREATED",
            })

    total_points = sum(story["story_points"] for story in stories)
    assumed_velocity = 20
    sprint_count = max(1, math.ceil(total_points / assumed_velocity))
    sprint_plan = {
        "sprint_length_weeks": 2,
        "sprint_count_estimate": sprint_count,
        "total_story_points": total_points,
        "historical_velocity": None,
        "estimated_velocity_story_points": assumed_velocity,
        "capacity_basis": "Assumed 20 story points per sprint for a stable, cross-functional team; replace with observed team capacity and historical velocity.",
        "capacity_estimate": {"available_hours": None, "basis": "No approved roster, allocation, or calendar availability supplied."},
        "sprints": [
            {"sprint": index, "goal": epics[min(index - 1, len(epics) - 1)]["name"],
             "epic_ids": [epics[min(index - 1, len(epics) - 1)]["epic_id"]],
             "planned_story_points": min(assumed_velocity, max(total_points - (index - 1) * assumed_velocity, 0)),
             "status": "PROPOSED_NOT_SCHEDULED"}
            for index in range(1, sprint_count + 1)
        ],
        "release_plan": [{"milestone": "Release readiness review", "after_sprint": sprint_count,
                          "gate": "Separate authorized release decision; no release is performed by this plan."}],
    }

    wbs = {
        "hierarchy": [{"level": 1, "id": "PROJECT", "name": clean_title,
                       "children": [{"level": 2, "id": epic["epic_id"], "name": epic["name"],
                                     "children": [{"level": 3, "id": feature["feature_id"], "name": feature["name"],
                                                   "children": [{"level": 4, "id": story["story_id"], "name": story["title"],
                                                                 "children": [task["task_id"] for task in tasks if task["story_id"] == story["story_id"]]}
                                                                for story in stories if story["feature_id"] == feature["feature_id"]]}
                                                   for feature in features if feature["epic_id"] == epic["epic_id"]]}
                                    for epic in epics]}],
        "deliverables": ["Reviewed project charter", "Approved architecture and data contracts", "Accepted feature increments", "Verified security and test evidence", "Release and support review package"],
        "dependencies": [{"work_item_id": epic["epic_id"], "depends_on": epic["dependencies"]} for epic in epics],
        "milestones": [{"name": epic["name"], "target": "Unscheduled", "exit_evidence": f"Acceptance and governance evidence for {epic['epic_id']}"} for epic in epics],
    }

    technical_roles = {}
    supplied_workforce = tech_artifacts.get("workforce_plan", {}) if isinstance(tech_artifacts, dict) else {}
    for role in supplied_workforce.get("role_alignment", []):
        technical_roles[role.get("discipline")] = role.get("proposed_role")
    workforce_mapping = []
    for discipline, default_role, contribution in ROLE_DISCIPLINES:
        task_discipline = "Developers" if discipline == "Developer" else discipline
        role_lookup = "Developers" if discipline == "Developer" else discipline
        linked_tasks = [task["task_id"] for task in tasks if task["role_discipline"] == task_discipline]
        workforce_mapping.append({
            "discipline": discipline, "proposed_role": technical_roles.get(role_lookup, default_role),
            "work_item_ids": linked_tasks,
            "contribution": contribution,
            "assignment_status": "NOT_ASSIGNED",
        })

    governance = {
        "risks": [
            {"risk_id": "R-01", "description": "Scope or acceptance criteria remain unvalidated.", "severity": "High", "response": "Business owner review before baseline."},
            {"risk_id": "R-02", "description": "Data classification, tenancy, privacy, or retention needs may be incomplete.", "severity": "High" if sensitive else "Medium", "response": "Security/data owner review before design approval."},
            *([{"risk_id": "R-03", "description": "External integration contracts and availability are unconfirmed.", "severity": "Medium", "response": "Validate interface, authentication, rate limits, and failure handling."}] if integration else []),
        ],
        "assumptions": charter["assumptions"],
        "dependencies": ["Business owner and stakeholder availability", "Approved identity, data, and integration decisions", "Workforce capacity and skill evidence"],
        "constraints": ["No project or task records are created by this planner.", "No agent assignment, runtime action, code execution, or deployment is performed.", "Sprint velocity and capacity are assumed until measured."],
        "approval_requirements": ["Business owner validates charter, objectives, and acceptance criteria.", "Architecture/data/security owners review design and classification.", "Authorized governance approval remains required for high-risk, security, workforce, release, or production decisions."],
        "approval_authority_granted": False,
    }

    return {
        "package": "Autonomous Project Factory",
        "status": "PLANNING_ONLY",
        "analysis_mode": "DETERMINISTIC_TEMPLATE_DRAFT_REQUIRES_HUMAN_VALIDATION",
        "source_requirement": {"title": clean_title, "description": clean_description, "priority": chosen_priority},
        "project_charter": charter,
        "epic_catalog": epics,
        "feature_catalog": features,
        "user_story_catalog": stories,
        "task_catalog": tasks,
        "sprint_plan": sprint_plan,
        "work_breakdown_structure": wbs,
        "workforce_mapping": workforce_mapping,
        "governance_package": governance,
        "controls": {"project_created": False, "epics_created": False, "features_created": False,
                     "stories_created": False, "tasks_created": False, "sprint_created": False,
                     "assignments_created": False, "runtime_started": False,
                     "deployment_performed": False, "persistence": False},
    }