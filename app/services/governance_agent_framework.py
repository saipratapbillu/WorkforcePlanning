"""Evidence-bound shadow reviews for AI governance roles.

This module deliberately has no database, network, or operational dependencies.
Its output is advisory and cannot authorize state changes.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


POLICY_VERSION = "shadow-governance-v1"
AUTONOMOUS_POLICY_VERSION = "controlled-eligibility-v1"
GOVERNANCE_POLICY_CATALOG_VERSION = "governance-policy-catalog-v1"
AUTONOMY_LEVEL = 2

ROLE_IMPACT = {
    "AI CEO": "CRITICAL",
    "AI Governance Board": "CRITICAL",
    "AI Security Officer": "CRITICAL",
    "AI Compliance Officer": "HIGH",
    "AI Data Steward": "HIGH",
    "AI Enterprise Architect": "HIGH",
    "AI Change Advisory Board": "CRITICAL",
    "AI Risk Officer": "HIGH",
    "AI Workforce Director": "HIGH",
    "AI Certification Authority": "HIGH",
    "AI Release Manager": "CRITICAL",
    "AI Runtime Controller": "CRITICAL",
    "AI Audit Officer": "HIGH",
    "AI Production Readiness Assessor": "CRITICAL",
}
IMPACT_SCORE = {"LOW": 25, "MEDIUM": 50, "HIGH": 75, "CRITICAL": 100}

ACTION_POLICY_DOMAINS = {
    "migration_approval": "migration",
    "ownership_approval": "ownership",
    "provider_approval": "provider",
    "model_approval": "model",
    "certification": "certification",
    "workforce_approval": "workforce",
    "adapter_approval": "adapter",
    "runtime_approval": "runtime",
    "security_review": "security",
    "low_risk_release": "release",
    "routine_governance_review": "ownership",
}
ACTION_REQUIRED_CHECKS = {
    "migration_approval": ("dependencies_verified", "cab_approval", "dba_approval", "backup_verified", "rollback_available", "post_deployment_verified"),
    "ownership_approval": ("exact_mappings_verified", "candidate_set_current", "data_steward_approval", "business_approval", "governance_approval", "reconciliation_complete"),
    "provider_approval": ("security_review_passed", "privacy_review_passed", "residency_review_passed", "data_handling_review_passed", "risk_assessment_complete", "independent_approval"),
    "model_approval": ("provider_approved", "policies_approved", "evaluations_passed", "risk_assessment_complete", "security_assessment_passed", "independent_review"),
    "certification": ("skill_evidence_complete", "evaluations_passed", "governance_requirements_met", "independent_review"),
    "workforce_approval": ("active_certified_agents", "skill_coverage_verified", "capacity_verified", "assignment_eligibility_verified", "independent_review"),
    "adapter_approval": ("provider_approved", "model_approved", "credential_reference_valid", "security_review_passed", "authorized_health_check_passed"),
    "runtime_approval": ("assignment_qualified", "queue_eligible", "execution_validated", "deliverable_accepted", "audit_trail_complete"),
    "security_review": ("rbac_verified", "api_security_verified", "secrets_reviewed", "audit_controls_verified", "negative_tests_passed", "independent_review"),
    "low_risk_release": ("rollback_available", "tests_passed", "security_passed", "audit_trail_complete", "change_approval", "release_approval"),
    "routine_governance_review": ("independent_review_complete",),
}
RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

GOVERNANCE_POLICIES: dict[str, dict[str, Any]] = {
    "migration": {"required_evidence": ["migration script hash", "dependency validation", "schema prerequisites", "CAB approval", "DBA approval", "backup verification", "rollback validation", "post-deployment verification"], "minimum_evidence_completeness": 100, "risk_threshold": "LOW", "impact_threshold": "LOW", "escalation_rules": ["Any missing CAB/DBA approval", "Unverified backup/rollback", "Script integrity mismatch"]},
    "ownership": {"required_evidence": ["candidate fingerprint", "exact GUID mapping", "data steward approval", "business approval", "governance approval", "rollback package", "post-change reconciliation"], "minimum_evidence_completeness": 100, "risk_threshold": "LOW", "impact_threshold": "LOW", "escalation_rules": ["Any unresolved or changed candidate", "Missing independent approval", "Coverage below 100%"]},
    "provider": {"required_evidence": ["security review", "privacy review", "data residency", "data handling", "risk assessment", "provider approval record"], "minimum_evidence_completeness": 100, "risk_threshold": "LOW", "impact_threshold": "LOW", "escalation_rules": ["Unassessed provider terms", "Unapproved data transfer", "Missing authorized decision"]},
    "model": {"required_evidence": ["immutable proposal", "risk assessment", "security assessment", "usage policy", "passing evaluations", "independent approval", "retirement plan"], "minimum_evidence_completeness": 100, "risk_threshold": "LOW", "impact_threshold": "LOW", "escalation_rules": ["Provider not approved", "Evaluation failure", "Self-approval or missing reviewer"]},
    "certification": {"required_evidence": ["active role profile", "validated skills", "Capability evaluation", "Safety evaluation", "Security evaluation", "Governance evaluation", "independent certification decision"], "minimum_evidence_completeness": 100, "risk_threshold": "LOW", "impact_threshold": "LOW", "escalation_rules": ["Any required evaluation missing/failed", "Skill evidence inactive", "No independent reviewer"]},
    "workforce": {"required_evidence": ["active certified agents", "skill coverage", "capacity coverage", "assignment eligibility", "workforce decision record"], "minimum_evidence_completeness": 100, "risk_threshold": "LOW", "impact_threshold": "LOW", "escalation_rules": ["No active certified agents", "Skill/capacity evidence missing", "Assignment violates role or workload limits"]},
    "adapter": {"required_evidence": ["approved provider", "approved model association", "credential reference", "security validation", "authorized health check", "adapter approval"], "minimum_evidence_completeness": 100, "risk_threshold": "LOW", "impact_threshold": "LOW", "escalation_rules": ["Raw/missing credential reference", "Provider/model mismatch", "Health check absent or failed"]},
    "runtime": {"required_evidence": ["approved requirement", "recorded approval", "project lineage", "qualified assignment", "eligible queue", "execution record", "reviewed deliverable", "audit trail"], "minimum_evidence_completeness": 100, "risk_threshold": "LOW", "impact_threshold": "LOW", "escalation_rules": ["Any missing gate", "Unauthorized execution", "Missing audit or deliverable lineage"]},
    "security": {"required_evidence": ["RBAC review", "API security review", "secrets review", "audit controls", "negative authorization tests", "security approval"], "minimum_evidence_completeness": 100, "risk_threshold": "LOW", "impact_threshold": "LOW", "escalation_rules": ["Access-control finding", "secret exposure", "negative test failure", "missing independent approval"]},
    "release": {"required_evidence": ["rollback available", "tests passed", "security passed", "audit trail complete", "change approval", "release approval"], "minimum_evidence_completeness": 100, "risk_threshold": "LOW", "impact_threshold": "LOW", "escalation_rules": ["Risk exceeds LOW", "Rollback/tests/security/audit evidence missing", "Change or release approval absent"]},
}


def get_governance_policies() -> dict[str, dict[str, Any]]:
    policies = json.loads(json.dumps(GOVERNANCE_POLICIES))
    owners = {
        "migration": "AI Change Advisory Board",
        "ownership": "AI Data Steward",
        "provider": "AI Governance Board",
        "model": "AI Governance Board",
        "certification": "AI Certification Authority",
        "workforce": "AI Workforce Director",
        "adapter": "AI Security Officer",
        "runtime": "AI Runtime Controller",
        "security": "AI Security Officer",
        "release": "AI Release Manager",
    }
    for domain, policy in policies.items():
        policy["policy_id"] = f"GOV-{domain.upper()}-001"
        policy["version"] = GOVERNANCE_POLICY_CATALOG_VERSION
        policy["owner"] = owners[domain]
        policy["domain"] = domain
    return policies

AGENT_ROLES: tuple[dict[str, Any], ...] = (
    {"role": "AI CEO", "scope": "Business value, portfolio, and executive recommendation", "gates": ("ownership_approved", "migration_applied", "providers_approved", "models_approved", "certifications_completed", "adapters_configured", "runtime_validated", "security_review_completed", "rls_approved")},
    {"role": "AI Governance Board", "scope": "Cross-domain evidence and governance gaps", "gates": ("ownership_approved", "migration_applied", "providers_approved", "models_approved", "certifications_completed", "adapters_configured", "runtime_validated", "security_review_completed", "rls_approved")},
    {"role": "AI Security Officer", "scope": "Security review and RLS evidence", "gates": ("security_review_completed", "rls_approved")},
    {"role": "AI Compliance Officer", "scope": "Compliance status and assessment evidence", "sources": ("compliance_monitor",)},
    {"role": "AI Data Steward", "scope": "Ownership mapping, coverage, and review evidence", "gates": ("ownership_approved",)},
    {"role": "AI Enterprise Architect", "scope": "Migration, adapter, and runtime dependencies", "gates": ("migration_applied", "adapters_configured", "runtime_validated")},
    {"role": "AI Change Advisory Board", "scope": "Change/migration readiness and rollback evidence", "gates": ("migration_applied",)},
    {"role": "AI Risk Officer", "scope": "Recorded risk assessment and mitigation state", "sources": ("risk_monitor",)},
    {"role": "AI Workforce Director", "scope": "Certification and operational workforce gates", "gates": ("certifications_completed", "runtime_validated")},
    {"role": "AI Certification Authority", "scope": "Certification gate and required evaluation evidence", "gates": ("certifications_completed",)},
    {"role": "AI Release Manager", "scope": "All release and operational readiness gates", "gates": ("ownership_approved", "migration_applied", "providers_approved", "models_approved", "certifications_completed", "adapters_configured", "runtime_validated", "security_review_completed", "rls_approved")},
    {"role": "AI Runtime Controller", "scope": "Runtime validation gate only; no queue/runtime controls", "gates": ("runtime_validated",)},
    {"role": "AI Audit Officer", "scope": "Observed audit event presence; completeness is not inferred", "sources": ("audit_timeline",)},
    {"role": "AI Production Readiness Assessor", "scope": "All production authorization gates", "gates": ("ownership_approved", "migration_applied", "providers_approved", "models_approved", "certifications_completed", "adapters_configured", "runtime_validated", "security_review_completed", "rls_approved")},
)


def _snapshot_fingerprint(snapshot: dict[str, Any]) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _gate_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for gate in snapshot.get("production_gate_monitor", []):
        name = str(gate.get("gate"))
        existing = indexed.get(name)
        if existing is None:
            indexed[name] = dict(gate)
            indexed[name]["_conflict_detected"] = False
            continue
        comparable = ("status", "authorization_status", "display_status", "current_evidence")
        if any(existing.get(field) != gate.get(field) for field in comparable):
            existing["_conflict_detected"] = True
            existing["_conflicting_records"] = int(existing.get("_conflicting_records", 1)) + 1
    return indexed


def _source_assessment(source_key: str, snapshot: dict[str, Any]) -> tuple[str, str, dict[str, Any] | None]:
    if source_key == "risk_monitor":
        source = snapshot.get("risk_monitor")
        if not source or str(source.get("status", "")).lower().startswith("unavailable") or source.get("status") == "Template: not assessed":
            return "UNVERIFIED", "No recorded risk assessment is available.", source
        return "RECOMMEND_REVIEW", "Risk source exists; an authorized reviewer must assess it.", source
    if source_key == "compliance_monitor":
        source = snapshot.get("compliance_monitor")
        if not source or source.get("status") in {"Not assessed", "Unavailable"}:
            return "UNVERIFIED", "No approved compliance assessment is available.", source
        return "RECOMMEND_REVIEW", "Compliance source exists; no legal/compliance determination is made here.", source
    if source_key == "audit_timeline":
        events = snapshot.get("change_activity", {}).get("audit_timeline")
        if not isinstance(events, list) or not events:
            return "UNVERIFIED", "No audit events were present in the supplied evidence snapshot.", None
        return "RECOMMEND_REVIEW", "Audit events are present; completeness and integrity require independent review.", {"observed_event_count": len(events)}
    return "UNVERIFIED", "Evidence source is not recognized.", None


def evaluate_decision_quality(
    findings: list[dict[str, Any]],
    *,
    role: str,
    evaluated_at: str | None = None,
    freshness_limit_days: int | None = None,
) -> dict[str, Any]:
    required = len(findings)
    verified = sum(item.get("status") == "VERIFIED" for item in findings)
    score = round(100 * verified / required, 1) if required else 0.0
    confidence_band = "LOW"
    freshness_values = []
    current_time = None
    freshness_invalid = False
    if evaluated_at and freshness_limit_days is not None:
        try:
            current_time = datetime.fromisoformat(evaluated_at.replace("Z", "+00:00"))
        except ValueError:
            current_time = None
    if current_time is not None and freshness_limit_days >= 0:
        for item in findings:
            evidence = item.get("evidence")
            timestamp = evidence.get("CreatedAtUtc") or evidence.get("created_at_utc") if isinstance(evidence, dict) else None
            if not timestamp:
                freshness_values = []
                break
            try:
                observed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                if observed.tzinfo is None and current_time.tzinfo is not None:
                    observed = observed.replace(tzinfo=timezone.utc)
                if current_time.tzinfo is None and observed.tzinfo is not None:
                    current_time = current_time.replace(tzinfo=timezone.utc)
                if observed > current_time:
                    freshness_invalid = True
                    freshness_values = []
                    break
                age = (current_time - observed).total_seconds() / 86400
                freshness_values.append(max(0.0, min(100.0, 100 * (1 - age / max(1, freshness_limit_days)))))
            except (TypeError, ValueError):
                freshness_invalid = True
                freshness_values = []
                break
    freshness_score = round(sum(freshness_values) / len(freshness_values), 1) if freshness_values and len(freshness_values) == required else None
    freshness_status = ("UNVERIFIED" if freshness_invalid or freshness_score is None
                        else "STALE" if freshness_score == 0 else "VERIFIED")
    if freshness_status == "STALE":
        freshness_status = "STALE"
    if freshness_score is not None and score == 100 and freshness_score >= 80 and freshness_status == "VERIFIED":
        confidence_band = "HIGH"
    elif freshness_score is not None and score >= 60 and freshness_score >= 50 and freshness_status == "VERIFIED":
        confidence_band = "MEDIUM"
    unverified = [item for item in findings if item.get("status") == "UNVERIFIED"]
    blocked = [item for item in findings if item.get("status") == "BLOCKED"]
    role_impact = ROLE_IMPACT.get(role, "HIGH")
    if unverified and not blocked:
        risk = "UNVERIFIED"
    elif blocked:
        risk = "CRITICAL" if role_impact == "CRITICAL" and any(
            item.get("evidence_type") in {"security_review_completed", "rls_approved", "runtime_validated"}
            for item in blocked
        ) else "HIGH"
    else:
        risk = "LOW" if score == 100 else "MEDIUM"
    escalation = []
    if score < 100:
        escalation.append("Required evidence is incomplete or not independently verified.")
    if risk in {"HIGH", "CRITICAL", "UNVERIFIED"}:
        escalation.append(f"Risk rating {risk} exceeds or cannot be compared to the autonomous low-risk threshold.")
    if blocked:
        escalation.append("One or more required governance gates are blocked.")
    if unverified:
        escalation.append("One or more evidence sources are unavailable or unverified.")
    if freshness_score is None:
        escalation.append("Evidence freshness cannot be verified; source timestamps or approved freshness policy are missing.")
    elif freshness_status == "STALE":
        escalation.append("Evidence is stale under the explicitly supplied freshness policy.")
    return {
        "evidence_completeness_score": score,
        "evidence_verified_count": verified,
        "evidence_required_count": required,
        "evidence_freshness_score": freshness_score,
        "freshness_status": freshness_status,
        "freshness_basis": "All evidence records need source timestamps and an approved freshness limit; otherwise UNVERIFIED.",
        "risk_score": round(100 - score, 1),
        "risk_score_basis": "Percentage of required evidence not independently verified; not a probability of loss.",
        "decision_confidence_band": confidence_band,
        "confidence_basis": "Evidence completeness band only; not a calibrated probability or decision confidence claim.",
        "risk_rating": risk,
        "impact_rating": role_impact,
        "impact_score": IMPACT_SCORE[role_impact],
        "impact_score_basis": "Ordinal role-impact rubric: LOW=25, MEDIUM=50, HIGH=75, CRITICAL=100.",
        "escalation_criteria": escalation,
    }


def evaluate_decision_assurance(
    *,
    findings: list[dict[str, Any]],
    recommendation: str,
    reasoning: list[str],
    evidence_fingerprint: str,
    trace_fingerprint: str,
) -> dict[str, Any]:
    blocked = any(item.get("status") == "BLOCKED" for item in findings)
    unverified = any(item.get("status") == "UNVERIFIED" for item in findings)
    approved_like = recommendation.upper() in {"APPROVED", "AUTHORIZED", "CERTIFIED", "RELEASED"}
    decision_consistency = not approved_like and not (
        (blocked or unverified) and recommendation in {"RECOMMEND_REVIEW", "ELIGIBLE_FOR_AUTHORIZED_REVIEW"}
    )
    evidence_verification = bool(evidence_fingerprint) and all(
        item.get("evidence_type") and item.get("status")
        and (item.get("status") != "VERIFIED" or item.get("evidence") is not None)
        for item in findings
    )
    reasoning_validation = bool(reasoning) and all(isinstance(item, str) and item.strip() for item in reasoning)
    conflict_detection = not approved_like and not any(
        item.get("status") == "BLOCKED" and recommendation in {"RECOMMEND_REVIEW", "ELIGIBLE_FOR_AUTHORIZED_REVIEW"}
        for item in findings
    )
    checks = {
        "decision_consistency": decision_consistency,
        "evidence_verification": evidence_verification,
        "reasoning_validation": reasoning_validation,
        "conflict_detection": conflict_detection,
    }
    return {
        "assurance_score": round(100 * sum(checks.values()) / len(checks), 1),
        "checks": checks,
        "evidence_fingerprint": evidence_fingerprint,
        "trace_fingerprint": trace_fingerprint,
        "status": "ASSURED_FOR_SHADOW_REVIEW" if all(checks.values()) else "ASSURANCE_GAP",
        "authority": "NONE",
    }


def evaluate_autonomous_eligibility(
    *,
    action_type: str,
    evidence_complete: bool,
    risk_rating: str,
    impact_rating: str = "UNVERIFIED",
    evidence_completeness_score: float | None = None,
    governance_violations: list[str] | None,
    policy_exceptions: list[str] | None,
    governance_checks_verified: bool | None = None,
    exceptions_check_verified: bool | None = None,
    evidence_fingerprint: str | None = None,
    evaluation_timestamp: str | None = None,
    **action_checks: bool | None,
) -> dict[str, Any]:
    """Evaluate whether evidence satisfies a bounded policy; never performs the action."""
    reasons = []
    policy_domain = ACTION_POLICY_DOMAINS.get(action_type)
    policy = GOVERNANCE_POLICIES.get(policy_domain) if policy_domain else None
    threshold = policy.get("risk_threshold") if policy else None
    impact_threshold = policy.get("impact_threshold") if policy else None
    if threshold is None:
        reasons.append("Action type is not in the controlled eligibility policy.")
    minimum_completeness = float(policy.get("minimum_evidence_completeness", 100)) if policy else 100.0
    if evidence_complete is not True or evidence_completeness_score is None or evidence_completeness_score < minimum_completeness:
        reasons.append("Evidence is incomplete or not independently verified.")
    if risk_rating not in RISK_ORDER or threshold is None or RISK_ORDER.get(risk_rating, 99) > RISK_ORDER.get(threshold, -1):
        reasons.append("Risk is above the permitted threshold or unverified.")
    if impact_rating not in RISK_ORDER or impact_threshold is None or RISK_ORDER.get(impact_rating, 99) > RISK_ORDER.get(impact_threshold, -1):
        reasons.append("Impact exceeds the permitted threshold or is unverified.")
    if governance_checks_verified is not True or governance_violations is None:
        reasons.append("Violation/exception evidence is missing or unverified")
    elif governance_violations:
        reasons.append("Governance violations are present.")
    if exceptions_check_verified is not True or policy_exceptions is None:
        reasons.append("Violation/exception evidence is missing or unverified")
    elif policy_exceptions:
        reasons.append("Policy exceptions are present.")

    required_checks = ACTION_REQUIRED_CHECKS.get(action_type, ())
    for check in required_checks:
        if action_checks.get(check) is not True:
            reasons.append(f"Required action evidence is missing or failed: {check}.")
    eligible = not reasons
    blocked = risk_rating == "CRITICAL" or impact_rating == "CRITICAL"
    reason_codes = [f"POLICY:{policy_domain or 'UNKNOWN'}"]
    for reason in reasons:
        normalized = reason.lower()
        if "violation/exception evidence is missing" in normalized:
            code = "GOVERNANCE_EVIDENCE_UNVERIFIED"
        elif "evidence is incomplete" in normalized or "required action evidence" in normalized:
            code = "EVIDENCE_INCOMPLETE"
        elif "risk" in normalized:
            code = "RISK_THRESHOLD_EXCEEDED"
        elif "impact" in normalized:
            code = "IMPACT_THRESHOLD_EXCEEDED"
        elif "violation" in normalized:
            code = "GOVERNANCE_VIOLATION_PRESENT"
        elif "exception" in normalized:
            code = "POLICY_EXCEPTION_PRESENT"
        else:
            code = "POLICY_CHECK_FAILED"
        if code not in reason_codes:
            reason_codes.append(code)
    return {
        "policy_version": AUTONOMOUS_POLICY_VERSION,
        "domain_policy": policy_domain,
        "domain_policy_version": GOVERNANCE_POLICY_CATALOG_VERSION,
        "evidence_fingerprint": evidence_fingerprint,
        "evaluation_timestamp": evaluation_timestamp or datetime.now(timezone.utc).isoformat(),
        "reason_codes": reason_codes,
        "action_type": action_type,
        "status": "BLOCK" if blocked else "ELIGIBLE_FOR_AUTHORIZED_REVIEW" if eligible else "ESCALATE",
        "risk_threshold": threshold,
        "impact_threshold": impact_threshold,
        "minimum_evidence_completeness": minimum_completeness,
        "reasons": reasons,
        "escalation_state": "Critical" if blocked else "Warning" if reasons else "Info",
        "escalations": [{"state": "Critical" if risk_rating == "CRITICAL" else "Warning", "reason": reason}
                for reason in reasons],
        "authority": "NONE",
        "action_allowed": False,
        "persistence_enabled": False,
        "decision_persisted": False,
        "note": "Eligibility is a policy assessment only; existing authorized human approval and execution controls remain mandatory.",
    }


def build_shadow_review(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Evaluate role-specific evidence and return recommendations without authority."""
    fingerprint = _snapshot_fingerprint(snapshot)
    gates = _gate_index(snapshot)
    agents = []
    for profile in AGENT_ROLES:
        findings: list[dict[str, Any]] = []
        recommendations: list[str] = []
        required_gate_names = list(profile.get("gates", ()))
        missing_gate_names = [name for name in required_gate_names if name not in gates]
        for gate_name in required_gate_names:
            gate = gates.get(gate_name)
            if gate is None:
                findings.append({"evidence_type": gate_name, "status": "UNVERIFIED", "evidence": None,
                                 "blockers": ["Required gate evidence is absent."]})
                continue
            if gate.get("_conflict_detected"):
                findings.append({"evidence_type": gate_name, "status": "BLOCKED",
                    "evidence": gate.get("current_evidence"),
                    "blockers": ["Conflicting records exist for this gate; independent reconciliation is required."],
                    "conflicting_record_count": gate.get("_conflicting_records", 2)})
                continue
            state = gate.get("status", "BLOCKED")
            approved = gate.get("authorization_status") == "Approved" and state == "READY"
            findings.append({"evidence_type": gate_name, "status": "VERIFIED" if approved else state,
                             "evidence": gate.get("current_evidence"),
                             "blockers": gate.get("blockers", []) if not approved else []})
        for source_key in profile.get("sources", ()):
            state, message, evidence = _source_assessment(source_key, snapshot)
            findings.append({"evidence_type": source_key, "status": state, "evidence": evidence,
                             "blockers": [] if state == "RECOMMEND_REVIEW" else [message]})
            recommendations.append(message)
        if missing_gate_names:
            recommendation = "UNVERIFIED"
            recommendations.append("Required gate records are missing: " + ", ".join(missing_gate_names))
        elif any(item["status"] == "BLOCKED" for item in findings):
            recommendation = "BLOCKED"
            recommendations.append("One or more required gates are blocked; preserve the existing authorization boundary.")
        elif any(item["status"] == "UNVERIFIED" for item in findings):
            recommendation = "UNVERIFIED"
        else:
            recommendation = "RECOMMEND_REVIEW"
            recommendations.append("Evidence appears complete for this role's scope; a separately authorized decision is still required.")
        evaluated_at = snapshot.get("generated_at_utc")
        quality = evaluate_decision_quality(
            findings,
            role=profile["role"],
            evaluated_at=evaluated_at,
            freshness_limit_days=snapshot.get("approved_evidence_freshness_days"),
        )
        reason_codes = sorted({
            f"{item.get('status', 'UNKNOWN')}:{item.get('evidence_type', 'evidence')}"
            for item in findings if item.get("status") != "VERIFIED"
        })
        assurance = evaluate_decision_assurance(
            findings=findings,
            recommendation=recommendation,
            reasoning=recommendations,
            evidence_fingerprint=fingerprint,
            trace_fingerprint=fingerprint,
        )
        def escalation_type(evidence_type: str) -> str:
            key = evidence_type.lower()
            if any(term in key for term in ("security", "rls", "adapter")):
                return "Security Issue"
            if any(term in key for term in ("certification", "skill", "evaluation")):
                return "Certification Gap"
            if any(term in key for term in ("runtime", "assignment", "queue", "deliverable")):
                return "Runtime Risk"
            if any(term in key for term in ("provider", "model", "ownership", "migration")):
                return "Governance Violation"
            return "Missing Evidence"
        escalations = [{
            "state": "Critical" if quality["impact_rating"] == "CRITICAL" and item.get("status") == "BLOCKED"
                else "Warning" if item.get("status") == "BLOCKED" else "Info",
            "type": escalation_type(str(item.get("evidence_type", "evidence"))),
            "evidence_type": item.get("evidence_type"),
            "reason": "; ".join(item.get("blockers", [])) or "Evidence requires independent review.",
        } for item in findings if item.get("status") != "VERIFIED"]
        agents.append({
            "role": profile["role"],
            "scope": profile["scope"],
            "mode": "SHADOW_REVIEW",
            "recommendation": recommendation,
            "authority": "NONE",
            "confidence_score": None,
            "confidence_status": "Uncalibrated; no probability is asserted",
            "evidence_fingerprint": fingerprint,
            "decision_trace": {
                "evidence_fingerprint": fingerprint,
                "policy_version": POLICY_VERSION,
                "autonomous_policy_version": AUTONOMOUS_POLICY_VERSION,
                "governance_policy_catalog_version": GOVERNANCE_POLICY_CATALOG_VERSION,
                "evaluation_timestamp": evaluated_at or datetime.now(timezone.utc).isoformat(),
                "reason_codes": reason_codes,
            },
            "reason_codes": reason_codes,
            "findings": findings,
            "decision_assurance": assurance,
            "escalations": escalations,
            **quality,
            "reasoning": recommendations,
            "can_approve": False,
            "can_persist_decision": False,
            "can_execute_operations": False,
        })

    overall = "ESCALATE: EVIDENCE INCOMPLETE" if any(item["recommendation"] in {"BLOCKED", "UNVERIFIED"} for item in agents) else "RECOMMEND AUTHORIZED REVIEW"
    complete = all(agent["evidence_completeness_score"] == 100 for agent in agents)
    violations = snapshot.get("governance_violations")
    exceptions = snapshot.get("policy_exceptions")
    policy_evaluations = {}
    policy_check_groups = snapshot.get("autonomous_policy_checks", {})
    for action_type, domain in ACTION_POLICY_DOMAINS.items():
        if action_type == "routine_governance_review":
            continue
        checks = policy_check_groups.get(domain, {})
        required_checks = ACTION_REQUIRED_CHECKS.get(action_type, ())
        checks_complete = bool(required_checks) and all(checks.get(name) is True for name in required_checks)
        policy_evaluations[action_type] = evaluate_autonomous_eligibility(
            action_type=action_type,
            evidence_complete=checks_complete,
            evidence_completeness_score=100.0 if checks_complete else 0.0,
            risk_rating=snapshot.get("risk_rating_by_domain", {}).get(domain, "UNVERIFIED"),
            impact_rating=snapshot.get("impact_rating_by_domain", {}).get(domain, "UNVERIFIED"),
            governance_violations=violations,
            policy_exceptions=exceptions,
            governance_checks_verified=snapshot.get("governance_checks_verified"),
            exceptions_check_verified=snapshot.get("exceptions_check_verified"),
            evidence_fingerprint=fingerprint,
            evaluation_timestamp=snapshot.get("generated_at_utc"),
            **checks,
        )
    policy_evaluations["ownership_approval"] = evaluate_autonomous_eligibility(
        action_type="ownership_approval", evidence_complete=False, evidence_completeness_score=0,
        risk_rating="UNVERIFIED", impact_rating="HIGH", governance_violations=violations,
        policy_exceptions=exceptions, governance_checks_verified=snapshot.get("governance_checks_verified"),
        exceptions_check_verified=snapshot.get("exceptions_check_verified"),
        evidence_fingerprint=fingerprint, evaluation_timestamp=snapshot.get("generated_at_utc"),
        **policy_check_groups.get("ownership", {}))
    return {
        "framework": "AI Governance Agent Shadow Review",
        "policy_version": POLICY_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "SHADOW_RECOMMENDATION_ONLY",
        "overall_recommendation": overall,
        "evidence_fingerprint": fingerprint,
        "agents": agents,
        "governance_policies": get_governance_policies(),
        "autonomy_maturity": {
            "current_level": 2,
            "current_label": "Eligibility Assessment",
            "levels": [
                {"level": 0, "name": "Observation Only"},
                {"level": 1, "name": "Recommendation"},
                {"level": 2, "name": "Eligibility Assessment"},
                {"level": 3, "name": "Supervised Approval", "enabled": False},
                {"level": 4, "name": "Controlled Autonomy", "enabled": False},
                {"level": 5, "name": "Full Autonomous Operation", "enabled": False},
            ],
            "advancement_status": "BLOCKED: separate approved policy, assurance, calibration, audit, and rollback controls required",
        },
        "autonomy_dashboard": {
            "governance_status": overall,
            "readiness_status": "BLOCKED" if overall.startswith("ESCALATE") else "RECOMMEND_REVIEW",
            "risk_status": max((item["risk_rating"] for item in agents), key=lambda value: RISK_ORDER.get(value, -1), default="UNVERIFIED"),
            "evidence_status": "UNVERIFIED" if any(item["evidence_freshness_score"] is None for item in agents) else "VERIFIED",
            "autonomy_level": 2,
        },
        "autonomous_eligibility_policy": {
            "policy_version": AUTONOMOUS_POLICY_VERSION,
            "catalog_version": GOVERNANCE_POLICY_CATALOG_VERSION,
            "evaluations": policy_evaluations,
            "eligible_actions_are_non_executable": True,
            "human_authorized_controls_preserved": True,
        },
        "autonomy_maturity": {
            "current_level": AUTONOMY_LEVEL,
            "current_label": "Eligibility Assessment",
            "levels": ["Observation Only", "Recommendation", "Eligibility Assessment",
                       "Supervised Approval", "Controlled Autonomy", "Full Autonomous Operation"],
            "higher_levels_enabled": False,
        },
        "autonomy_dashboard": {
            "governance_status": overall,
            "readiness_status": "BLOCKED" if overall.startswith("ESCALATE") else "RECOMMEND_REVIEW",
            "risk_status": max((item["risk_rating"] for item in agents), key=lambda value: RISK_ORDER.get(value, -1), default="UNVERIFIED"),
            "evidence_status": "VERIFIED" if agents and all(item["evidence_freshness_score"] is not None for item in agents) else "UNVERIFIED",
            "autonomy_level": AUTONOMY_LEVEL,
            "mean_assurance_score": round(sum(item["decision_assurance"]["assurance_score"] for item in agents) / len(agents), 1) if agents else None,
        },
        "decision_persistence_enabled": False,
        "operational_actions_enabled": False,
        "approval_authority_granted": False,
        "note": "Rule-based evidence review only; no model inference, approval, certification, authorization, or operational action was performed.",
        "durable_decision_record": None,
    }


