"""Simulation-only agent lifecycle planning built from workforce blueprints."""

from __future__ import annotations

import hashlib
import re
from typing import Any


SUPPORTED_ROLE_CATALOG = (
    ("business_analyst", "AI Business Analyst", "Analyst"),
    ("solution_architect", "AI Solution Architect", "Architect"),
    ("data_analyst", "AI Data Analyst", "Analyst"),
    ("backend_developer", "AI Backend Developer", "Developer"),
    ("frontend_developer", "AI Frontend Developer", "Developer"),
    ("qa_engineer", "AI QA Engineer", "Quality"),
    ("security_engineer", "AI Security Engineer", "Security"),
    ("devops_engineer", "AI DevOps Engineer", "Operations"),
    ("project_manager", "AI Project Manager", "Delivery"),
    ("product_owner", "AI Product Owner", "Product"),
)

LIFECYCLE_PHASES = (
    {
        "phase": "Created",
        "entry_criteria": ["Approved role profile and need validated by accountable owner"],
        "exit_criteria": ["Non-active agent record created through an authorized provisioning workflow"],
        "governance_gates": ["Recruiting/provisioning authority", "Duplicate and role-profile check"],
        "required_evidence": ["Approved role profile version", "Authorized request and actor", "Idempotency/correlation reference"],
    },
    {
        "phase": "Provisioned",
        "entry_criteria": ["Authorized creation workflow has created a non-active record"],
        "exit_criteria": ["Approved provider/model, secret references, skills, and boundaries are configured"],
        "governance_gates": ["Provider/model approval", "Credential reference validation", "Least-privilege review"],
        "required_evidence": ["Approved model/provider association", "Configuration review", "Pending skill assignments"],
    },
    {
        "phase": "Certified",
        "entry_criteria": ["Training completed and independent evaluation evidence submitted"],
        "exit_criteria": ["Authorized independent reviewer records current certification decision"],
        "governance_gates": ["Capability", "Safety", "Security", "Governance evaluations", "Separation of duties"],
        "required_evidence": ["Versioned evaluation results", "Reviewer identity", "Evidence references", "Expiry and renewal date"],
    },
    {
        "phase": "Active",
        "entry_criteria": ["Provisioned configuration and required current evaluations are verified"],
        "exit_criteria": ["Authorized activation decision after all blockers are resolved"],
        "governance_gates": ["Provider/model configured", "Current certifications", "Active skills", "No open blockers", "Authorized actor"],
        "required_evidence": ["Activation decision and reason", "Readiness evaluation", "Audit correlation"],
    },
    {
        "phase": "Assigned",
        "entry_criteria": ["Active role-qualified agent and approved work item are available"],
        "exit_criteria": ["Authorized assignment is recorded and capacity rechecked"],
        "governance_gates": ["Skill threshold", "Certification freshness", "Availability/capacity", "Project/task authorization"],
        "required_evidence": ["Assignment rationale", "Work-item scope", "Capacity snapshot", "Required approvals"],
    },
    {
        "phase": "Paused",
        "entry_criteria": ["Safety, capacity, security, certification, or operational concern is raised"],
        "exit_criteria": ["Concern independently reviewed and authorized resume decision recorded"],
        "governance_gates": ["Containment", "Work/credential impact assessment", "Owner or security review as required"],
        "required_evidence": ["Pause reason", "Affected work and credentials", "Remediation evidence", "Resume decision"],
    },
    {
        "phase": "Retired",
        "entry_criteria": ["Documented retirement rationale and impact assessment are reviewed"],
        "exit_criteria": ["Authorized retirement and revocation/retention actions are completed"],
        "governance_gates": ["No active assignments/executions", "Credential and permission revocation", "Data/audit retention review", "Owner approval"],
        "required_evidence": ["Retirement decision", "Credential revocation evidence", "Work reassignment plan", "Retention and audit closure"],
    },
)

