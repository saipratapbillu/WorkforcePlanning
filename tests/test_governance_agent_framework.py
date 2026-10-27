import unittest
from unittest.mock import Mock, patch

from app.services import governance_agent_framework
from app.api.operations import ai_governance_assurance_platform, ai_governance_shadow_review


class GovernanceAgentFrameworkTests(unittest.TestCase):
    def test_shadow_review_registers_all_roles_without_authority(self):
        review = governance_agent_framework.build_shadow_review(self.snapshot())

        self.assertEqual(len(review["agents"]), 14)
        self.assertEqual(review["mode"], "SHADOW_RECOMMENDATION_ONLY")
        self.assertFalse(review["decision_persistence_enabled"])
        self.assertFalse(review["operational_actions_enabled"])
        self.assertTrue(all(agent["authority"] == "NONE" for agent in review["agents"]))
        self.assertTrue(all(agent["recommendation"] != "APPROVED" for agent in review["agents"]))

    def test_shadow_recommendations_are_bound_to_evidence_fingerprint(self):
        snapshot = self.snapshot()

        first = governance_agent_framework.build_shadow_review(snapshot)
        second = governance_agent_framework.build_shadow_review(snapshot)

        self.assertEqual(first["evidence_fingerprint"], second["evidence_fingerprint"])
        self.assertEqual(first["agents"], second["agents"])
        self.assertNotIn("decision_id", first)
        self.assertIsNone(first["durable_decision_record"])

    def test_missing_evidence_stays_unverified_and_never_approves(self):
        snapshot = self.snapshot()
        snapshot["production_gate_monitor"] = []
        snapshot["evidence_collection_center"] = {"missing_evidence_report": {"items": ["All evidence"], "count": 1}}

        review = governance_agent_framework.build_shadow_review(snapshot)

        self.assertEqual(review["overall_recommendation"], "ESCALATE: EVIDENCE INCOMPLETE")
        self.assertTrue(all(agent["recommendation"] != "APPROVED" for agent in review["agents"]))
        self.assertTrue(all(agent["authority"] == "NONE" for agent in review["agents"]))

    def test_shadow_review_route_does_not_write_database(self):
        db = Mock()
        snapshot = self.snapshot()

        with patch("app.api.operations.phase17_operational_tracking", return_value=snapshot):
            result = ai_governance_shadow_review(db)

        self.assertEqual(len(result["agents"]), 14)
        self.assertEqual(result["mode"], "SHADOW_RECOMMENDATION_ONLY")
        db.execute.assert_not_called()
        db.commit.assert_not_called()

    def test_quality_dimensions_and_escalation_fields_are_present_for_every_role(self):
        review = governance_agent_framework.build_shadow_review(self.snapshot())

        self.assertEqual(len(review["agents"]), 14)
        for agent in review["agents"]:
            self.assertIn("evidence_completeness_score", agent)
            self.assertIn("risk_score", agent)
            self.assertIn("impact_score", agent)
            self.assertIn(agent["decision_confidence_band"], {"LOW", "MEDIUM", "HIGH"})
            self.assertIn(agent["risk_rating"], {"CRITICAL", "HIGH", "MEDIUM", "LOW", "UNVERIFIED"})
            self.assertIn(agent["impact_rating"], {"CRITICAL", "HIGH", "MEDIUM", "LOW"})
            self.assertIsInstance(agent["escalation_criteria"], list)
            self.assertIn("evidence_freshness_score", agent)
            self.assertIn("decision_trace", agent)
            assurance = agent["decision_assurance"]
            self.assertEqual(set(assurance["checks"]), {
                "decision_consistency", "evidence_verification", "reasoning_validation", "conflict_detection"
            })
            self.assertGreaterEqual(assurance["assurance_score"], 0)
            self.assertLessEqual(assurance["assurance_score"], 100)
            self.assertEqual(agent["decision_trace"]["evidence_fingerprint"], review["evidence_fingerprint"])
            self.assertIn("policy_version", agent["decision_trace"])
            self.assertIn("evaluation_timestamp", agent["decision_trace"])
            self.assertIsInstance(agent["reason_codes"], list)
        self.assertEqual(review["autonomy_maturity"]["current_level"], 2)
        self.assertFalse(review["autonomy_maturity"]["higher_levels_enabled"])
        evaluations = review["autonomous_eligibility_policy"]["evaluations"]
        self.assertEqual(set(evaluations), {
            "migration_approval", "ownership_approval", "provider_approval", "model_approval",
            "certification", "workforce_approval", "adapter_approval", "runtime_approval",
            "security_review", "low_risk_release",
        })
        self.assertTrue(all(result["status"] == "ESCALATE" and not result["action_allowed"]
                            and result["authority"] == "NONE" and not result["decision_persisted"]
                            and result["evidence_fingerprint"] == review["evidence_fingerprint"]
                            and result["evaluation_timestamp"] for result in evaluations.values()))
        self.assertEqual(review["autonomy_dashboard"]["autonomy_level"], 2)

    def test_central_policy_catalog_covers_eight_governance_domains(self):
        policies = governance_agent_framework.get_governance_policies()

        self.assertEqual(set(policies), {"migration", "ownership", "provider", "model",
            "certification", "workforce", "adapter", "runtime", "security", "release"})
        for domain, policy in policies.items():
            self.assertTrue(policy["policy_id"])
            self.assertTrue(policy["version"])
            self.assertTrue(policy["owner"])
            self.assertEqual(policy["domain"], domain)
            self.assertTrue(policy["required_evidence"])
            self.assertIn("minimum_evidence_completeness", policy)
            self.assertIn(policy["risk_threshold"], {"LOW", "MEDIUM", "HIGH", "CRITICAL"})
            self.assertIn(policy["impact_threshold"], {"LOW", "MEDIUM", "HIGH", "CRITICAL"})
            self.assertTrue(policy["escalation_rules"])

    def test_evidence_freshness_is_unverified_without_timestamps(self):
        findings = [{"status": "VERIFIED", "evidence": {"record_id": "abc"}}]
        quality = governance_agent_framework.evaluate_decision_quality(
            findings, role="AI Data Steward", evaluated_at="2026-10-27T00:00:00+00:00")

        self.assertEqual(quality["evidence_completeness_score"], 100)
        self.assertIsNone(quality["evidence_freshness_score"])
        self.assertEqual(quality["freshness_status"], "UNVERIFIED")
        self.assertEqual(quality["decision_confidence_band"], "LOW")

    def test_evidence_freshness_uses_timestamps_only_with_explicit_policy_limit(self):
        findings = [{"status": "VERIFIED", "evidence": {"created_at_utc": "2026-10-26T00:00:00+00:00"}}]
        quality = governance_agent_framework.evaluate_decision_quality(
            findings, role="AI Data Steward", evaluated_at="2026-10-27T00:00:00+00:00",
            freshness_limit_days=30)

        self.assertEqual(quality["evidence_freshness_score"], 96.7)
        self.assertEqual(quality["freshness_status"], "VERIFIED")
        self.assertEqual(quality["decision_confidence_band"], "HIGH")

    def test_future_evidence_timestamp_is_unverified(self):
        quality = governance_agent_framework.evaluate_decision_quality(
            [{"status": "VERIFIED", "evidence": {"created_at_utc": "2026-10-28T00:00:00+00:00"}}],
            role="AI Data Steward", evaluated_at="2026-10-27T00:00:00+00:00", freshness_limit_days=30)

        self.assertEqual(quality["freshness_status"], "UNVERIFIED")
        self.assertIsNone(quality["evidence_freshness_score"])
        self.assertEqual(quality["decision_confidence_band"], "LOW")

    def test_policy_escalates_when_violation_or_exception_evidence_is_missing(self):
        result = governance_agent_framework.evaluate_autonomous_eligibility(
            action_type="low_risk_release",
            evidence_complete=True,
            evidence_completeness_score=100,
            risk_rating="LOW",
            impact_rating="LOW",
            governance_violations=[],
            policy_exceptions=[],
            rollback_available=True,
            tests_passed=True,
            security_passed=True,
            audit_trail_complete=True,
            change_approval=True,
            release_approval=True,
        )

        self.assertEqual(result["status"], "ESCALATE")
        self.assertFalse(result["action_allowed"])
        self.assertIn("Violation/exception evidence is missing or unverified", result["reasons"])
        self.assertIn("GOVERNANCE_EVIDENCE_UNVERIFIED", result["reason_codes"])
        self.assertIn("POLICY:release", result["reason_codes"])

    def test_low_risk_release_can_only_be_eligible_for_authorized_review(self):
        result = governance_agent_framework.evaluate_autonomous_eligibility(
            action_type="low_risk_release",
            evidence_complete=True,
            evidence_completeness_score=100,
            risk_rating="LOW",
            impact_rating="LOW",
            governance_violations=[],
            policy_exceptions=[],
            governance_checks_verified=True,
            exceptions_check_verified=True,
            rollback_available=True,
            tests_passed=True,
            security_passed=True,
            audit_trail_complete=True,
            change_approval=True,
            release_approval=True,
        )

        self.assertEqual(result["status"], "ELIGIBLE_FOR_AUTHORIZED_REVIEW")
        self.assertEqual(result["authority"], "NONE")
        self.assertFalse(result["action_allowed"])

    def test_certification_and_model_policy_require_all_verified_conditions(self):
        cert = governance_agent_framework.evaluate_autonomous_eligibility(
            action_type="certification", evidence_complete=True, evidence_completeness_score=100,
            risk_rating="LOW", impact_rating="LOW",
            governance_violations=[], policy_exceptions=[], governance_checks_verified=True,
            exceptions_check_verified=True, skill_evidence_complete=True,
            evaluations_passed=True, governance_requirements_met=True, independent_review=True,
        )
        model = governance_agent_framework.evaluate_autonomous_eligibility(
            action_type="model_approval", evidence_complete=True, evidence_completeness_score=100,
            risk_rating="LOW", impact_rating="LOW",
            governance_violations=[], policy_exceptions=[], governance_checks_verified=True,
            exceptions_check_verified=True, provider_approved=True,
            policies_approved=True, evaluations_passed=True, risk_assessment_complete=True,
            security_assessment_passed=True, independent_review=True,
        )

        self.assertEqual(cert["status"], "ELIGIBLE_FOR_AUTHORIZED_REVIEW")
        self.assertEqual(model["status"], "ELIGIBLE_FOR_AUTHORIZED_REVIEW")
        self.assertFalse(cert["action_allowed"])
        self.assertFalse(model["action_allowed"])

    def test_high_risk_or_missing_release_control_forces_escalation(self):
        high_risk = governance_agent_framework.evaluate_autonomous_eligibility(
            action_type="low_risk_release", evidence_complete=True, evidence_completeness_score=100,
            risk_rating="HIGH", impact_rating="LOW",
            governance_violations=[], policy_exceptions=[], governance_checks_verified=True,
            exceptions_check_verified=True, rollback_available=True,
            tests_passed=True, security_passed=True, audit_trail_complete=True,
            change_approval=True, release_approval=True,
        )
        missing_control = governance_agent_framework.evaluate_autonomous_eligibility(
            action_type="low_risk_release", evidence_complete=True, evidence_completeness_score=100,
            risk_rating="LOW", impact_rating="LOW",
            governance_violations=[], policy_exceptions=[], governance_checks_verified=True,
            exceptions_check_verified=True, rollback_available=True,
            tests_passed=True, security_passed=False, audit_trail_complete=True,
            change_approval=True, release_approval=True,
        )

        self.assertEqual(high_risk["status"], "ESCALATE")
        self.assertEqual(missing_control["status"], "ESCALATE")
        self.assertFalse(high_risk["action_allowed"])
        self.assertFalse(missing_control["action_allowed"])

    def test_critical_risk_blocks_eligibility_and_medium_high_escalate(self):
        def evaluate(risk):
            return governance_agent_framework.evaluate_autonomous_eligibility(
                action_type="low_risk_release", evidence_complete=True, evidence_completeness_score=100,
                risk_rating=risk, impact_rating="LOW", governance_violations=[], policy_exceptions=[],
                governance_checks_verified=True, exceptions_check_verified=True,
                rollback_available=True, tests_passed=True, security_passed=True,
                audit_trail_complete=True, change_approval=True, release_approval=True)

        self.assertEqual(evaluate("MEDIUM")["status"], "ESCALATE")
        self.assertEqual(evaluate("HIGH")["status"], "ESCALATE")
        critical = evaluate("CRITICAL")
        self.assertEqual(critical["status"], "BLOCK")
        self.assertFalse(critical["action_allowed"])

    def test_assurance_detects_recommendation_conflicts_and_missing_reasoning(self):
        result = governance_agent_framework.evaluate_decision_assurance(
            findings=[{"evidence_type": "security_review", "status": "BLOCKED", "evidence": None}],
            recommendation="RECOMMEND_REVIEW", reasoning=[], evidence_fingerprint="abc", trace_fingerprint="abc")

        self.assertFalse(result["checks"]["decision_consistency"])
        self.assertFalse(result["checks"]["reasoning_validation"])
        self.assertEqual(result["status"], "ASSURANCE_GAP")

    def test_assurance_platform_replays_deterministically_without_persisting_history(self):
        report = governance_agent_framework.build_assurance_platform(self.snapshot())

        self.assertEqual(report["decision_consistency"]["classification"], "Stable")
        self.assertEqual(report["decision_consistency"]["score"], 100)
        self.assertEqual(report["simulation_replay"]["difference_count"], 0)
        self.assertEqual(report["governance_memory"]["persistence"], "DISABLED")
        self.assertEqual(report["governance_memory"]["historical_trend"], "Unavailable: decisions are not persisted")
        self.assertFalse(report["authority"] != "NONE")
        self.assertFalse(report["action_allowed"])
        self.assertFalse(report["persistence_enabled"])

    def test_assurance_platform_endpoint_does_not_write(self):
        db = Mock()
        snapshot = self.snapshot()
        with patch("app.api.operations.phase17_operational_tracking", return_value=snapshot):
            report = ai_governance_assurance_platform(db)

        self.assertEqual(report["autonomy_level"], 2)
        self.assertEqual(report["authority"], "NONE")
        self.assertFalse(report["persistence_enabled"])
        self.assertFalse(report["action_allowed"])
        db.execute.assert_not_called()
        db.commit.assert_not_called()

    def test_assurance_endpoint_uses_phase17_snapshot_without_writes(self):
        from app.api.operations import ai_governance_assurance_platform

        db = Mock()
        with patch("app.api.operations.phase17_operational_tracking", return_value=self.snapshot()):
            result = ai_governance_assurance_platform(db)

        self.assertEqual(result["autonomy_level"], 2)
        self.assertFalse(result["persistence_enabled"])
        self.assertFalse(result["action_allowed"])
        db.execute.assert_not_called()
        db.commit.assert_not_called()

    def test_level3_assessment_fails_closed_when_assurance_prerequisites_are_missing(self):
        report = governance_agent_framework.build_assurance_platform(self.snapshot())

        self.assertNotEqual(report["level3_readiness"]["status"], "Ready")
        self.assertLess(report["level3_readiness"]["readiness_percent"], 100)
        self.assertTrue(report["level3_readiness"]["blocking_criteria"])

    def test_assurance_platform_reports_fragility_drift_and_policy_coverage(self):
        report = governance_agent_framework.build_assurance_platform(self.snapshot())

        self.assertIn("evidence_fragility", report)
        self.assertEqual(set(report["evidence_fragility"]["perturbations"]), {
            "evidence_removed", "evidence_expired", "evidence_incomplete", "evidence_conflicted"})
        self.assertIn("governance_drift_lab", report)
        self.assertEqual(set(report["governance_drift_lab"]["simulations"]), {
            "policy_version_change", "evidence_change", "risk_change"})
        self.assertEqual(len(report["policy_coverage_analysis"]["policies"]), 10)
        self.assertIn(report["decision_reliability"]["classification"], {"Excellent", "Good", "Fair", "Poor"})
        self.assertIn(report["level3_readiness"]["status"], {"Ready", "Partially Ready", "Not Ready"})
        self.assertFalse(report["persistence_enabled"])

    def test_assurance_metrics_cover_sensitivity_drift_coverage_and_replay_only(self):
        snapshot = self.snapshot()
        fingerprint_before = governance_agent_framework._snapshot_fingerprint(snapshot)
        report = governance_agent_framework.build_assurance_platform(snapshot)

        reliability = report["decision_reliability"]
        self.assertIn("recommendation_stability", reliability)
        self.assertIn("replay_consistency", reliability)
        self.assertIn("evidence_sensitivity", reliability)
        self.assertIn("policy_consistency", reliability)
        self.assertIn("fragility_score", report["evidence_fragility"])
        self.assertEqual(set(report["evidence_fragility"]["perturbations"]), {
            "evidence_removed", "evidence_expired", "evidence_incomplete", "evidence_conflicted"})
        self.assertEqual(set(report["governance_drift_lab"]["simulations"]), {
            "policy_version_change", "evidence_change", "risk_change"})
        self.assertEqual(report["decision_history"]["historical_decisions"],
                         "Unavailable: persistence is disabled")
        self.assertEqual(report["decision_reliability"]["replay_consistency"], 100.0)
        self.assertEqual(report["policy_coverage_analysis"]["coverage_percent"], 0.0)
        self.assertTrue(all(item["simulation_only"] for item in report["evidence_fragility"]["perturbations"].values()))
        self.assertTrue(all(item["simulation_only"] for item in report["governance_drift_lab"]["simulations"].values()))
        self.assertEqual(governance_agent_framework._snapshot_fingerprint(snapshot), fingerprint_before)
        self.assertFalse(report["persistence_enabled"])

    def test_policy_coverage_counts_only_explicit_verified_artifact_mapping(self):
        snapshot = self.snapshot()
        snapshot["policy_evidence"] = {"migration": {
            "migration script hash": {"status": "VERIFIED", "source": "artifact-store",
                                       "evidence_id": "sha256:example",
                                       "policy_version": governance_agent_framework.GOVERNANCE_POLICY_CATALOG_VERSION},
            "dependency validation": {"status": "VERIFIED", "source": "artifact-store",
                                      "evidence_id": "sha256:missing-policy-version"},
        }}

        report = governance_agent_framework.build_assurance_platform(snapshot)

        migration = next(item for item in report["policy_coverage_analysis"]["policies"]
                         if item["domain"] == "migration")
        self.assertEqual(migration["available_evidence"], ["migration script hash"])
        self.assertEqual(migration["available_count"], 1)
        self.assertEqual(migration["missing_count"], migration["required_count"] - 1)
        version_change = report["governance_drift_lab"]["simulations"]["policy_version_change"]
        self.assertNotEqual(version_change["policy_version"]["baseline"],
                    version_change["policy_version"]["simulated"])

    def test_conflicting_duplicate_gate_records_are_blocked_not_last_write_wins(self):
        snapshot = self.snapshot()
        snapshot["production_gate_monitor"].append({
            "gate": "migration_applied", "display_status": "Approved", "status": "READY",
            "authorization_status": "Approved", "current_evidence": {"migration_applied": True},
            "blockers": [],
        })

        review = governance_agent_framework.build_shadow_review(snapshot)

        affected = [finding for agent in review["agents"] for finding in agent["findings"]
                    if finding["evidence_type"] == "migration_applied"]
        self.assertTrue(affected)
        self.assertTrue(all(finding["status"] == "BLOCKED" for finding in affected))
        self.assertTrue(all("Conflicting records" in finding["blockers"][0] for finding in affected))

    def test_escalations_classify_evidence_policy_risk_and_authorization_gaps(self):
        report = governance_agent_framework.build_assurance_platform(self.snapshot())
        categories = {item["category"] for item in report["escalation_analytics"]["items"]}

        self.assertTrue(categories.intersection({"Evidence Gap", "Policy Gap", "Risk Gap", "Authorization Gap"}))
        self.assertTrue(all(item["state"] in {"Info", "Warning", "Critical"}
                            for item in report["escalation_analytics"]["items"]))

    @staticmethod
    def snapshot():
        return {
            "generated_at_utc": "2026-10-26T00:00:00+00:00",
            "pilot_authorization_status": "Not Authorized",
            "production_authorization_status": "Not Authorized",
            "evidence_coverage_percent": 0,
            "evidence_collection_center": {"missing_evidence_report": {
                "items": ["Approval Evidence", "Runtime Validation Evidence"], "count": 2}},
            "risk_monitor": {"status": "Unavailable: risks not assessed"},
            "compliance_monitor": {"status": "Not assessed"},
            "production_gate_monitor": [
                {"gate": "ownership_approved", "display_status": "Locked", "status": "BLOCKED",
                 "evidence": None, "blockers": ["Owner approval missing"]},
                {"gate": "migration_applied", "display_status": "Locked", "status": "BLOCKED",
                 "evidence": {"migration_applied": False}, "blockers": ["Migration not applied"]},
                {"gate": "providers_approved", "display_status": "Locked", "status": "BLOCKED",
                 "evidence": None, "blockers": ["Provider approval missing"]},
                {"gate": "models_approved", "display_status": "Locked", "status": "BLOCKED",
                 "evidence": None, "blockers": ["Model approval missing"]},
                {"gate": "certifications_completed", "display_status": "Locked", "status": "BLOCKED",
                 "evidence": None, "blockers": ["Certification missing"]},
                {"gate": "adapters_configured", "display_status": "Locked", "status": "BLOCKED",
                 "evidence": None, "blockers": ["Adapter missing"]},
                {"gate": "runtime_validated", "display_status": "Locked", "status": "BLOCKED",
                 "evidence": None, "blockers": ["Runtime missing"]},
                {"gate": "security_review_completed", "display_status": "Locked", "status": "BLOCKED",
                 "evidence": None, "blockers": ["Security review missing"]},
                {"gate": "rls_approved", "display_status": "Locked", "status": "BLOCKED",
                 "evidence": {"enabled": False}, "blockers": ["RLS approval missing"]},
            ],
            "change_activity": {"audit_timeline": [{"Action": "ApprovalCreated", "Outcome": "Success"}]},
        }


if __name__ == "__main__":
    unittest.main()