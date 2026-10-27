"""Level 3 approval workflow simulation; recommendations never become decisions."""

from __future__ import annotations

from typing import Any


APPROVAL_TYPES = ("worker", "assignment", "certification", "release", "governance")
REVIEW_STATES = ("PENDING_HUMAN_REVIEW", "IN_REVIEW", "NEEDS_INFORMATION", "ESCALATED", "CLOSED")
HUMAN_DECISIONS = ("APPROVE", "REJECT", "REQUEST_INFORMATION", "OVERRIDE")


def _recommendation(approval_type: str, *, evidence_present: bool, missing: list[str], risk: str) -> dict[str, Any]:
    return {
        "type": approval_type,
        "recommendation": "RECOMMEND_REVIEW" if evidence_present else "INSUFFICIENT_EVIDENCE",
        "status": "PENDING_HUMAN_REVIEW",
        "risk": risk,
        "evidence_present": evidence_present,
        "missing_evidence": missing,
        "authority": "NONE",
        "decision_made": False,
        "decision_persisted": False,
    }


def build_approval_sandbox_package(workforce_blueprint: dict[str, Any]) -> dict[str, Any]:
    """Produce transient approval recommendation and review workflow plans only."""
    if not isinstance(workforce_blueprint, dict) or not isinstance(workforce_blueprint.get("requirement"), dict):
        raise ValueError("A workforce blueprint with requirement context is required")
    lifecycle = workforce_blueprint.get("agent_lifecycle_package", {})
    assignment = workforce_blueprint.get("assignment_recommendation_package", {})
    project = workforce_blueprint.get("project_delivery_package", {})
    delivery = workforce_blueprint.get("delivery_execution_package", {})
    testing = workforce_blueprint.get("testing_execution_package", {})
    build = workforce_blueprint.get("build_execution_package", {})
    deployment = workforce_blueprint.get("deployment_execution_package", {})
    operations = workforce_blueprint.get("operations_execution_package", {})

    scoped_profiles = lifecycle.get("agent_profiles", [])
    worker = _recommendation("worker", evidence_present=bool(scoped_profiles),
        missing=[] if scoped_profiles else ["Approved workforce role profile", "Named human owner", "Current skill evidence"],
        risk="HIGH")
    assignment_ready_status = assignment.get("assignment_readiness", {}).get("status")
    assignment_item = _recommendation("assignment",
        evidence_present=bool(assignment.get("assignment_blueprint", {}).get("work_items")),
        missing=["Independently verified candidate identity", "Current skill/certification evidence", "Live availability and capacity", "Work-item authorization"],
        risk="HIGH")
    if assignment_ready_status == "PARTIALLY_READY":
        assignment_item["recommendation"] = "RECOMMEND_REVIEW_WITH_UNVERIFIED_CLAIMS"
    certification = _recommendation("certification", evidence_present=bool(lifecycle.get("certification_paths")),
        missing=["Completed training evidence", "Independent evaluation results", "Authorized certification reviewer", "Expiry/renewal verification"],
        risk="HIGH")
    deployment_status = deployment.get("deployment_readiness_report", {}).get("status")
    release = _recommendation("release", evidence_present=bool(deployment),
        missing=["Observed successful build", "Executed test/security evidence", "Verified hosting/infrastructure readiness", "Rollback/restore test", "Authorized release decision"],
        risk="CRITICAL")
    release["source_readiness"] = deployment_status or "UNAVAILABLE"
    governance = _recommendation("governance", evidence_present=bool(operations or deployment),
        missing=["Named accountable owners", "Approved policies and control evidence", "Independent audit verification", "Recorded human decision"],
        risk="CRITICAL")

    recommendations = {
        "worker": worker, "assignment": assignment_item, "certification": certification,
        "release": release, "governance": governance,
    }
    review_queue = []
    for index, approval_type in enumerate(APPROVAL_TYPES, start=1):
        rec = recommendations[approval_type]
        review_queue.append({
            "sandbox_item_id": f"SIM-APR-{index:03d}",
            "approval_type": approval_type,
            "resource": workforce_blueprint["requirement"].get("title", "Requirement"),
            "recommendation": rec["recommendation"],
            "reviewer_role": {"worker": "Workforce Manager", "assignment": "Workforce Manager",
                              "certification": "Certification Authority", "release": "Owner/Release Authority",
                              "governance": "Owner/Governance Authority"}[approval_type],
            "state": "PENDING_HUMAN_REVIEW",
            "missing_evidence": rec["missing_evidence"],
            "decision_options": list(HUMAN_DECISIONS),
            "review_record_created": False,
            "decision_persisted": False,
        })

    evidence_checks = {
        "workforce_blueprint_present": bool(scoped_profiles),
        "project_plan_present": bool(project.get("epic_catalog")),
        "delivery_plan_present": bool(delivery.get("delivery_blueprint")),
        "testing_plan_present": bool(testing.get("test_execution_package")),
        "build_plan_present": bool(build.get("build_execution_package")),
        "deployment_plan_present": bool(deployment.get("deployment_blueprint")),
        "operations_plan_present": bool(operations.get("operations_blueprint")),
        "independent_evidence_verified": False,
        "human_decision_recorded": False,
    }
    evidence_quality_score = round(100 * sum(evidence_checks.values()) / len(evidence_checks), 1)
    confidence_engine = {
        "recommendation_confidence_percent": None,
        "confidence_status": "UNCALIBRATED_NOT_REPORTED",
        "evidence_quality_score_percent": evidence_quality_score,
        "evidence_checks": evidence_checks,
        "decision_strength": "UNVERIFIED",
        "basis": "Package presence is not proof of truth, freshness, completeness, or approval. No calibrated decision dataset is supplied.",
    }

    override_categories = ["Evidence exception", "Policy exception", "Emergency handling", "Role/capacity exception", "Security exception"]
    override_management = {
        "categories": override_categories,
        "tracking_schema": ["override_id", "approval_item_id", "requester", "independent_approver", "category", "reason", "evidence_reference", "expiry", "review_outcome"],
        "override_tracking_enabled": False,
        "override_analytics": {"override_frequency": "UNAVAILABLE_NO_DECISIONS", "override_counts": None,
                               "outcome_correlation": "UNAVAILABLE_NO_PERSISTED_HISTORY"},
    }
    audit_event_schema = {
        "required_fields": ["sandbox_item_id", "actor_id", "actor_role", "action", "from_state", "to_state", "reason", "evidence_reference", "timestamp", "correlation_id"],
        "prohibited_fields": ["credentials", "raw_secrets", "unnecessary_sensitive_payload"],
        "append_only_design_required": True,
        "events_written": False,
    }
    review_workflow = {
        "states": list(REVIEW_STATES),
        "decision_states": list(HUMAN_DECISIONS),
        "escalation_paths": [
            {"trigger": "Missing required evidence", "target": "Evidence owner", "automatic_transition": False},
            {"trigger": "Security/privacy concern", "target": "Security/Privacy owner", "automatic_transition": False},
            {"trigger": "Reviewer deadline or high-risk exception", "target": "Governance authority", "automatic_transition": False},
        ],
        "separation_of_duties": "Recommender cannot act as the approving human for consequential decisions.",
        "workflow_executed": False,
    }

    simulations = [
        {"scenario": "recommendation_for_review", "proposed_state": "PENDING_HUMAN_REVIEW", "human_action": "None simulated", "simulation_only": True, "decision_persisted": False, "workflow_executed": False},
        {"scenario": "human_rejection", "proposed_state": "CLOSED_REJECTED", "human_action": "Illustrative human rejection only", "simulation_only": True, "decision_persisted": False, "workflow_executed": False},
        {"scenario": "human_override", "proposed_state": "OVERRIDE_REQUIRES_INDEPENDENT_REVIEW", "human_action": "Illustrative override schema only", "simulation_only": True, "decision_persisted": False, "workflow_executed": False},
        {"scenario": "escalation", "proposed_state": "ESCALATED_PENDING_HUMAN_REVIEW", "human_action": "Illustrative escalation only", "simulation_only": True, "decision_persisted": False, "workflow_executed": False},
    ]
    dashboard = {
        "approval_dashboard": {"recommendation_count": len(recommendations), "pending_human_review_count": len(review_queue), "operational_decisions": 0},
        "override_dashboard": override_management["override_analytics"],
        "audit_dashboard": {"audit_schema_defined": True, "audit_events_written": False, "history": "UNAVAILABLE_NO_PERSISTENCE"},
        "governance_dashboard": {"evidence_quality_score_percent": evidence_quality_score, "decision_strength": "UNVERIFIED", "governance_score": None},
    }
    governance_analytics = {
        "approval_accuracy": "UNAVAILABLE_NO_DECISIONS",
        "override_frequency": "UNAVAILABLE_NO_DECISIONS",
        "approval_risk": "HIGH_CONSERVATIVE_PLANNING_CLASSIFICATION",
        "governance_score": None,
        "basis": "No persisted decision outcomes exist; analytics are not fabricated.",
    }
    readiness = {
        "status": "REVIEW_PLAN_READY_NOT_OPERATIONALLY_READY" if review_queue else "NOT_READY",
        "recommendations_generated": len(recommendations),
        "human_review_required": True,
        "operational_approval_ready": False,
        "readiness_blockers": ["No approval workflow execution is enabled", "Evidence is not independently verified", "No human decisions are recorded"],
    }
    audit_package = {
        "decision_audit_trail": audit_event_schema,
        "event_schema": audit_event_schema,
        "approval_history_design": {"schema_fields": ["approval_item_id", "decision", "reviewer", "reason", "evidence", "decided_at", "correlation_id"], "history_persisted": False},
        "review_history_design": {"schema_fields": ["reviewer", "state_transition", "comments", "evidence_reference", "timestamp"], "history_persisted": False},
    }
    governance_package = {
        "recommendation_policy": "Recommendations may identify review need only; humans retain all decision authority.",
        "separation_of_duties": review_workflow["separation_of_duties"],
        "override_management": override_management,
        "analytics": governance_analytics,
        "operational_approval_enabled": False,
    }
    executive_summary = {
        "summary": "Level 3 supervised approval sandbox design is available for review; no operational approval workflow is enabled.",
        "recommendations": len(recommendations), "human_reviews_queued_in_simulation": len(review_queue),
        "confidence": "UNCALIBRATED_NOT_REPORTED", "governance_score": None,
        "authority": "NONE", "actions_taken": 0,
    }
    approval_execution_package = {
        "approval_package": {"recommendations": recommendations, "review_queue": review_queue, "readiness": readiness},
        "audit_package": audit_package,
        "governance_package": governance_package,
        "executive_summary": executive_summary,
    }
    return {
        "package": "Level 3 Supervised Approval Sandbox Simulation",
        "status": "SIMULATION_ONLY",
        "authority": "NONE", "action_allowed": False, "persistence": False,
        "approval_recommendation_engine": {"recommendations": recommendations,
                                            "recommendation_only": True,
                                            "operational_approvals_enabled": False},
        "recommendation_engine": {"recommendations": recommendations,
                      "recommendation_only": True,
                      "operational_approvals_enabled": False},
        "approval_readiness": readiness,
        "approval_workflow": review_workflow,
        "human_review_workflow": review_workflow,
        "review_queue": review_queue,
        "override_management": override_management,
        "confidence_engine": confidence_engine,
        "decision_audit": audit_package,
        "governance_analytics": governance_analytics,
        "approval_dashboard": {**dashboard["approval_dashboard"],
                       "approval_accuracy": governance_analytics["approval_accuracy"]},
        "override_dashboard": dashboard["override_dashboard"],
        "audit_dashboard": dashboard["audit_dashboard"],
        "governance_dashboard": dashboard["governance_dashboard"],
        "sandbox_simulation": {"scenarios": simulations, "simulation_only": True,
                               "workflow_executed": False, "decisions_persisted": False},
        "approval_execution_package": approval_execution_package,
        "controls": {"operational_approvals": False, "workflow_executed": False,
                     "decision_persisted": False, "audit_written": False,
                     "override_recorded": False, "assignment_executed": False,
                     "certification_issued": False, "release_executed": False,
                     "runtime_started": False, "persistence": False},
    }