"""Read-only executive dashboard aggregation; unknown values stay unavailable, no actions."""

from __future__ import annotations

from typing import Any

UNAVAILABLE = "UNAVAILABLE"


def _d(source: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(source, dict):
            return None
        source = source.get(key)
    return source


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _pct(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def build_executive_command_center(blueprint: dict[str, Any] | None) -> dict[str, Any]:
    """Aggregate existing planning packages into executive dashboards without inventing measurements."""
    bp = blueprint if isinstance(blueprint, dict) else {}
    project = bp.get("project_delivery_package") or {}
    delivery = bp.get("delivery_execution_package") or {}
    testing = bp.get("testing_execution_package") or {}
    build = bp.get("build_execution_package") or {}
    deployment = bp.get("deployment_execution_package") or {}
    hosting = bp.get("hosting_execution_package") or {}
    operations = bp.get("operations_execution_package") or {}
    assignment = bp.get("assignment_recommendation_package") or {}
    lifecycle = bp.get("agent_lifecycle_package") or {}
    sandbox = bp.get("approval_sandbox_package") or {}
    autonomy = bp.get("autonomy_execution_package") or {}
    enterprise = bp.get("autonomous_enterprise_package") or {}
    title = _d(bp, "requirement", "title") or _d(project, "project_charter", "project_name") or "Proposed Portfolio"

    quality_statuses = {
        "testing_readiness": _d(testing, "release_assessment", "status") or UNAVAILABLE,
        "build_readiness": _d(build, "build_readiness_assessment", "status") or UNAVAILABLE,
        "deployment_readiness": _d(deployment, "deployment_readiness_report", "status") or UNAVAILABLE,
        "hosting_readiness": _d(hosting, "hosting_readiness_report", "status") or UNAVAILABLE,
        "operations_readiness": _d(operations, "operations_readiness_report", "status") or UNAVAILABLE,
    }
    quality_scores = {
        "testing_readiness": _num(_d(testing, "quality_dashboard", "quality_score_observed")),
        "build_readiness": _num(_d(build, "build_readiness_assessment", "readiness_score_percent")),
        "deployment_readiness": _num(_d(deployment, "deployment_readiness_report", "readiness_score_percent")),
        "hosting_readiness": _num(_d(hosting, "hosting_readiness_report", "readiness_score_percent")),
        "operations_readiness": _num(_d(operations, "operations_readiness_report", "readiness_score_percent")),
    }
    quality_dashboard = {
        key: {"status": quality_statuses[key], "score_percent": quality_scores[key]} for key in quality_statuses
    }
    quality_dashboard["overall_status"] = ("READY" if all(s == "READY" for s in quality_statuses.values())
                                           else "NOT READY")

    # Workforce
    director = _d(assignment, "workforce_director_dashboard") or {}
    coverage = director.get("coverage") or {}
    required_roles = coverage.get("roles_required") or len(bp.get("roles") or [])
    qualified = coverage.get("roles_with_qualified_candidates") or 0
    capacity = director.get("capacity") or {}
    gaps = director.get("skill_gaps") or []
    cert_plan = _d(lifecycle, "workforce_director_report", "certification_coverage_plan") or {}
    certs_issued = cert_plan.get("issued_count") or 0
    workforce_dashboard = {
        "workforce_readiness": {"status": _d(assignment, "assignment_readiness", "verified_readiness_status") or UNAVAILABLE,
                                "score_percent": _num(_d(assignment, "assignment_readiness", "verified_readiness_score_percent"))},
        "capacity_coverage": {"required_hours": capacity.get("required_hours"), "available_hours": capacity.get("available_hours"),
                              "status": capacity.get("status") or UNAVAILABLE},
        "skill_coverage": {"roles_required": required_roles, "roles_with_qualified_candidates": qualified,
                           "coverage_percent": _pct(qualified, required_roles),
                           "disciplines_with_gaps": len(gaps)},
        "certification_coverage": {"certifications_issued": certs_issued,
                                   "status": cert_plan.get("coverage_status") or UNAVAILABLE},
        "replacement_readiness": director.get("replacement_readiness") or UNAVAILABLE,
        "assignment_readiness": {"status": _d(assignment, "assignment_readiness", "status") or UNAVAILABLE,
                                 "can_project_be_staffed": _d(assignment, "execution_readiness_report", "can_project_be_staffed")},
    }

    # Delivery
    sprint = project.get("sprint_plan") or {}
    delivery_dashboard = {
        "projects": 1 if project else 0,
        "epics": len(project.get("epic_catalog") or []),
        "features": len(project.get("feature_catalog") or []),
        "stories": len(project.get("user_story_catalog") or []),
        "tasks": len(project.get("task_catalog") or []),
        "sprint_health": {"sprints_estimated": sprint.get("sprint_count_estimate"),
                          "total_story_points": sprint.get("total_story_points"),
                          "historical_velocity": sprint.get("historical_velocity"),
                          "constrained_velocity": _d(delivery, "sprint_simulation", "constrained_velocity_story_points"),
                          "basis": "Planning assumptions; no live sprint data"},
        "release_readiness": {"status": _d(delivery, "project_health", "readiness_status") or UNAVAILABLE,
                              "score_percent": _num(_d(delivery, "project_health", "readiness_score")),
                              "release_gates": len(_d(delivery, "release_plan", "release_gates") or [])},
    }

    # Governance
    analytics = sandbox.get("governance_analytics") or {}
    approval = sandbox.get("approval_readiness") or {}
    governance_score = _num(analytics.get("governance_score"))
    governance_dashboard = {
        "approval_readiness": {"status": approval.get("status") or UNAVAILABLE,
                               "operational_approval_ready": bool(approval.get("operational_approval_ready")),
                               "blockers": approval.get("readiness_blockers") or []},
        "risk_index": {"approval_risk": analytics.get("approval_risk") or UNAVAILABLE,
                       "delivery_overall_risk": _d(delivery, "risk_register", "overall_risk") or UNAVAILABLE},
        "compliance_status": "NOT_ASSESSED_NO_COMPLIANCE_EVIDENCE",
        "override_analytics": {"override_frequency": analytics.get("override_frequency") or UNAVAILABLE,
                               "tracking_enabled": bool(_d(sandbox, "override_management", "override_tracking_enabled"))},
        "governance_score": governance_score if governance_score is not None else UNAVAILABLE,
    }

    # Autonomy
    inventory = _d(autonomy, "decision_catalog", "decision_inventory") or []
    tiers = {d.get("risk_tier") for d in inventory}
    override = autonomy.get("human_override_framework") or {}
    autonomy_dashboard = {
        "autonomy_readiness": _d(autonomy, "autonomy_readiness_report", "overall_autonomy_readiness") or {"status": UNAVAILABLE},
        "decision_coverage": {"decisions_classified": len(inventory),
                              "autonomous_decisions_enabled": sum(1 for d in inventory if d.get("autonomy_enabled"))},
        "risk_coverage": {"tiers_defined": len(tiers), "tiers_expected": 4,
                          "policy_coverage_percent": _d(autonomy, "autonomy_policy_engine", "policy_coverage", "coverage_percent")},
        "override_coverage": {"rule_groups_defined": sum(1 for k in ("override_rules", "escalation_rules", "exception_rules", "recovery_rules") if override.get(k)),
                              "overrides_executed": bool(override.get("overrides_executed"))},
    }

    # CEO
    goals = _d(project, "project_charter", "goals") or []
    outcomes = _d(project, "project_charter", "business_outcomes") or []
    risk_items = list((_d(delivery, "risk_register", "risks") or [])[:5])
    executive_risks = [{"risk": r.get("description") or r.get("risk") or str(r), "severity": r.get("severity")}
                       if isinstance(r, dict) else {"risk": str(r), "severity": None} for r in risk_items]
    executive_risks += [{"risk": b, "severity": "HIGH"} for b in (enterprise.get("executive_summary") or {}).get("blockers", [])[:3]]
    ceo_dashboard = {
        "portfolio_health": {"portfolio": title, "projects": delivery_dashboard["projects"],
                             "delivery_readiness": delivery_dashboard["release_readiness"]["status"],
                             "quality_overall": quality_dashboard["overall_status"], "basis": "Planning evidence only"},
        "strategic_objectives": [{"objective": g, "status": "PROPOSED_NOT_MEASURED"} for g in goals],
        "business_outcomes": outcomes,
        "roi_forecast": {"value": None, "status": "UNAVAILABLE_NO_BUSINESS_CASE_INPUTS",
                         "basis": "Cost, benefit, and baseline figures were not supplied; none are inferred."},
        "investment_status": {"approved_budget": None, "committed_spend": None, "status": "UNAVAILABLE_NO_FINANCIAL_DATA"},
        "executive_risks": executive_risks,
    }

    # Overall
    scores = [s for s in quality_scores.values() if s is not None]
    scores += [s for s in (workforce_dashboard["workforce_readiness"]["score_percent"],
                           delivery_dashboard["release_readiness"]["score_percent"],
                           _num(autonomy_dashboard["autonomy_readiness"].get("score_percent"))) if s is not None]
    domains = {
        "workforce": workforce_dashboard["workforce_readiness"]["status"],
        "delivery": delivery_dashboard["release_readiness"]["status"],
        "quality": quality_dashboard["overall_status"],
        "governance": approval.get("status") or UNAVAILABLE,
        "autonomy": autonomy_dashboard["autonomy_readiness"].get("status", UNAVAILABLE),
        "enterprise": _d(enterprise, "enterprise_architecture") and "ARCHITECTURE_ONLY_NOT_READY" or UNAVAILABLE,
    }
    enterprise_readiness = {
        "status": "NOT READY",
        "average_known_score_percent": round(sum(scores) / len(scores), 1) if scores else None,
        "known_score_count": len(scores),
        "domain_status": domains,
        "basis": "Average covers only available numeric scores; unavailable values are not treated as passing.",
    }
    executive_dashboard = {
        "ceo_dashboard": ceo_dashboard, "workforce_dashboard": workforce_dashboard,
        "delivery_dashboard": delivery_dashboard, "quality_dashboard": quality_dashboard,
        "governance_dashboard": governance_dashboard, "autonomy_dashboard": autonomy_dashboard,
        "enterprise_readiness": enterprise_readiness,
    }
    return {
        "package": "Executive Command Center",
        "status": "DASHBOARD_ONLY",
        "authority": "NONE", "action_allowed": False, "persistence": False,
        "portfolio": title,
        **executive_dashboard,
        "executive_dashboard": executive_dashboard,
        "controls": {"actions_performed": False, "workflows_executed": False, "approvals_created": False,
                     "assignments_executed": False, "deployments_executed": False, "runtime_started": False,
                     "cloud_actions": False, "persistence": False},
    }
