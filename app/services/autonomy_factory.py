"""Level 4 controlled-autonomy design artifacts; design only, no autonomous action."""

from __future__ import annotations

from typing import Any

RISK_TIERS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
LEVELS = (1, 2, 3, 4, 5)
IMPACT_LABELS = {1: "Negligible", 2: "Minor", 3: "Moderate", 4: "Major", 5: "Severe"}
LIKELIHOOD_LABELS = {1: "Rare", 2: "Unlikely", 3: "Possible", 4: "Likely", 5: "Almost certain"}
RISK_THRESHOLDS = (
    {"tier": "LOW", "min_score": 1, "max_score": 4},
    {"tier": "MEDIUM", "min_score": 5, "max_score": 9},
    {"tier": "HIGH", "min_score": 10, "max_score": 16},
    {"tier": "CRITICAL", "min_score": 17, "max_score": 25},
)
# Future ceilings are design proposals; none is enabled today.
TIER_POLICY = {
    "LOW": {"future_autonomy_ceiling": "SUPERVISED_AUTO_WITH_NOTIFICATION", "approvals": ["Service Owner post-hoc review"],
            "governance": ["Audit record", "Reversibility proof", "Kill switch coverage"]},
    "MEDIUM": {"future_autonomy_ceiling": "HUMAN_APPROVAL_BEFORE_ACTION", "approvals": ["Service Owner", "Governance reviewer"],
               "governance": ["Audit record", "Tested rollback", "Policy check", "Kill switch coverage"]},
    "HIGH": {"future_autonomy_ceiling": "RECOMMEND_ONLY", "approvals": ["Service Owner", "Security/Platform Owner", "Change Authority"],
             "governance": ["Independent review", "Tested rollback", "Evidence package", "Change window"]},
    "CRITICAL": {"future_autonomy_ceiling": "HUMAN_ONLY", "approvals": ["Owner", "Security Lead", "Governance Board"],
                 "governance": ["Board-level approval", "Step-up verification", "Tested recovery", "Complete audit evidence"]},
}


def classify_risk(likelihood: int, impact: int) -> dict[str, Any]:
    """Score likelihood x impact; severe impact never classifies below HIGH."""
    likelihood = max(1, min(5, int(likelihood)))
    impact = max(1, min(5, int(impact)))
    score = likelihood * impact
    tier = next(t["tier"] for t in RISK_THRESHOLDS if t["min_score"] <= score <= t["max_score"])
    if impact == 5 and RISK_TIERS.index(tier) < RISK_TIERS.index("HIGH"):
        tier = "HIGH"
    return {"likelihood": likelihood, "impact": impact, "score": score, "tier": tier}


def _decision(decision_id: str, name: str, category: str, likelihood: int, impact: int, reversible: bool) -> dict[str, Any]:
    risk = classify_risk(likelihood, impact)
    if not reversible and risk["tier"] in ("LOW", "MEDIUM"):
        risk["tier"] = "HIGH"
    return {"decision_id": decision_id, "name": name, "category": category, "risk": risk,
            "risk_tier": risk["tier"], "reversible": reversible,
            "future_autonomy_ceiling": TIER_POLICY[risk["tier"]]["future_autonomy_ceiling"],
            "autonomy_enabled": False, "authority": "NONE", "action_allowed": False}


def _decision_inventory() -> list[dict[str, Any]]:
    return [
        _decision("DEC-01", "Draft status summary or report", "Reporting", 1, 1, True),
        _decision("DEC-02", "Reorder non-binding recommendations", "Planning", 2, 2, True),
        _decision("DEC-03", "Re-run read-only validation", "Quality", 2, 2, True),
        _decision("DEC-04", "Reprioritize task backlog", "Delivery", 3, 2, True),
        _decision("DEC-05", "Propose agent assignment", "Workforce", 3, 3, True),
        _decision("DEC-06", "Update non-production configuration", "Operations", 3, 3, True),
        _decision("DEC-07", "Approve release candidate to QA", "Delivery", 3, 3, True),
        _decision("DEC-08", "Execute agent assignment", "Workforce", 3, 4, True),
        _decision("DEC-09", "Activate or retire an agent", "Workforce", 3, 4, False),
        _decision("DEC-10", "Deploy to UAT", "Deployment", 3, 4, True),
        _decision("DEC-11", "Scale or change hosting capacity", "Hosting", 3, 4, True),
        _decision("DEC-12", "Apply security patch", "Operations", 3, 4, True),
        _decision("DEC-13", "Deploy to production", "Deployment", 4, 5, False),
        _decision("DEC-14", "Change access control or identity", "Security", 4, 5, False),
        _decision("DEC-15", "Modify or restore production data", "Data", 2, 5, False),
        _decision("DEC-16", "Provision or delete infrastructure", "Hosting", 4, 5, False),
        _decision("DEC-17", "Execute production rollback or failover", "Operations", 3, 5, False),
        _decision("DEC-18", "Disable governance control or kill switch", "Governance", 2, 5, False),
    ]


