"""Deterministic delivery sequencing and simulation; never executes or assigns work."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


ROLE_PROFILES = {
    "Architect": {"role": "AI Solution Architect", "capacity_hours_per_sprint": 48},
    "Business Analyst": {"role": "AI Business Analyst", "capacity_hours_per_sprint": 48},
    "Developer": {"role": "AI Backend Developer", "capacity_hours_per_sprint": 60},
    "QA": {"role": "AI QA Engineer", "capacity_hours_per_sprint": 48},
    "Security": {"role": "AI Security Engineer", "capacity_hours_per_sprint": 32},
    "DevOps": {"role": "AI DevOps Engineer", "capacity_hours_per_sprint": 32},
}
TASK_HOURS = {"DEVELOPMENT": 6, "TESTING": 4, "SECURITY": 3, "DEPLOYMENT": 2, "DOCUMENTATION": 2}
DISCIPLINE_ALIASES = {"Developers": "Developer", "Security Engineer": "Security", "Architect": "Architect"}


def _topological_epics(epics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(item["epic_id"]): item for item in epics}
    if len(by_id) != len(epics):
        raise ValueError("Epic identifiers must be unique")
    for epic_id, item in by_id.items():
        unknown = set(item.get("dependencies", [])) - set(by_id)
        if unknown:
            raise ValueError(f"Epic {epic_id} has unknown dependencies: {', '.join(sorted(unknown))}")
    remaining = set(by_id)
    ordered: list[dict[str, Any]] = []
    while remaining:
        ready = sorted(epic_id for epic_id in remaining
                       if set(by_id[epic_id].get("dependencies", [])) <= {item["epic_id"] for item in ordered})
        if not ready:
            raise ValueError("Epic dependencies contain a cycle")
        for epic_id in ready:
            ordered.append(by_id[epic_id])
            remaining.remove(epic_id)
    return ordered


def _risk(risk_id: str, category: str, severity: str, description: str, mitigation: str,
          evidence: str = "ASSUMPTION_OR_PLANNING_INPUT") -> dict[str, str]:
    return {"risk_id": risk_id, "category": category, "severity": severity,
            "description": description, "mitigation": mitigation, "evidence": evidence,
            "status": "OPEN_PLANNING_RISK"}


def build_delivery_execution_package(project_package: dict[str, Any]) -> dict[str, Any]:
    """Produce execution planning and simulation outputs from a project blueprint only."""
    if not isinstance(project_package, dict) or project_package.get("status") != "PLANNING_ONLY":
        raise ValueError("A PLANNING_ONLY Project Factory package is required")
    epics = _topological_epics(project_package.get("epic_catalog", []))
    stories = project_package.get("user_story_catalog", [])
    tasks = project_package.get("task_catalog", [])
    charter = project_package.get("project_charter", {})
    total_points = sum(max(0, int(story.get("story_points", 0))) for story in stories)
    assumed_velocity = int(project_package.get("sprint_plan", {}).get("estimated_velocity_story_points") or 20)
    assumed_velocity = max(1, min(assumed_velocity, 100))
    hours_per_point = 6

    stories_by_epic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for story in stories:
        stories_by_epic[story["epic_id"]].append(story)
    points_by_epic = {epic["epic_id"]: sum(int(story.get("story_points", 0))
                                            for story in stories_by_epic[epic["epic_id"]])
                      for epic in epics}
    task_hours_by_role: dict[str, int] = defaultdict(int)
    for task in tasks:
        discipline = DISCIPLINE_ALIASES.get(task.get("role_discipline", ""), task.get("role_discipline", ""))
        task_type = task.get("task_type", "DEVELOPMENT")
        if discipline in ROLE_PROFILES:
            task_hours_by_role[discipline] += TASK_HOURS.get(task_type, 3)

    delivery_sequence = []
    epic_schedule: dict[str, dict[str, Any]] = {}
    for sequence, epic in enumerate(epics, start=1):
        dependency_finish = max((epic_schedule[item]["earliest_finish_sprint"]
                                 for item in epic.get("dependencies", [])), default=0)
        epic_points = points_by_epic.get(epic["epic_id"], 0)
        duration_sprints = max(1, math.ceil(epic_points / assumed_velocity))
        start_sprint = dependency_finish + 1
        finish_sprint = start_sprint + duration_sprints - 1
        epic_schedule[epic["epic_id"]] = {
            "earliest_start_sprint": start_sprint,
            "earliest_finish_sprint": finish_sprint,
            "duration_sprints": duration_sprints,
        }
        delivery_sequence.append({
            "sequence": sequence, "epic_id": epic["epic_id"], "epic": epic["name"],
            "dependencies": epic.get("dependencies", []), "story_points": epic_points,
            **epic_schedule[epic["epic_id"]], "status": "PROPOSED_NOT_STARTED",
        })

    total_sprints = max((item["earliest_finish_sprint"] for item in epic_schedule.values()), default=0)
    critical_epic_ids: list[str] = []
    current = max(epic_schedule, key=lambda epic_id: epic_schedule[epic_id]["earliest_finish_sprint"], default=None)
    parents = {item["epic_id"]: item for item in epics}
    while current:
        critical_epic_ids.append(current)
        dependencies = parents[current].get("dependencies", [])
        if not dependencies:
            break
        current = max(dependencies, key=lambda epic_id: epic_schedule[epic_id]["earliest_finish_sprint"])
    critical_epic_ids.reverse()
    critical_path = [{"epic_id": epic_id, "epic": next(item["name"] for item in epics if item["epic_id"] == epic_id),
                      **epic_schedule[epic_id]} for epic_id in critical_epic_ids]
    dependency_edges = [{"work_item_id": epic["epic_id"], "depends_on": epic.get("dependencies", [])}
                        for epic in epics]
    milestones = [{"milestone_id": f"MS-{index:02d}", "name": item["epic"],
                   "target_sprint": item["earliest_finish_sprint"],
                   "exit_criteria": "Epic acceptance and governance evidence reviewed",
                   "status": "PROPOSED_NOT_SCHEDULED"}
                  for index, item in enumerate(delivery_sequence, start=1)]

    total_hours = total_points * hours_per_point
    role_forecasts = []
    for discipline, profile in ROLE_PROFILES.items():
        demand = task_hours_by_role.get(discipline, 0)
        capacity = profile["capacity_hours_per_sprint"]
        role_forecasts.append({
            "discipline": discipline, "proposed_role": profile["role"],
            "estimated_demand_hours": demand,
            "assumed_capacity_hours_per_sprint": capacity,
            "required_role_sprints": round(demand / capacity, 2) if demand else 0,
            "capacity_gap_hours": max(demand - capacity * max(total_sprints, 1), 0),
            "skill_gaps": "Unavailable: no live agent skill evidence supplied",
            "capacity_source": "ASSUMED_NOT_LIVE",
        })
    capacity_forecast = {
        "roles": role_forecasts,
        "total_estimated_effort_hours": total_hours,
        "hours_per_story_point": hours_per_point,
        "assumption_based": True,
        "basis": "Planning conversion of 6 effort hours per story point and role capacities from generic team assumptions; no roster, leave calendar, availability, or contract hours were queried.",
        "workforce_risks": [item["discipline"] for item in role_forecasts if item["capacity_gap_hours"] > 0],
    }

    sprint_buckets: dict[int, list[str]] = defaultdict(list)
    sprint_points: dict[int, int] = defaultdict(int)
    for item in delivery_sequence:
        sprint = item["earliest_start_sprint"]
        sprint_buckets[sprint].append(item["epic_id"])
        sprint_points[sprint] += item["story_points"]
    simulated_sprints = []
    cumulative_points = 0
    for sprint_number in range(1, total_sprints + 1):
        planned = sprint_points.get(sprint_number, 0)
        cumulative_points += planned
        simulated_sprints.append({
            "sprint": sprint_number, "epic_ids": sprint_buckets.get(sprint_number, []),
            "planned_points": planned, "base_velocity": assumed_velocity,
            "capacity_load_percent": round(100 * planned / assumed_velocity, 1),
            "scope_completion_projection_percent": round(100 * cumulative_points / max(total_points, 1), 1),
            "simulated_sprint_completion": planned <= assumed_velocity,
            "forecast": "AT_CAPACITY" if planned > assumed_velocity else "WITHIN_ASSUMED_CAPACITY",
            "risk": "HIGH" if planned > assumed_velocity else "MEDIUM" if planned >= assumed_velocity * 0.8 else "LOW",
            "status": "SIMULATED_NOT_SCHEDULED",
        })
    constrained_velocity = max(1, round(assumed_velocity * 0.7))
    constrained_sprints = math.ceil(total_points / constrained_velocity) if total_points else 0
    sprint_simulation = {
        "assumption_based": True,
        "historical_velocity": None,
        "base_velocity_story_points": assumed_velocity,
        "constrained_velocity_story_points": constrained_velocity,
        "sprints": simulated_sprints,
        "velocity_forecast": {"base": assumed_velocity, "constrained": constrained_velocity,
                              "basis": "Base velocity inherits Project Factory assumption; constrained scenario is 70% of base, not observed performance."},
        "delivery_forecast": {"base_sprints": total_sprints, "constrained_sprints": constrained_sprints,
                               "calendar_duration_weeks": None,
                               "basis": "Sprint count is a sequence estimate; calendar dates and team availability are unknown."},
        "risk_forecast": [{"scenario": "Base", "risk": "MEDIUM" if total_sprints else "UNAVAILABLE"},
                          {"scenario": "Constrained capacity", "risk": "HIGH" if constrained_sprints > total_sprints else "MEDIUM"}],
    }

    recommendation_by_discipline = defaultdict(list)
    for task in tasks:
        raw_discipline = task.get("role_discipline", "Developer")
        discipline = DISCIPLINE_ALIASES.get(raw_discipline, raw_discipline)
        if discipline not in ROLE_PROFILES:
            discipline = "Developer"
        recommendation_by_discipline[discipline].append(task["task_id"])
    agent_execution_plan = [{
        "discipline": discipline, "proposed_role": profile["role"],
        "work_item_ids": recommendation_by_discipline.get(discipline, []),
        "recommendation": "Review role fit and capacity evidence before any authorized assignment.",
        "assignment_status": "NOT_ASSIGNED",
    } for discipline, profile in ROLE_PROFILES.items()]

    release_gates = [
        "Approved scope and acceptance evidence",
        "Security and privacy review passed with no open critical findings",
        "Operational monitoring, backup, restore, and rollback evidence reviewed",
        "Authorized release approval recorded through the separate governance workflow",
    ]
    release_plan = {
        "release_name": f"{charter.get('project_name', 'Project')} initial release",
        "deployment_waves": [
            {"wave": 0, "name": "Non-production verification", "gate": "UAT, security, and operational evidence reviewed", "status": "PROPOSED_NOT_SCHEDULED"},
            {"wave": 1, "name": "Controlled release candidate", "gate": "Explicit authorized release decision", "status": "PROPOSED_NOT_SCHEDULED"},
        ],
        "rollback_strategy": ["Define a tested rollback trigger and accountable decision owner.",
                              "Verify backup/restore and data compatibility before any future release.",
                              "This plan does not create or execute rollback steps."],
        "release_gates": release_gates,
        "deployment_performed": False,
    }

    risks = [
        _risk("DR-01", "Schedule Risk", "HIGH", "Sprint count depends on assumed velocity and unconfirmed calendar availability.", "Reforecast using measured team velocity and approved availability."),
        _risk("DR-02", "Workforce Risk", "HIGH", "Live role capacity and skill coverage were not queried.", "Validate named role capacity and evidence with Workforce Manager."),
        _risk("DR-03", "Dependency Risk", "MEDIUM", "A delay in a predecessor epic shifts all dependent work.", "Review dependency owners and unblock architecture/data decisions early."),
        _risk("DR-04", "Technology Risk", "MEDIUM", "Technology and integration assumptions may not match the approved target environment.", "Confirm stack, interface contracts, and non-functional requirements."),
        _risk("DR-05", "Governance Risk", "HIGH", "No authorization or release evidence is included in planning artifacts.", "Retain existing independent approval and release gates."),
    ]
    risk_register = {"risks": risks, "risk_count": len(risks), "highest_severity": "HIGH",
                     "overall_risk": "HIGH", "basis": "Conservative planning risks; not a measured live project risk assessment."}

    planning_checks = [
        bool(project_package.get("project_charter")), bool(epics), bool(stories), bool(tasks),
        bool(dependency_edges), bool(release_gates),
    ]
    planning_completeness = round(100 * sum(planning_checks) / len(planning_checks), 1)
    project_health = {
        "readiness_score": 0.0,
        "readiness_status": "NOT_EXECUTION_READY",
        "planning_completeness_percent": planning_completeness,
        "execution_readiness": {"score": 0, "status": "BLOCKED", "reason": "This package grants no execution authority and contains no live approval or runtime evidence."},
        "capacity_readiness": {"score": 0, "status": "UNVERIFIED", "reason": "No live capacity, availability, or skill evidence was supplied."},
        "release_readiness": {"score": 0, "status": "BLOCKED", "reason": "Release gates and rollback strategy are proposals; no approvals or verification evidence exist."},
        "execution_authorized": False,
        "basis": "Operational readiness is intentionally 0 until separate evidence and authorized decisions exist; planning completeness is reported separately.",
    }

    dashboards = {
        "milestone_dashboard": {"milestones": milestones, "total": len(milestones), "scheduled": 0},
        "capacity_dashboard": {"roles": role_forecasts, "live_capacity": "UNAVAILABLE"},
        "risk_dashboard": {"risk_count": len(risks), "high_risk_count": sum(item["severity"] == "HIGH" for item in risks), "status": "PLANNING_ESTIMATE"},
        "sprint_dashboard": {"sprints": simulated_sprints, "historical_velocity": None},
        "release_dashboard": {"waves": release_plan["deployment_waves"], "deployment_performed": False},
    }

    predicted_outcomes = []
    for scenario, forecast_sprints, risk_level in (
        ("Base assumptions", total_sprints, "MEDIUM"),
        ("Constrained capacity", constrained_sprints, "HIGH" if constrained_sprints > total_sprints else "MEDIUM"),
    ):
        predicted_outcomes.append({
            "scenario": scenario, "estimated_sprints": forecast_sprints,
            "delivery_date": None, "risk": risk_level,
            "predicted_state": "PLAN_ONLY_NO_EXECUTION",
            "execution_started": False, "project_changed": False,
            "assignment_changed": False,
        })
    execution_simulator = {
        "mode": "DETERMINISTIC_SCENARIO_SIMULATION",
        "scenarios": predicted_outcomes,
        "sprint_completion_projection": [{
            "sprint": item["sprint"], "planned_points": item["planned_points"],
            "scope_completion_projection_percent": item["scope_completion_projection_percent"],
            "forecast": "WITHIN_ASSUMED_CAPACITY" if item["simulated_sprint_completion"] else "OVER_ASSUMED_CAPACITY",
            "simulated_only": True,
        } for item in simulated_sprints],
        "simulated_resource_constraints": ["30% velocity reduction scenario", "No live role capacity scenario"],
        "delays": [{"trigger": "Predecessor epic slips one sprint", "impact": "Dependent epic earliest start moves by one sprint", "simulated_only": True}],
        "risk_events": [{"event": "Security gate evidence missing", "impact": "Release forecast remains blocked until independently reviewed", "simulated_only": True}],
        "runtime_executed": False,
    }
    executive_package = {
        "executive_summary": f"{charter.get('project_name', 'Project')} has {len(epics)} proposed epics, {len(stories)} stories, and an assumption-based estimate of {total_sprints} sprint(s). Operational readiness is not established.",
        "execution_plan": delivery_sequence,
        "sprint_plan": sprint_simulation,
        "capacity_plan": capacity_forecast,
        "risk_register": risk_register,
        "release_plan": release_plan,
        "readiness_assessment": project_health,
    }

    return {
        "package": "Autonomous Delivery Factory",
        "status": "PLANNING_AND_SIMULATION_ONLY",
        "source_project": {"name": charter.get("project_name"),
                           "priority": charter.get("priority"),
                           "epic_count": len(epics), "story_count": len(stories),
                           "task_outline_count": len(tasks)},
        "assumptions": {"velocity_story_points_per_sprint": assumed_velocity,
                        "capacity_hours_per_sprint": {discipline: profile["capacity_hours_per_sprint"] for discipline, profile in ROLE_PROFILES.items()},
                        "effort_hours_per_story_point": hours_per_point,
                        "historical_velocity_available": False,
                        "live_roster_or_calendar_used": False},
        "delivery_blueprint": {"delivery_sequence": delivery_sequence,
                               "critical_path": critical_path,
                               "dependencies": dependency_edges,
                               "milestones": milestones,
                               "critical_path_sprint_estimate": total_sprints},
        "capacity_forecast": capacity_forecast,
        "sprint_simulation": sprint_simulation,
        "agent_execution_plan": agent_execution_plan,
        "release_plan": release_plan,
        "risk_register": risk_register,
        "project_health": project_health,
        "delivery_dashboard": dashboards,
        "execution_simulator": execution_simulator,
        "executive_delivery_package": executive_package,
        "controls": {"project_created": False, "tasks_created": False,
                     "assignments_created": False, "runtime_started": False,
                     "deployment_performed": False, "persistence": False,
                     "approval_authority_granted": False},
    }