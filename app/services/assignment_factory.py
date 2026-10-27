"""Evidence-scored agent allocation recommendations; never assigns or persists."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


WEIGHTS = {
    "skills": 30,
    "certifications": 20,
    "availability": 15,
    "capacity": 15,
    "project_fit": 10,
    "technology_fit": 5,
    "performance": 5,
}
TASK_HOURS = {"DEVELOPMENT": 6, "TESTING": 4, "SECURITY": 3, "DEPLOYMENT": 2, "DOCUMENTATION": 2}
DISCIPLINE_ALIASES = {"Developers": "Developer", "QA": "QA", "Security": "Security",
                      "DevOps": "DevOps", "Architect": "Architect", "Business Analyst": "Business Analyst"}
ROLE_NAME_ALIASES = {
    "Architect": "AI Solution Architect", "Developer": "AI Backend Developer",
    "QA": "AI QA Engineer", "Security": "AI Security Engineer",
    "DevOps": "AI DevOps Engineer", "Business Analyst": "AI Business Analyst",
    "Product Owner": "AI Product Owner",
}


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2}


def _profile_skills(profile: dict[str, Any]) -> dict[str, int]:
    return {str(skill.get("skill")): int(skill.get("required_level", 1))
            for skill in profile.get("skill_matrix", []) if skill.get("skill")}


def _required_certifications(profile: dict[str, Any]) -> set[str]:
    return set(profile.get("certification_path", {}).get("required_evaluations", []))


def _candidate_score(candidate: dict[str, Any], profile: dict[str, Any], project_name: str,
                     technologies: set[str]) -> dict[str, Any]:
    required_skills = _profile_skills(profile)
    provided_skills = candidate.get("skills", {})
    if not isinstance(provided_skills, dict):
        provided_skills = {}
    present_skill_values = [
        min(max(float(provided_skills[name]), 0), level) / level * 100
        for name, level in required_skills.items()
        if isinstance(provided_skills.get(name), (int, float))
    ]
    skill_score = round(sum(present_skill_values) / len(required_skills), 1) if required_skills else 100.0
    missing_skills = [name for name, level in required_skills.items()
                      if not isinstance(provided_skills.get(name), (int, float))
                      or float(provided_skills[name]) < level]
    required_certs = _required_certifications(profile)
    candidate_certs = set(candidate.get("certifications_current", []))
    cert_score = round(100 * len(required_certs & candidate_certs) / len(required_certs), 1) if required_certs else 100.0
    missing_certifications = sorted(required_certs - candidate_certs)

    available_value = candidate.get("available")
    available_score = 100.0 if available_value is True else 0.0 if available_value is False else None
    available_hours = candidate.get("available_capacity_hours")
    reserved_hours = candidate.get("reserved_capacity_hours")
    capacity_score = None
    remaining_hours = None
    if isinstance(available_hours, (int, float)) and isinstance(reserved_hours, (int, float)):
        remaining_hours = max(float(available_hours) - max(float(reserved_hours), 0), 0)
        capacity_score = round(min(remaining_hours / 40, 1) * 100, 1)

    project_tags = {str(item).lower() for item in candidate.get("project_fit_tags", [])}
    project_tokens = _tokens(project_name)
    overlap = len(project_tags & project_tokens)
    project_fit = round(100 * overlap / max(len(project_tokens), 1), 1) if project_tags else None
    technologies_list = [str(item).lower() for item in candidate.get("technology_experience", [])]
    technology_fit = (round(100 * len(technologies & set(technologies_list)) / len(technologies), 1)
                      if technologies else 100.0 if technologies_list else None)
    raw_performance = candidate.get("performance_score")
    performance_evidence_reference = candidate.get("performance_evidence_reference")
    performance = (round(max(0.0, min(float(raw_performance), 100.0)), 1)
                   if performance_evidence_reference and isinstance(raw_performance, (int, float)) else None)

    components = {"skills": skill_score, "certifications": cert_score,
                  "availability": available_score, "capacity": capacity_score,
                  "project_fit": project_fit, "technology_fit": technology_fit,
                  "performance": performance,
                  "performance_evidence_verified": False}
    known_dimensions = {key: value for key, value in components.items()
                        if key in WEIGHTS and value is not None}
    used_weight = sum(WEIGHTS[key] for key in known_dimensions)
    score = round(sum(value * WEIGHTS[key] for key, value in known_dimensions.items()) / used_weight, 1) if used_weight else None
    unverified_dimensions = [key for key, weight in WEIGHTS.items() if weight and components.get(key) is None]
    substantive_blockers = []
    if missing_skills:
        substantive_blockers.append("Missing required skills/proficiency: " + ", ".join(missing_skills))
    if missing_certifications:
        substantive_blockers.append("Missing current certifications: " + ", ".join(missing_certifications))
    if available_value is not True:
        substantive_blockers.append("Availability is unavailable" if available_value is None else "Candidate is unavailable")
    if remaining_hours is None:
        substantive_blockers.append("Capacity evidence is unavailable")
    elif remaining_hours <= 0:
        substantive_blockers.append("No available capacity remains")

    blockers = substantive_blockers + ["Candidate attributes are caller-supplied and not independently verified"]
    readiness = "PARTIALLY_READY" if not substantive_blockers and score is not None else "NOT_READY"
    return {
        "candidate_id": str(candidate.get("candidate_id")),
        "match_score": score,
        "score_status": "PROVISIONAL_CALLER_SUPPLIED_EVIDENCE" if score is not None else "UNAVAILABLE",
        "score_components": components,
        "unverified_dimensions": unverified_dimensions,
        "missing_skills": missing_skills,
        "missing_certifications": missing_certifications,
        "remaining_capacity_hours_claimed": remaining_hours,
        "capacity_claim_status": "UNVERIFIED_CALLER_SUPPLIED",
        "performance_evidence_reference_supplied": bool(performance_evidence_reference),
        "readiness": readiness,
        "substantive_blockers": substantive_blockers,
        "blockers": blockers,
        "assignment_status": "NOT_ASSIGNED",
        "assignment_performed": False,
    }


def build_assignment_package(workforce_blueprint: dict[str, Any],
                             candidate_evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Score explicit candidate evidence against proposed work and return recommendations only."""
    if not isinstance(workforce_blueprint, dict) or not isinstance(workforce_blueprint.get("requirement"), dict):
        raise ValueError("A workforce blueprint with requirement context is required")
    candidates = candidate_evidence or []
    candidate_ids = [str(candidate.get("candidate_id", "")).strip() for candidate in candidates]
    if any(not identifier for identifier in candidate_ids) or len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("Candidate evidence must include unique non-empty candidate_id values")
    requirement = workforce_blueprint["requirement"]
    title = str(requirement.get("title", "Project"))
    technologies = {str(item).lower() for item in requirement.get("technology_changes", [])}
    lifecycle = workforce_blueprint.get("agent_lifecycle_package", {})
    profiles = lifecycle.get("agent_profiles", [])
    profiles_by_role = {profile["agent_name"]: profile for profile in profiles}
    project_package = workforce_blueprint.get("project_delivery_package", {})
    delivery = workforce_blueprint.get("delivery_execution_package", {})
    task_catalog = project_package.get("task_catalog", [])
    workforces = project_package.get("workforce_mapping", [])
    mapping_by_discipline = {item.get("discipline"): item for item in workforces}

    demand_hours: dict[str, int] = defaultdict(int)
    work_items: list[dict[str, Any]] = []
    for task in task_catalog:
        discipline = DISCIPLINE_ALIASES.get(task.get("role_discipline", ""), task.get("role_discipline", ""))
        task_type = str(task.get("task_type", "DEVELOPMENT"))
        hours = TASK_HOURS.get(task_type, 3)
        if discipline:
            demand_hours[discipline] += hours
            work_items.append({"work_item_id": task.get("task_id"), "title": task.get("title"),
                               "task_type": task_type, "role_discipline": discipline,
                               "estimated_effort_hours": hours,
                               "dependencies": task.get("dependencies", [])})

    by_discipline_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    scored_by_discipline: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        role_name = str(candidate.get("agent_role", ""))
        for discipline, canonical_role in ROLE_NAME_ALIASES.items():
            if role_name == canonical_role or role_name == discipline:
                by_discipline_candidates[discipline].append(candidate)
                profile = profiles_by_role.get(canonical_role)
                if profile:
                    scored_by_discipline[discipline].append(
                        _candidate_score(candidate, profile, title, technologies))
                break

    disciplines = ["Architect", "Business Analyst", "Developer", "QA", "Security", "DevOps", "Product Owner"]
    recommendations_by_discipline: dict[str, list[dict[str, Any]]] = {}
    team_composition = []
    capacity_roles = []
    skill_gaps: list[dict[str, Any]] = []
    readiness_states = []
    for discipline in disciplines:
        role_name = ROLE_NAME_ALIASES[discipline]
        profile = profiles_by_role.get(role_name)
        mapped = mapping_by_discipline.get(discipline, {})
        if discipline == "Developer":
            mapped = mapping_by_discipline.get("Developers", mapped)
        proposed_role = mapped.get("proposed_role", role_name)
        role_candidates = sorted(scored_by_discipline.get(discipline, []),
                                 key=lambda item: (item["match_score"] is None,
                                                   -(item["match_score"] or 0),
                                                   item["candidate_id"]))
        recommendations_by_discipline[discipline] = role_candidates
        qualified = []
        provisional = [item for item in role_candidates if item["readiness"] == "PARTIALLY_READY"]
        capacity_values = [item["remaining_capacity_hours_claimed"] for item in role_candidates
                   if item["remaining_capacity_hours_claimed"] is not None]
        claimed_capacity = sum(capacity_values) if capacity_values else None
        required_capacity = demand_hours.get(discipline, 0)
        capacity_status = ("UNVERIFIED" if claimed_capacity is None else
                   "CLAIMED_SUFFICIENT_UNVERIFIED" if claimed_capacity >= required_capacity
                   else "CLAIMED_GAP_UNVERIFIED")
        missing_skill_names = sorted({name for item in role_candidates for name in item["missing_skills"]})
        missing_certs = sorted({name for item in role_candidates for name in item["missing_certifications"]})
        if profile and not role_candidates:
            missing_skill_names.extend(skill["skill"] for skill in profile["skill_matrix"])
            missing_certs.extend(profile["certification_path"]["required_evaluations"])
        if missing_skill_names or missing_certs or capacity_status == "CLAIMED_GAP_UNVERIFIED":
            skill_gaps.append({"discipline": discipline, "missing_skills": sorted(set(missing_skill_names)),
                               "missing_certifications": sorted(set(missing_certs)),
                               "capacity_gap_hours": max(required_capacity - (claimed_capacity or 0), 0)
                                   if claimed_capacity is not None else None,
                               "upskilling_plan": "Review evidence gaps, assign approved training, and obtain independent evaluation; no profile is modified."})
        state = ("PARTIALLY_READY" if provisional and capacity_status == "CLAIMED_SUFFICIENT_UNVERIFIED"
             else "NOT_READY")
        readiness_states.append(state)
        team_composition.append({"discipline": discipline, "proposed_role": proposed_role,
                                 "required_work_items": sum(item["role_discipline"] == discipline for item in work_items),
                                 "candidate_count": len(role_candidates),
                                                                 "qualified_candidate_count": 0,
                                                                 "provisional_candidate_count": len(provisional),
                                                                 "composition_status": "PROVISIONAL_RECOMMENDATION_NOT_VERIFIED" if provisional else "ROLE_GAP_OR_UNVERIFIED",
                                 "assignment_status": "NOT_ASSIGNED"})
        capacity_roles.append({"discipline": discipline, "proposed_role": proposed_role,
                               "required_capacity_hours": required_capacity,
                                                             "available_capacity_hours": None,
                                                             "claimed_available_capacity_hours": claimed_capacity,
                               "reserved_capacity_hours": (sum(float(item.get("reserved_capacity_hours") or 0)
                                                               for item in by_discipline_candidates.get(discipline, []))
                                                           if role_candidates else None),
                               "reserved_capacity_status": "CALLER_SUPPLIED_UNVERIFIED" if role_candidates else "UNAVAILABLE",
                               "capacity_status": capacity_status,
                                                             "skill_coverage_status": "CLAIMED_COVERAGE_UNVERIFIED" if provisional else "GAP_OR_UNVERIFIED",
                                                             "capacity_source": "CALLER_SUPPLIED_UNVERIFIED" if role_candidates else "UNAVAILABLE"})

    work_recommendations = []
    for work_item in work_items:
        discipline = work_item["role_discipline"]
        candidates_for_role = recommendations_by_discipline.get(discipline, [])
        work_recommendations.append({
            **work_item,
            "readiness": "PROVISIONAL_NOT_VERIFIED" if candidates_for_role else "NOT_READY",
            "recommendations": candidates_for_role[:3],
            "dependencies": work_item["dependencies"],
            "assignment_status": "NOT_ASSIGNED",
        })

    has_provisional = any(state == "PARTIALLY_READY" for state in readiness_states)
    overall_status = "PARTIALLY_READY" if candidates and has_provisional else "NOT_READY"
    readiness_score = None
    provisional_coverage = (round(100 * sum(state == "PARTIALLY_READY" for state in readiness_states)
                                  / len(readiness_states), 1)
                            if candidates and readiness_states else None)
    assignment_readiness = {
        "status": overall_status,
        "readiness_score_percent": readiness_score,
        "verified_readiness_status": "UNVERIFIED",
        "verified_readiness_score_percent": None,
        "provisional_claim_coverage_percent": provisional_coverage,
        "dimensions": {"skills": "EVIDENCE_SCANNED" if candidates else "UNVERIFIED",
                       "certification": "EVIDENCE_SCANNED" if candidates else "UNVERIFIED",
                       "capacity": "EVIDENCE_SCANNED" if candidates else "UNVERIFIED",
                       "dependencies": "PROPOSED_NOT_EXECUTED",
                       "project_fit": "EVIDENCE_SCANNED" if candidates else "UNVERIFIED"},
        "explanation": "Caller-supplied candidate claims can support provisional matching only. Verified readiness is unavailable because the preview does not independently validate workforce evidence.",
    }

    replacement_plans = []
    for discipline in disciplines:
        role_candidates = recommendations_by_discipline.get(discipline, [])
        replacement_plans.append({
            "discipline": discipline,
            "primary_candidate": role_candidates[0] if role_candidates else None,
            "secondary_candidate": role_candidates[1] if len(role_candidates) > 1 else None,
            "fallback_candidate": role_candidates[2] if len(role_candidates) > 2 else None,
            "candidate_status": "PROVISIONAL_RANKING_UNVERIFIED" if role_candidates else "UNAVAILABLE_NO_CANDIDATE_EVIDENCE",
            "reassignment_performed": False,
        })

    total_demand = sum(item["required_capacity_hours"] for item in capacity_roles)
    known_capacity_claims = [item["claimed_available_capacity_hours"] for item in capacity_roles
                             if item["claimed_available_capacity_hours"] is not None]
    total_claimed_capacity = sum(known_capacity_claims) if known_capacity_claims else None
    capacity_plan = {
        "roles": capacity_roles,
        "required_capacity_hours": total_demand,
        "available_capacity_hours": None,
        "claimed_available_capacity_hours": total_claimed_capacity,
        "reserved_capacity_hours": sum(item["reserved_capacity_hours"] or 0 for item in capacity_roles)
            if any(item["reserved_capacity_hours"] is not None for item in capacity_roles) else None,
        "capacity_status": "UNVERIFIED" if total_claimed_capacity is None else "CLAIMED_ONLY_REQUIRES_VERIFICATION",
        "skill_gaps": skill_gaps,
        "source": "Caller-supplied candidate claims only; no workforce database query or independent verification was performed.",
    }

    director_dashboard = {
        "assignment_readiness": assignment_readiness,
        "coverage": {"roles_required": len(disciplines), "roles_with_qualified_candidates": 0,
                 "roles_with_provisional_candidates": sum(item["provisional_candidate_count"] > 0 for item in team_composition),
                     "status": "UNVERIFIED" if not candidates else overall_status},
        "utilization": "UNAVAILABLE_UNVERIFIED_CLAIMS" if candidates else "UNAVAILABLE",
        "capacity": {"available_hours": None, "claimed_available_hours": total_claimed_capacity,
                 "required_hours": total_demand,
                     "status": capacity_plan["capacity_status"]},
        "skill_gaps": skill_gaps,
        "replacement_readiness": "UNAVAILABLE_NO_CANDIDATE_EVIDENCE" if not candidates else "CANDIDATES_RANKED_NOT_REASSIGNED",
    }
    execution_readiness = {
        "can_project_be_staffed": False,
        "status": overall_status if candidates else "NOT_READY",
        "reason": "No candidate evidence is independently verified; provisional recommendations cannot establish staffing readiness.",
        "assignment_authority": "NONE",
        "execution_authorized": False,
    }
    assignment_blueprint = {
        "project_name": title,
        "work_items": work_recommendations,
        "team_composition": team_composition,
        "recommendation_weights_percent": dict(WEIGHTS),
        "scoring_note": "Unknown evidence is excluded and reported, never treated as a zero-performance score.",
    }
    assignment_plan = {
        "assignment_blueprint": assignment_blueprint,
        "resource_plan": team_composition,
        "capacity_plan": capacity_plan,
        "skill_gap_report": skill_gaps,
        "replacement_plan": replacement_plans,
        "readiness_report": execution_readiness,
    }
    return {
        "package": "Autonomous Agent Assignment Recommendation Package",
        "status": "PLANNING_ONLY",
        "authority": "NONE", "action_allowed": False, "persistence": False,
        "candidate_evidence_supplied": bool(candidates),
        "assignment_blueprint": assignment_blueprint,
        "match_results": [result for values in recommendations_by_discipline.values() for result in values],
        "capacity_plan": capacity_plan,
        "assignment_readiness": assignment_readiness,
        "replacement_plan": replacement_plans,
        "team_composition": team_composition,
        "skill_gap_report": skill_gaps,
        "workforce_director_dashboard": director_dashboard,
        "execution_readiness_report": execution_readiness,
        "assignment_package": assignment_plan,
        "controls": {"assignments_created": False, "agents_activated": False,
                     "agents_provisioned": False, "runtime_executed": False,
                     "workforce_tables_modified": False, "projects_modified": False,
                     "tasks_modified": False, "persistence": False},
    }