def _policy(tier: str) -> dict[str, Any]:
    base = TIER_POLICY[tier]
    return {"policy_id": f"POL-{tier}", "risk_tier": tier, "future_autonomy_ceiling": base["future_autonomy_ceiling"],
            "approval_requirements": base["approvals"], "governance_requirements": base["governance"],
            "default_effect": "DENY", "policy_enabled": False}


def _readiness(name: str, checks: dict[str, bool]) -> dict[str, Any]:
    passed = sum(checks.values())
    return {"domain": name, "status": "NOT READY" if passed < len(checks) else "READY_FOR_REVIEW",
            "score_percent": round(100 * passed / len(checks), 1), "checks": checks,
            "blockers": [key for key, ok in checks.items() if not ok]}


def build_autonomy_package(blueprint: dict[str, Any] | None) -> dict[str, Any]:
    """Compose controlled-autonomy design artifacts from a workforce blueprint; takes no action."""
    source = blueprint if isinstance(blueprint, dict) else {}
    title = source.get("requirement", {}).get("title") or "Proposed Service"
    inventory = _decision_inventory()
    by_tier = {tier: [d for d in inventory if d["risk_tier"] == tier] for tier in RISK_TIERS}
    categories = sorted({d["category"] for d in inventory})
    decision_catalog = {
        "decision_inventory": inventory,
        "decision_categories": [{"category": c, "decision_ids": [d["decision_id"] for d in inventory if d["category"] == c]} for c in categories],
        "tier_counts": {tier: len(items) for tier, items in by_tier.items()},
        "classification_basis": "Likelihood x impact with severe-impact and irreversibility escalation.",
    }

    policies = [_policy(tier) for tier in RISK_TIERS]
    policy_engine = {
        "autonomy_policies": policies,
        "approval_requirements": {p["risk_tier"]: p["approval_requirements"] for p in policies},
        "governance_requirements": {p["risk_tier"]: p["governance_requirements"] for p in policies},
        "policy_coverage": {"decisions_total": len(inventory),
                            "decisions_covered": sum(1 for d in inventory if d["risk_tier"] in TIER_POLICY),
                            "coverage_percent": 100.0, "uncovered_decisions": [],
                            "default_effect": "DENY", "policies_enabled": False},
    }

    risk_matrix = {
        "risk_matrix": [{"likelihood": l, "impact": i, **{k: v for k, v in classify_risk(l, i).items() if k in ("score", "tier")}}
                        for l in LEVELS for i in LEVELS],
        "impact_matrix": [{"level": k, "label": v} for k, v in IMPACT_LABELS.items()],
        "likelihood_matrix": [{"level": k, "label": v} for k, v in LIKELIHOOD_LABELS.items()],
        "risk_thresholds": list(RISK_THRESHOLDS),
        "escalation_rules": ["Impact 5 classifies as at least HIGH", "Irreversible decisions classify as at least HIGH"],
        "scores_are_estimates": True,
    }

    override = {
        "override_rules": ["A named human may halt, veto, or reverse any autonomous decision at any time",
                           "Override takes precedence over every policy and requires no justification to halt",
                           "Kill switch must stop all autonomous decisions and is independent of the autonomy engine"],
        "escalation_rules": ["LOW anomalies notify the Service Owner", "MEDIUM anomalies require Governance reviewer acknowledgement",
                             "HIGH/CRITICAL anomalies page Security/Platform Owner and halt the decision class",
                             "Unanswered escalation fails closed to HUMAN_ONLY"],
        "exception_rules": ["Exceptions are time-boxed, owner-approved, and recorded with evidence",
                            "No exception may waive CRITICAL-tier approval or kill switch",
                            "Expired exceptions revert automatically to DENY"],
        "recovery_rules": ["Resume only after human root-cause review", "Restore autonomy one tier at a time",
                           "Preserve audit evidence for every override"],
        "overrides_executed": False,
    }

    rollback = {
        "rollback_policies": ["Every autonomous action needs a verified rollback plan before approval",
                              "Irreversible actions are HUMAN_ONLY", "Rollback needs a named owner and tested procedure"],
        "rollback_triggers": ["Policy or approval violation", "Error or health threshold breach", "Audit gap",
                              "Human override or kill switch", "Anomalous decision rate"],
        "recovery_procedures": ["Halt the decision class", "Preserve logs and evidence", "Restore last verified state after owner approval",
                                "Validate integrity, then conduct blameless review"],
        "safety_controls": ["Global kill switch", "Rate and blast-radius limits", "Dry-run before action",
                            "Segregation of duties", "Fail-closed defaults"],
        "rollback_tested": False, "rollbacks_executed": False,
    }

    def has(key: str) -> bool:
        return bool(source.get(key))

    readiness_domains = {
        "governance_readiness": _readiness("Governance", {
            "policy_framework_designed": True, "risk_matrix_designed": True, "override_framework_designed": True,
            "policies_approved_by_governance_board": False, "kill_switch_implemented_and_tested": False}),
        "workforce_readiness": _readiness("Workforce", {
            "lifecycle_package_designed": has("agent_lifecycle_package"), "assignment_framework_designed": has("assignment_framework"),
            "certified_agents_verified": False, "agent_performance_baseline": False}),
        "delivery_readiness": _readiness("Delivery", {
            "delivery_plan_present": has("delivery_execution_package"), "build_and_test_evidence_verified": False,
            "deployment_gates_verified": False}),
        "operations_readiness": _readiness("Operations", {
            "operations_plan_present": has("operations_execution_package"), "monitoring_configured": False,
            "incident_owners_confirmed": False, "rollback_tested": False}),
    }
    all_checks = [ok for d in readiness_domains.values() for ok in d["checks"].values()]
    overall = {"status": "NOT READY", "score_percent": round(100 * sum(all_checks) / len(all_checks), 1),
               "blockers": [f"{d['domain']}: {b}" for d in readiness_domains.values() for b in d["blockers"]],
               "basis": "Design completeness only; no operational evidence verifies autonomy safety."}
    readiness_report = {**readiness_domains, "overall_autonomy_readiness": overall}

    dashboard = {
        "decision_dashboard": {"tier_counts": decision_catalog["tier_counts"], "total": len(inventory), "autonomous_decisions_enabled": 0},
        "risk_dashboard": {"thresholds": list(RISK_THRESHOLDS), "irreversible_decisions": sum(1 for d in inventory if not d["reversible"])},
        "policy_dashboard": {"policies": len(policies), "policies_enabled": 0, "coverage_percent": 100.0},
        "readiness_dashboard": {"overall": overall["status"], "score_percent": overall["score_percent"],
                                "domains": {k: v["status"] for k, v in readiness_domains.items()}},
    }

    scenarios = [
        {"scenario": "approval", "decision_id": "DEC-10", "steps": ["Classify as HIGH", "Collect Service Owner, Security/Platform Owner, and Change Authority approval", "Verify rollback and evidence"],
         "forecast_outcome": "Proceeds only after every required human approval; simulated, not executed."},
        {"scenario": "override", "decision_id": "DEC-04", "steps": ["Human issues halt", "Decision class suspended", "Audit evidence preserved"],
         "forecast_outcome": "Human override wins over policy; no action continues."},
        {"scenario": "rollback", "decision_id": "DEC-12", "steps": ["Health threshold breach trigger", "Halt decision class", "Owner approves recovery per tested procedure"],
         "forecast_outcome": "Rollback requires owner approval; nothing is rolled back in simulation."},
        {"scenario": "blocked", "decision_id": "DEC-13", "steps": ["Classify as CRITICAL", "Autonomy ceiling is HUMAN_ONLY", "Readiness NOT READY"],
         "forecast_outcome": "Blocked: autonomous production deployment is never permitted by this design."},
    ]
    simulation = {"scenarios": scenarios, "actions_executed": False, "runtime_executed": False}

    executive_summary = {
        "summary": f"Level 4 controlled-autonomy design for {title} is complete as a framework but autonomy readiness is NOT READY. No autonomous action is enabled.",
        "decision_counts": decision_catalog["tier_counts"],
        "top_risks": ["No approved governance policies", "No tested kill switch or rollback", "No verified certified agent evidence"],
        "decisions_required": ["Governance Board approval of tier policies", "Approve risk thresholds", "Fund kill switch and rollback testing"],
        "readiness": overall,
    }
    blueprint_out = {
        "service_name": title,
        "operating_model": "Human-governed autonomy: risk-tiered decisions, default deny, human override, verified rollback.",
        "autonomy_levels": {"level_3": "Supervised approval sandbox (current)", "level_4": "Controlled autonomy (design only)"},
        "tiers": list(RISK_TIERS),
        "autonomy_enabled": False,
    }
    autonomy_package = {
        "autonomy_blueprint": blueprint_out,
        "policy_package": policy_engine,
        "risk_package": risk_matrix,
        "override_package": override,
        "rollback_package": rollback,
        "readiness_report": readiness_report,
        "executive_summary": executive_summary,
    }
    return {
        "package": "Level 4 Controlled Autonomy Design",
        "status": "DESIGN_ONLY",
        "authority": "NONE", "action_allowed": False, "persistence": False,
        "autonomy_blueprint": blueprint_out,
        "autonomy_readiness_report": readiness_report,
        "decision_catalog": decision_catalog,
        "autonomy_policy_engine": policy_engine,
        "risk_matrix_engine": risk_matrix,
        "human_override_framework": override,
        "rollback_governance": rollback,
        "autonomy_dashboard": dashboard,
        "autonomy_simulation": simulation,
        "executive_summary": executive_summary,
        "controlled_autonomy_package": autonomy_package,
        "controls": {"autonomous_actions": False, "provisioning": False, "assignment_executed": False,
                     "deployment_executed": False, "production_actions": False, "agents_activated": False,
                     "cloud_actions": False, "runtime_started": False, "persistence": False},
    }