CERTIFICATION_TIERS = {
    "Bronze": {"scope": "Supervised role fundamentals", "training_requirements": ["Role charter", "Safety and governance fundamentals"], "evaluation_requirements": ["Knowledge check", "Supervised sandbox task"], "expiry_months": 12, "renewal_rules": ["Repeat safety and governance training", "Renew before expiry"]},
    "Silver": {"scope": "Bounded independent task delivery", "training_requirements": ["Role-specific workflow", "Security and evidence handling"], "evaluation_requirements": ["Capability evaluation", "Safety evaluation", "Reviewed work sample"], "expiry_months": 12, "renewal_rules": ["Current task evidence", "Re-evaluate after material role change"]},
    "Gold": {"scope": "Complex work with peer review", "training_requirements": ["Advanced role practice", "Risk and escalation scenarios"], "evaluation_requirements": ["Capability, Safety, Security, and Governance evaluations", "Independent portfolio review"], "expiry_months": 12, "renewal_rules": ["Annual independent review", "Immediate review after serious incident"]},
    "Platinum": {"scope": "Lead and mentor within explicitly approved boundaries", "training_requirements": ["Leadership, auditability, and incident exercises"], "evaluation_requirements": ["All current evaluations", "Independent panel review"], "expiry_months": 6, "renewal_rules": ["Semiannual panel renewal", "Revalidate delegated scope at renewal"]},
}

TECHNOLOGY_SKILLS = {
    ".net": ("DotNetDevelopment", "Technical", "Complete approved .NET secure-service training and an independently reviewed sandbox exercise."),
    "angular": ("AngularDevelopment", "Technical", "Complete approved Angular architecture/accessibility training and a reviewed sandbox exercise."),
    "react": ("ReactDevelopment", "Technical", "Complete approved React component, accessibility, and client-security training with an assessed sandbox exercise."),
    "python": ("PythonDevelopment", "Technical", "Complete approved Python implementation, testing, dependency, and secure-coding training."),
    "azure ai": ("AzureAIIntegration", "AI", "Complete responsible AI, data handling, evaluation, and Azure AI integration training."),
    "copilot studio": ("CopilotStudioDesign", "AI", "Complete conversation design, connector security, evaluation, and governance training."),
    "openai": ("OpenAIIntegration", "AI", "Complete approved provider policy, privacy, evaluation, and integration training."),
    "anthropic": ("AnthropicIntegration", "AI", "Complete approved provider policy, privacy, evaluation, and integration training."),
}


def _simulated_agent_id(requirement_title: str, role_code: str) -> str:
    digest = hashlib.sha256(f"{requirement_title.strip().lower()}:{role_code}".encode("utf-8")).hexdigest()[:12].upper()
    return f"SIM-AGENT-{digest}"


def _skill_category(category: str) -> str:
    normalized = category.strip().lower()
    return {"technical": "Technical", "domain": "Domain", "security": "Security",
            "governance": "Governance", "ai": "AI"}.get(normalized, "Domain")