def build_assurance_platform(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build reproducibility and assurance analytics without storing any review."""
    first = build_shadow_review(snapshot)
    replay = build_shadow_review(snapshot)
    first_agents = first["agents"]
    replay_agents = replay["agents"]
    first_signature = [
        (agent["role"], agent["recommendation"], agent["reason_codes"], agent["risk_rating"],
         agent["impact_rating"], agent["evidence_fingerprint"])
        for agent in first_agents
    ]
    replay_signature = [
        (agent["role"], agent["recommendation"], agent["reason_codes"], agent["risk_rating"],
         agent["impact_rating"], agent["evidence_fingerprint"])
        for agent in replay_agents
    ]
    stable = first_signature == replay_signature
    consistency_score = 100.0 if stable else round(
        100 * sum(left == right for left, right in zip(first_signature, replay_signature))
        / max(len(first_signature), 1), 1
    )
    consistency_class = "Stable" if consistency_score == 100 else "Minor Drift" if consistency_score >= 80 else "Major Drift"

    def simulated_review(mutator: Any) -> dict[str, Any]:
        simulated_snapshot = deepcopy(snapshot)
        mutator(simulated_snapshot)
        return build_shadow_review(simulated_snapshot)

    def compare_recommendations(candidate: dict[str, Any]) -> dict[str, Any]:
        baseline = {agent["role"]: agent["recommendation"] for agent in first_agents}
        changed = [agent["role"] for agent in candidate["agents"]
                   if baseline.get(agent["role"]) != agent["recommendation"]]
        return {"changed_roles": changed, "recommendation_changes": len(changed),
                "baseline_recommendation": first["overall_recommendation"],
                "simulated_recommendation": candidate["overall_recommendation"]}

    gate_records = snapshot.get("production_gate_monitor", [])
    perturbation_mutators: dict[str, Any] = {
        "evidence_removed": lambda value: value.get("production_gate_monitor", []).pop(0)
            if value.get("production_gate_monitor") else None,
        "evidence_expired": lambda value: value.get("production_gate_monitor", [{}])[0].update(
            {"status": "EXPIRED", "display_status": "Expired"}) if value.get("production_gate_monitor") else None,
        "evidence_incomplete": lambda value: value.get("production_gate_monitor", [{}])[0].update(
            {"current_evidence": None, "evidence": None, "status": "UNVERIFIED"})
            if value.get("production_gate_monitor") else None,
        "evidence_conflicted": lambda value: value.get("production_gate_monitor", []).append(
            {**value["production_gate_monitor"][0], "status": "READY",
             "display_status": "Approved", "authorization_status": "Approved"})
            if value.get("production_gate_monitor") else None,
    }
    fragility_perturbations: dict[str, Any] = {}
    for perturbation, mutator in perturbation_mutators.items():
        simulated = simulated_review(mutator)
        comparison = compare_recommendations(simulated)
        fragility_perturbations[perturbation] = {
            **comparison, "simulation_only": True,
            "evidence_fingerprint": simulated["evidence_fingerprint"],
        }
    fragility_changes = sum(item["recommendation_changes"] > 0
                            for item in fragility_perturbations.values())
    fragility_score = round(100 * fragility_changes / len(fragility_perturbations), 1)

    policies = get_governance_policies()
    supplied_policy_evidence = snapshot.get("policy_evidence", {})
    coverage_policies = []
    for domain, policy in policies.items():
        domain_evidence = supplied_policy_evidence.get(domain, {})
        verified_evidence = {
            name for name, record in domain_evidence.items()
            if isinstance(record, dict) and record.get("status") == "VERIFIED"
            and record.get("source") and record.get("evidence_id")
            and record.get("policy_version") == policy["version"]
        } if isinstance(domain_evidence, dict) else set()
        required_evidence = list(policy["required_evidence"])
        available = [item for item in required_evidence if item in verified_evidence]
        missing = [item for item in required_evidence if item not in verified_evidence]
        coverage_policies.append({
            "domain": domain, "policy_id": policy["policy_id"], "version": policy["version"],
            "owner": policy["owner"], "required_evidence": required_evidence,
            "required_count": len(required_evidence), "available_evidence": available,
            "available_count": len(available), "missing_evidence": missing,
            "missing_count": len(missing),
            "coverage_percent": round(100 * len(available) / len(required_evidence), 1)
                if required_evidence else 100.0,
        })
    policy_coverage_percent = round(
        100 * sum(item["available_count"] for item in coverage_policies)
        / max(sum(item["required_count"] for item in coverage_policies), 1), 1)

    drift_mutators: dict[str, Any] = {
        "policy_version_change": lambda value: value.update(
            {"policy_version": f"{POLICY_VERSION}-simulated-change"}),
        "evidence_change": lambda value: value.get("production_gate_monitor", [{}])[0].update(
            {"status": "UNVERIFIED", "current_evidence": None, "evidence": None})
            if value.get("production_gate_monitor") else None,
        "risk_change": lambda value: value.update({"risk_monitor": {
            "status": "High risk (simulated)", "simulation_only": True}}),
    }
    drift_simulations: dict[str, Any] = {}
    for name, mutator in drift_mutators.items():
        simulated = simulated_review(mutator)
        comparison = compare_recommendations(simulated)
        changes = comparison["recommendation_changes"]
        fingerprint_changed = simulated["evidence_fingerprint"] != first["evidence_fingerprint"]
        classification = ("Major" if changes > 2 else "Minor" if changes or fingerprint_changed
                          else "Stable")
        policy_version_change = name == "policy_version_change"
        drift_simulations[name] = {
            **comparison, "classification": classification, "simulation_only": True,
            "evidence_fingerprint_changed": fingerprint_changed,
            "policy_version": {"baseline": GOVERNANCE_POLICY_CATALOG_VERSION,
                "simulated": f"{GOVERNANCE_POLICY_CATALOG_VERSION}-simulated"
                    if policy_version_change else GOVERNANCE_POLICY_CATALOG_VERSION},
            "historical_comparison": "Unavailable: no persisted governance history",
            "evidence_fingerprint": simulated["evidence_fingerprint"],
        }
    catalog_versions = {policy["version"] for policy in policies.values()}
    policy_version_simulation = drift_simulations["policy_version_change"]
    policy_consistency = 100.0 if len(catalog_versions) == 1 and not policy_version_simulation[
        "recommendation_changes"] else 0.0
    recommendation_stability = round(100 * (1 - fragility_changes / max(len(fragility_perturbations), 1)), 1)
    replay_consistency = consistency_score
    evidence_sensitivity = round(100 - fragility_score, 1)
    reliability_score = round((recommendation_stability + replay_consistency
                               + evidence_sensitivity + policy_consistency) / 4, 1)
    reliability_class = ("Excellent" if reliability_score >= 95 else "Good" if reliability_score >= 85
                         else "Fair" if reliability_score >= 70 else "Poor")
    decision_reliability = {
        "recommendation_stability": recommendation_stability,
        "replay_consistency": replay_consistency,
        "evidence_sensitivity": evidence_sensitivity,
        "policy_consistency": policy_consistency,
        "score": reliability_score, "classification": reliability_class,
        "basis": "Deterministic same-snapshot replay and explicitly labeled in-memory perturbation simulations; not historical performance.",
    }

    findings = [finding for agent in first_agents for finding in agent["findings"]]
    required = len(findings)
    verified = sum(finding.get("status") == "VERIFIED" for finding in findings)
    completeness = round(100 * verified / required, 1) if required else None
    freshness_values = [agent["evidence_freshness_score"] for agent in first_agents
                        if agent.get("evidence_freshness_score") is not None]
    freshness = round(sum(freshness_values) / len(freshness_values), 1) if freshness_values else None
    evidence_quality = {
        "completeness_percent": completeness if completeness is not None else "Unavailable",
        "freshness_percent": freshness if freshness is not None else "Unavailable",
        "coverage_percent": completeness if completeness is not None else "Unavailable",
        "validity_percent": completeness if completeness is not None else "Unavailable",
        "verified_findings": verified,
        "required_findings": required,
        "score_percent": completeness if completeness is not None else "Unavailable",
        "score_basis": "Verified findings divided by required findings; freshness is reported separately and never assumed.",
    }
    traceable = all(
        agent.get("decision_trace", {}).get("evidence_fingerprint") == first["evidence_fingerprint"]
        and agent.get("decision_trace", {}).get("policy_version")
        and agent.get("decision_trace", {}).get("evaluation_timestamp")
        and isinstance(agent.get("reason_codes"), list)
        for agent in first_agents
    )
    audit_events = snapshot.get("change_activity", {}).get("audit_timeline")
    auditable = False
    audit_status = "UNVERIFIED"
    if isinstance(audit_events, list) and audit_events:
        audit_status = "Observed events; completeness not verified"
    reversibility = snapshot.get("reversibility_verified") is True
    readiness_criteria = {
        "policy_coverage": {"ready": policy_coverage_percent == 100,
            "value": policy_coverage_percent, "required": 100},
        "evidence_quality": {"ready": completeness == 100 and freshness == 100, "value": evidence_quality["score_percent"], "required": 100},
        "recommendation_consistency": {"ready": consistency_score >= 95 and reliability_score >= 95,
            "value": reliability_score, "required": 95},
        "traceability": {"ready": traceable, "value": "VERIFIED" if traceable else "UNVERIFIED", "required": "VERIFIED"},
        "auditability": {"ready": auditable, "value": audit_status, "required": "Completeness independently verified"},
        "reversibility": {"ready": reversibility, "value": "VERIFIED" if reversibility else "UNVERIFIED", "required": "Approved reversible control evidence"},
        "no_open_governance_escalations": {"ready": first["overall_recommendation"] == "RECOMMEND AUTHORIZED REVIEW",
            "value": first["overall_recommendation"], "required": "No blocked or unverified role recommendation"},
    }
    passed = sum(bool(item["ready"]) for item in readiness_criteria.values())
    readiness_percent = round(100 * passed / len(readiness_criteria), 1)
    level3_status = "Ready" if passed == len(readiness_criteria) else "Partially Ready" if passed else "Not Ready"

    escalations = []
    for agent in first_agents:
        for item in agent.get("escalations", []):
            key = str(item.get("type", "")).lower()
            category = ("Security Issue" if "security" in key else
                        "Certification Gap" if "certification" in key else
                        "Runtime Risk" if "runtime" in key else
                        "Policy Gap" if "governance" in key else "Evidence Gap")
            escalations.append({"role": agent["role"], "category": category,
                "state": item.get("state", "Info"), "reason": item.get("reason"),
                "evidence_type": item.get("evidence_type")})
    for name, result in first["autonomous_eligibility_policy"]["evaluations"].items():
        for reason in result.get("reasons", []):
            category = "Risk Gap" if "risk" in reason.lower() or "impact" in reason.lower() else (
                "Policy Gap" if "policy" in reason.lower() or "governance" in reason.lower() else
                "Authorization Gap" if "approval" in reason.lower() or "authorized" in reason.lower() else
                "Evidence Gap")
            escalations.append({"role": name, "category": category,
                "state": result.get("escalation_state", "Warning"), "reason": reason,
                "evidence_type": name})
    escalation_counts = {state: sum(item["state"] == state for item in escalations)
                         for state in ("Info", "Warning", "Critical")}

    history_entry = {
        "evidence_fingerprint": first["evidence_fingerprint"],
        "policy_version": first["policy_version"],
        "recommendation": first["overall_recommendation"],
        "risk_ratings": {agent["role"]: agent["risk_rating"] for agent in first_agents},
        "impact_ratings": {agent["role"]: agent["impact_rating"] for agent in first_agents},
        "reason_codes": {agent["role"]: agent["reason_codes"] for agent in first_agents},
        "evaluation_timestamp": first["generated_at_utc"],
    }
    return {
        "framework": "Governance Assurance Platform",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "autonomy_level": 2,
        "authority": "NONE",
        "action_allowed": False,
        "persistence": False,
        "persistence_enabled": False,
        "decision_history": {"current_evaluation": history_entry,
            "historical_decisions": "Unavailable: persistence is disabled",
            "trend_analysis": "Unavailable: no historical governance decisions are stored",
            "current_vs_historical": "Unavailable"},
        "governance_memory": {"mode": "READ_ONLY_CURRENT_EVALUATION",
            "current_entry": history_entry,
            "historical_entries": "Unavailable: decision persistence is disabled",
            "historical_trend": "Unavailable: decisions are not persisted",
            "persistence": "DISABLED"},
        "decision_consistency": {"score": consistency_score, "classification": consistency_class,
            "replay_count": 2, "same_evidence_fingerprint": first["evidence_fingerprint"] == replay["evidence_fingerprint"],
            "recommendations_stable": stable, "basis": "Two in-memory evaluations of the identical snapshot; not longitudinal history."},
        "decision_reliability": decision_reliability,
        "evidence_quality": evidence_quality,
        "policy_coverage_analysis": {"coverage_percent": policy_coverage_percent,
            "policies": coverage_policies,
            "basis": "Only explicitly mapped VERIFIED evidence records with a source and evidence_id count; generic gates do not satisfy granular policy artifacts."},
        "evidence_fragility": {"score": fragility_score, "fragility_score": fragility_score,
            "classification": "HIGH" if fragility_score >= 50 else "MODERATE" if fragility_score > 0 else "LOW",
            "perturbations": fragility_perturbations,
            "simulation_only": True,
            "basis": "Deep-copied current snapshot perturbations; no source data or operational state is changed."},
        "governance_drift_lab": {"simulations": drift_simulations,
            "historical_drift": "Unavailable: persistence is disabled",
            "simulation_only": True,
            "basis": "Policy-version, evidence, and risk perturbations are deterministic simulations, not historical drift measurements."},
        "governance_drift": {
            "policy_drift": "Unavailable: no persisted prior policy version comparison",
            "reasoning_drift": "Stable on identical in-memory replay" if stable else "Detected on identical replay",
            "evidence_drift": "No drift on identical replay" if first["evidence_fingerprint"] == replay["evidence_fingerprint"] else "Detected",
            "risk_drift": "Stable on identical in-memory replay" if stable else "Detected on identical replay",
            "historical_drift_status": "Unavailable",
        },
        "escalation_analytics": {"items": escalations, "counts": escalation_counts,
            "classification": ["Evidence Gap", "Policy Gap", "Risk Gap", "Authorization Gap"]},
        "simulation_replay": {"simulations": [{"evidence_fingerprint": first["evidence_fingerprint"],
            "expected_recommendation": first["overall_recommendation"],
            "current_recommendation": replay["overall_recommendation"],
            "differences": [], "difference_count": 0, "simulation_only": True}],
            "difference_count": 0,
            "approvals_created": False, "actions_executed": False},
        "level3_readiness": {"status": level3_status, "readiness_percent": readiness_percent,
            "passed_criteria": passed, "total_criteria": len(readiness_criteria),
            "criteria": readiness_criteria,
            "blocking_criteria": [name for name, item in readiness_criteria.items() if not item["ready"]],
            "authority_granted": False},
        "governance_kpi_dashboard": {"policy_coverage_percent": policy_coverage_percent,
            "evidence_coverage_percent": evidence_quality["coverage_percent"],
            "consistency_score": consistency_score,
            "drift_score": 0.0 if stable else round(100 - consistency_score, 1),
            "escalation_rate": "Unavailable: no persisted decision denominator",
            "escalation_counts": escalation_counts},
        "decision_assurance": {"mean_score": round(sum(agent["decision_assurance"]["assurance_score"] for agent in first_agents) / len(first_agents), 1) if first_agents else None,
            "auditability": audit_status, "traceability": "VERIFIED" if traceable else "UNVERIFIED",
            "reversibility": "VERIFIED" if reversibility else "UNVERIFIED"},
        "role_reviews": first_agents,
        "controls": {"approval_execution": False, "certification_execution": False,
            "release_execution": False, "migration_execution": False, "ownership_execution": False,
            "runtime_execution": False, "persistence": False},
    }