def build_agent_lifecycle_package(workforce_blueprint: dict[str, Any]) -> dict[str, Any]:
    """Return agent lifecycle plans only; do not create or alter any workforce state."""
    if not isinstance(workforce_blueprint, dict) or not isinstance(workforce_blueprint.get("requirement"), dict):
        raise ValueError("A workforce blueprint with requirement context is required")
    requirement = workforce_blueprint["requirement"]
    title = str(requirement.get("title", "Requirement"))
    roles = workforce_blueprint.get("roles", [])
    role_by_name = {str(role.get("role_name")): role for role in roles if isinstance(role, dict)}
    role_by_code = {str(role.get("role_code", "")).lower(): role for role in roles if isinstance(role, dict)}
    technologies = list(requirement.get("technology_changes", []))
    technology_keys = {technology.strip().lower() for technology in technologies if isinstance(technology, str)}

    agent_catalog = []
    profiles = []
    in_scope_roles = []
    for role_code, role_name, category in SUPPORTED_ROLE_CATALOG:
        role = role_by_name.get(role_name) or role_by_code.get(role_code)
        in_scope = role is not None
        agent_id = _simulated_agent_id(title, role_code)
        catalog_row = {"agent_id": agent_id, "role_code": role_code.upper(), "agent_name": role_name,
                       "agent_type": "Specialist", "agent_category": category,
                       "scope_status": "IN_SCOPE" if in_scope else "NOT_REQUIRED_BY_WORKFORCE_BLUEPRINT",
                       "creation_status": "SIMULATED_NOT_CREATED"}
        agent_catalog.append(catalog_row)
        if not in_scope:
            continue
        in_scope_roles.append(role_name)

        skills = []
        for skill in role.get("required_skills", []):
            level = int(skill.get("priority", 3))
            skills.append({
                "skill": skill.get("name"), "category": _skill_category(skill.get("category", "Domain")),
                "required_level": max(1, min(level, 5)),
                "criticality": "Critical" if level >= 5 else "High" if level >= 4 else "Medium",
                "training_path": f"Role training and evidence-backed evaluation for {skill.get('name')}.",
            })
        for baseline in (
            {"skill": "AIWorkforceSafety", "category": "AI", "required_level": 3,
             "criticality": "High", "training_path": "Responsible AI, human oversight, bounded authority, and escalation training."},
            {"skill": "GovernanceControls", "category": "Governance", "required_level": 4,
             "criticality": "Critical", "training_path": "Role-specific approval boundaries, evidence handling, audit, and separation-of-duties training."},
            {"skill": "SecureDataHandling", "category": "Security", "required_level": 3,
             "criticality": "High", "training_path": "Data minimization, access control, secret handling, and incident escalation training."},
        ):
            if baseline["skill"] not in {item["skill"] for item in skills}:
                skills.append(baseline)
        for technology in technologies:
            skill_info = TECHNOLOGY_SKILLS.get(technology.strip().lower())
            if skill_info:
                skill_name, skill_category, training = skill_info
                if skill_name not in {item["skill"] for item in skills}:
                    skills.append({"skill": skill_name, "category": skill_category,
                                   "required_level": 4, "criticality": "High",
                                   "training_path": training})

        job = role.get("job_description", {})
        profile = {
            "agent_id": agent_id, "agent_name": role_name,
            "role_name": role_name,
            "agent_type": role.get("agent_type", "Specialist"),
            "agent_category": category,
            "role_code": role.get("role_code", role_code.upper()),
            "scope_status": "IN_SCOPE",
            "purpose": job.get("purpose", f"Support the {title} requirement within the approved role scope."),
            "objectives": list(job.get("success_metrics", ["Meet reviewed acceptance criteria", "Maintain traceable evidence", "Escalate risks and blockers"])),
            "job_description": {
                "role_summary": job.get("purpose", f"Support {title} within approved role boundaries."),
                "responsibilities": list(job.get("responsibilities", [])),
                "deliverables": list(role.get("required_tools", [])) + ["Reviewed work-item evidence", "Role-specific documentation"],
                "success_metrics": list(job.get("success_metrics", [])),
                "kpis": list(job.get("kpis", [])),
                "reporting_structure": job.get("reporting_structure", "Reports through an authorized project lead; escalates governance decisions to accountable human owners."),
                "tools": list(role.get("required_tools", [])),
                "governance_responsibilities": ["Respect least privilege and role boundaries", "Preserve evidence and auditability", "Escalate safety, security, privacy, and approval blockers"],
            },
            "skill_matrix": skills,
            "certification_path": {
                "tiers": {name: {**requirements, "issued": False, "status": "PROPOSED_PATH_ONLY"}
                           for name, requirements in CERTIFICATION_TIERS.items()},
                "required_evaluations": list(role.get("required_certifications", [])),
                "certification_status": "NOT_ISSUED",
            },
            "certification_status": "NOT_ISSUED",
            "creation_status": "SIMULATED_NOT_CREATED",
            "activation_status": "NOT_ACTIVE",
            "assignment_status": "NOT_ASSIGNED",
            "agent_id_is_persisted": False,
        }
        profiles.append(profile)

    technology_updates = []
    for technology in technologies:
        if not isinstance(technology, str):
            continue
        skill_info = TECHNOLOGY_SKILLS.get(technology.strip().lower())
        if not skill_info:
            technology_updates.append({"technology": technology, "status": "REVIEW_REQUIRED",
                                      "skill_gap": "No approved mapping in the bounded technology catalog",
                                      "training_plan": "Confirm skill owner and approved training/evaluation before updating profiles."})
            continue
        skill_name, category, training = skill_info
        affected = [profile["agent_name"] for profile in profiles
                    if any(skill["skill"] == skill_name for skill in profile["skill_matrix"])]
        technology_updates.append({
            "technology": technology, "status": "PROPOSED_UPDATE",
            "skill_gap_analysis": {"skill": skill_name, "category": category,
                                   "affected_roles": affected, "current_proficiency": "UNVERIFIED",
                                   "required_level": 4},
            "training_plan": training,
            "certification_updates": [f"Add an independently reviewed {technology} evaluation to the relevant certification path."],
            "jd_updates": [f"Add reviewed {technology} responsibilities/tools to the relevant role description."],
            "profile_mutated": False,
        })

    assignment_recommendations = []
    task_items = workforce_blueprint.get("delivery_execution_package", {}).get("source_project", {})
    delivery = workforce_blueprint.get("delivery_execution_package", {})
    project_task_catalog = workforce_blueprint.get("project_delivery_package", {}).get("task_catalog", [])
    discipline_aliases = {"Developers": "Developer", "QA": "QA", "Security": "Security",
                          "DevOps": "DevOps", "Architect": "Architect", "Business Analyst": "Business Analyst"}
    for mapping in workforce_blueprint.get("project_delivery_package", {}).get("workforce_mapping", []):
        discipline = discipline_aliases.get(mapping.get("discipline"), mapping.get("discipline"))
        matching_tasks = [task["task_id"] for task in project_task_catalog
                          if task.get("role_discipline") == mapping.get("discipline")
                          or task.get("role_discipline") == discipline]
        assignment_recommendations.append({
            "role": mapping.get("discipline"), "proposed_agent_role": mapping.get("proposed_role"),
            "work_item_ids": matching_tasks or list(mapping.get("work_item_ids", [])),
            "readiness_score_percent": None, "readiness_status": "UNVERIFIED_NO_CANDIDATE_ROSTER",
            "evaluation_dimensions": ["Skills", "Current certification", "Availability", "Capacity", "Project fit"],
            "recommendation": "Review candidates with live evidence before a separate authorized assignment decision.",
            "assignment_status": "NOT_ASSIGNED",
        })
    assignment_readiness = {
        "readiness_score_percent": None,
        "status": "UNVERIFIED_NO_CANDIDATE_ROSTER",
        "dimensions": ["Skills", "Certification", "Availability", "Capacity", "Project fit"],
        "recommendations": assignment_recommendations,
        "assignment_performed": False,
        "basis": "No live candidate roster, certification freshness, availability, or capacity input was supplied.",
    }

    replacement_plans = [{
        "role": profile["agent_name"],
        "trigger": "Current agent unavailable or fails an authorized readiness check",
        "evaluation_dimensions": ["Skills match", "Current certification match", "Capacity", "Relevant project experience"],
        "candidate_status": "UNAVAILABLE_NO_LIVE_ROSTER",
        "candidate_recommendations": [],
        "replacement_performed": False,
        "approval_required": True,
    } for profile in profiles]

    governance_profiles = [{
        "agent_id": profile["agent_id"], "role": profile["agent_name"],
        "risk_profile": "HIGH_IMPACT_GOVERNED_ROLE",
        "responsibilities": profile["job_description"]["governance_responsibilities"],
        "approval_requirements": ["Independent role-profile approval", "Role-appropriate certifications", "Separate authorized activation/assignment decisions"],
        "security_classification": "Internal workforce configuration; handle requirement context according to approved data classification.",
        "ownership_model": "Accountable human owner retains lifecycle decision authority; agent has no approval authority.",
        "audit_requirements": ["Actor, action, resource, outcome, timestamp, and correlation ID", "Never log credentials or unnecessary sensitive payloads"],
    } for profile in profiles]

    skill_categories = {category: sorted({skill["skill"] for profile in profiles for skill in profile["skill_matrix"]
                                          if skill["category"] == category})
                        for category in ("Technical", "Domain", "Security", "Governance", "AI")}
    workforce_director = {
        "role": "Autonomous Workforce Director (Simulation Only)",
        "authority": "NONE", "action_allowed": False,
        "agent_creation_plan": {"scoped_roles": len(profiles), "catalog_roles": len(agent_catalog), "records_created": 0},
        "skill_coverage_plan": {"categories": skill_categories, "coverage_status": "PROPOSED_NOT_VERIFIED"},
        "certification_coverage_plan": {"tiers": list(CERTIFICATION_TIERS), "issued_count": 0,
                                       "coverage_status": "PROPOSED_PATHS_ONLY"},
        "capacity_forecast": workforce_blueprint.get("delivery_execution_package", {}).get("capacity_forecast", "UNAVAILABLE"),
        "assignment_readiness": assignment_readiness["status"],
        "replacement_readiness": "UNAVAILABLE_NO_LIVE_ROSTER",
        "retirement_readiness": {"status": "REVIEW_REQUIRED", "candidates": [],
                                 "note": "No lifecycle history or usage evidence was supplied; retirement is never automatic."},
    }

    return {
        "package": "Autonomous Agent Creation and Lifecycle Blueprint",
        "status": "SIMULATION_ONLY",
        "analysis_mode": "DETERMINISTIC_BLUEPRINT_TRANSFORMATION",
        "authority": "NONE", "action_allowed": False, "persistence": False,
        "agent_catalog": agent_catalog,
        "agent_profiles": profiles,
        "job_descriptions": [profile["job_description"] | {"agent_id": profile["agent_id"], "role_name": profile["agent_name"]} for profile in profiles],
        "skill_matrices": [{"agent_id": profile["agent_id"], "role_name": profile["agent_name"],
                            "skills": profile["skill_matrix"]} for profile in profiles],
        "certification_paths": [{"agent_id": profile["agent_id"], "role_name": profile["agent_name"],
                                 **profile["certification_path"]} for profile in profiles],
        "lifecycle_blueprints": [dict(item, state_change_performed=False) for item in LIFECYCLE_PHASES],
        "upskilling_factory": {"technology_updates": technology_updates, "profile_mutations": False},
        "assignment_readiness": assignment_readiness,
        "replacement_plans": replacement_plans,
        "governance_package": governance_profiles,
        "workforce_director_report": workforce_director,
        "controls": {"agent_records_created": False, "agents_provisioned": False,
                     "agents_activated": False, "certifications_issued": False,
                     "agents_assigned": False, "workforce_tables_modified": False,
                     "projects_modified": False, "tasks_modified": False,
                     "runtime_executed": False, "persistence": False},
        "future_phase": {"target": "Level 3 Supervised Agent Provisioning Sandbox",
                         "enabled": False,
                         "prerequisites": ["Separate authorization policy", "Reviewable proposals and approvals",
                                           "Idempotent audited provisioning", "Negative authorization tests",
                                           "No activation until independently approved"]},
    }