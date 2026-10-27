import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError
from app.api import operations

from app.api.operations import (
    AdapterConfiguration,
    OwnershipReviewDecision,
    activation_runbook,
    certification_campaign,
    export_ownership_rollback_package,
    export_ownership_approval_package,
    export_rls_readiness_package,
    model_onboarding_package,
    record_ownership_review,
    validate_migration_24_script,
    validate_migration_24,
    phase11_deployment_package,
    _migration_24_source,
    _phase10_launch_snapshot,
    adapter_deployment_package,
    ownership_remediation_report,
    record_adapter_health_check,
)


class OwnershipRemediationReportTests(unittest.TestCase):
    def test_unified_governance_package_keeps_operational_and_authorization_gates_blocked(self):
        phase17 = {
            "read_only": True, "evidence_coverage_percent": 0,
            "pilot_authorization_status": "Not Authorized",
            "production_authorization_status": "Not Authorized",
            "execution_tracking_center": {"activities": []},
            "evidence_collection_center": {"missing_evidence_report": {"count": 7}},
            "authorization_monitor": {"pilot": {"status": "Not Authorized"},
                "production": {"status": "Not Authorized"}},
            "operational_kpis": {"runtime_success_percent": "Unavailable"},
            "change_activity": {"audit_timeline": [], "change_timeline": []},
            "risk_monitor": {"status": "Unavailable: risks not assessed"},
            "compliance_monitor": {"status": "Not assessed"},
            "executive_operations_dashboard": {name: {"operational_status": "NO-GO"}
                for name in ("CEO", "COO", "CIO", "Governance Board")},
            "production_gate_monitor": [{"gate": f"gate_{i}", "display_status": "Locked", "blockers": ["Missing evidence"]}
                for i in range(9)],
            "actions_performed": [], "controls_changed": False,
        }
        builder = getattr(operations, "_build_unified_governance_package", None)
        self.assertIsNotNone(builder, "Unified governance package builder is missing")
        result = builder(phase17)

        self.assertEqual(result["package_type"], "Unified Governance Command Center")
        self.assertEqual(len(result["capabilities"]), 30)
        self.assertEqual(result["pilot_authorization"], "Not Authorized")
        self.assertEqual(result["production_authorization"], "Not Authorized")
        self.assertEqual(result["operational_readiness_percent"], 0)
        self.assertEqual(result["pilot_authorization_readiness_percent"], 0)
        self.assertEqual(result["production_authorization_readiness_percent"], 0)
        self.assertTrue(all(item["status"] in {"BLOCKED", "UNVERIFIED"} for item in result["capabilities"]))
        for item in result["capabilities"]:
            self.assertTrue((Path.cwd() / item["test_reference"]).is_file())
            self.assertTrue((Path.cwd() / item["documentation_reference"]).is_file())
            self.assertIn("audit_coverage_status", item)
            self.assertIn("governance_control_reference", item)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["approvals_created"])

    def test_uat_readiness_package_has_twenty_traced_scenarios_but_none_claimed_passed(self):
        phase17 = {
            "evidence_coverage_percent": 0,
            "pilot_authorization_status": "Not Authorized",
            "production_authorization_status": "Not Authorized",
            "production_gate_monitor": [{"gate": f"gate_{i}", "display_status": "Locked"} for i in range(9)],
        }
        builder = getattr(operations, "_build_uat_readiness_package", None)
        self.assertIsNotNone(builder, "UAT readiness package builder is missing")
        result = builder(phase17)

        self.assertEqual(result["package_type"], "UAT Readiness and Traceability Package")
        self.assertEqual(len(result["scenarios"]), 21)
        self.assertEqual(len(result["test_data_matrix"]), 21)
        self.assertTrue(all(row["execution_status"] == "Not Run" for row in result["scenarios"]))
        self.assertTrue(all(row["acceptance_status"] == "Not Accepted" for row in result["scenarios"]))
        self.assertTrue(all(row["evidence_status"] in {"Unavailable", "Source Mapped"} for row in result["scenarios"]))
        for row in result["scenarios"]:
            self.assertTrue((Path.cwd() / row["test_reference"]).is_file())
            self.assertTrue((Path.cwd() / row["documentation_reference"]).is_file())
            self.assertEqual(row["audit_reference"], "/operations/phase17-operational-tracking")
            self.assertEqual(row["governance_reference"], "/operations/phase16-authorization-readiness")
        self.assertEqual(result["uat_readiness_status"], "NOT READY: authorization/evidence gates blocked")
        self.assertFalse(result["fake_test_data_created"])
        self.assertFalse(result["uat_executed"])

    def test_phase17_monitor_builder_is_read_only_and_reports_unknowns_unavailable(self):
        phase16 = {
            "pilot_authorization": "Not Authorized", "production_authorization": "Not Authorized",
            "pilot_go_no_go": "NO-GO", "production_go_no_go": "NO-GO", "evidence_readiness_score": 0,
            "missing_evidence": ["Approval Evidence", "Runtime Validation Evidence"],
            "production_gates": [{"gate": f"gate_{index}", "label": f"Gate {index}",
                "status": "BLOCKED", "authorization_status": "NotRecorded",
                "current_evidence": None, "blockers": ["No verified evidence"]}
                for index in range(1, 10)],
            "executive_decision_board": {name: {"current_status": "BLOCKED", "recommendation": "NO-GO"}
                for name in ("CEO", "COO", "CIO", "Governance Board")},
            "business_continuity_disaster_recovery": {"recovery_tests_executed": False},
        }
        phase15 = {
            "evidence_checklist": [{"evidence_type": "Approval Evidence", "status": "Unavailable",
                "operationally_complete": False, "evidence": None}],
            "missing_evidence": ["Approval Evidence"], "evidence_readiness_score": 0,
            "approval_hub": {"workflow_definitions": [{"workflow": "Pilot Authorization",
                "workflow_status": "Defined", "decision_status": "NotRecorded", "approval_created": False}]},
            "risk_register": {"assessment_status": "Template: not assessed", "risks": []},
            "risk_dashboard": {"status": "Unavailable: risks not assessed", "heatmap_data": []},
            "compliance_readiness": {"status": "Not assessed", "checklist": [], "exception_register": {"status": "Unavailable"}},
            "success_measurement": {"metrics": {"approval_completion_percent": {"value": "Unavailable"}}},
            "executive_packages": {name: {"recommendation": "NO-GO"} for name in ("CEO", "COO", "CIO")},
            "actions_performed": [],
        }
        audit_events = [{"Action": "OwnershipRemediationReviewRecorded", "Outcome": "NeedsReview",
                         "CreatedAtUtc": "2026-10-26T10:00:00"}]

        builder = getattr(operations, "_build_phase17_operations_monitor", None)
        self.assertIsNotNone(builder, "Phase 17 operations monitor builder is missing")
        result = builder(phase15, phase16, audit_events)

        self.assertEqual(result["package_type"], "Phase 17 Operational Execution Tracking")
        self.assertEqual(result["pilot_authorization_status"], "Not Authorized")
        self.assertEqual(result["production_authorization_status"], "Not Authorized")
        self.assertEqual(result["evidence_coverage_percent"], 0)
        self.assertEqual(result["operational_kpis"]["approval_completion_percent"], "Unavailable")
        self.assertEqual(len(result["production_gate_monitor"]), 9)
        self.assertTrue(all(gate["display_status"] == "Locked" for gate in result["production_gate_monitor"]))
        self.assertEqual(result["change_activity"]["audit_timeline"], audit_events)
        self.assertEqual(result["risk_monitor"]["status"], "Unavailable: risks not assessed")
        self.assertTrue(result["read_only"])
        self.assertFalse(result["tracking_records_created"])
        self.assertFalse(result["approvals_created"])

    def test_phase17_route_only_reads_existing_audit_history(self):
        from app.api.operations import phase17_operational_tracking

        event_result = Mock()
        event_result.mappings.return_value.all.return_value = []
        db = Mock()
        db.execute.return_value = event_result
        phase15 = {"missing_evidence": [], "evidence_checklist": [], "approval_hub": {"workflow_definitions": []},
            "risk_register": {"assessment_status": "Template: not assessed", "risks": []},
            "risk_dashboard": {"status": "Unavailable", "heatmap_data": []},
            "compliance_readiness": {"status": "Not assessed", "checklist": [], "exception_register": {}},
            "success_measurement": {"metrics": {}}, "executive_packages": {}}
        phase16 = {"production_gates": [], "executive_decision_board": {},
            "pilot_authorization": "Not Authorized", "production_authorization": "Not Authorized",
            "pilot_go_no_go": "NO-GO", "production_go_no_go": "NO-GO"}

        with patch("app.api.operations.phase15_governance_evidence", return_value=phase15), \
             patch("app.api.operations.phase16_authorization_readiness", return_value=phase16):
            result = phase17_operational_tracking(db)

        statement = str(db.execute.call_args.args[0]).upper()
        self.assertIn("SELECT", statement)
        self.assertIn("AUDITLOG", statement)
        self.assertFalse(any(token in statement for token in ("INSERT", "UPDATE", "DELETE", "ALTER")))
        self.assertFalse(result["tracking_records_created"])
    def test_phase15_governance_evidence_package_is_read_only_and_fail_closed(self):
        phase14 = {
            "pilot_go_no_go": "NO-GO", "production_go_no_go": "NO-GO", "readiness_percent": 0,
            "blockers": ["Migration 24", "No certified agents"],
            "workstreams": {
                "ownership_execution_playbook": {"evidence": {"candidate_validation": {
                    "observed_candidates": 9, "exact_guid_matches": 9, "unresolved": 0}},
                    "execution_performed": False},
                "migration_24_execution_playbook": {"migration_applied": False},
                "provider_approval_execution_plan": {"supported_providers": [
                    {"provider_label": name, "governance_state": "NotRecorded"}
                    for name in ("Azure OpenAI", "OpenAI", "Google Vertex AI", "Anthropic")
                ]},
                "model_approval_execution_plan": {"lifecycle_counts": {"Approved": 0}},
                "certification_execution_campaign": {"roles": [], "certifications_issued": False},
                "adapter_activation_playbook": {"probes_performed": False},
                "pilot_execution_acceptance_plan": {"pilot_executed": False},
                "production_readiness_gate_model": {"gates": []},
                "executive_decision_package": {"packages": {name: {"recommendation": "NO-GO"}
                    for name in ("CEO", "COO", "CIO")}},
            },
            "actions_performed": [], "controls_changed": False,
        }

        builder = getattr(operations, "_build_phase15_governance_package", None)
        self.assertIsNotNone(builder, "Phase 15 governance package builder is missing")
        result = builder(phase14)

        self.assertEqual(result["package_type"], "Phase 15 Controlled Pilot Governance & Evidence Management")
        self.assertEqual(len(result["approval_hub"]["workflow_definitions"]), 7)
        self.assertEqual(result["risk_register"]["assessment_status"], "Template: not assessed")
        self.assertEqual(result["success_measurement"]["metrics"]["approval_completion_percent"]["value"], "Unavailable")
        self.assertEqual(result["pilot_authorization_readiness"], "NO-GO")
        self.assertTrue(result["read_only"])
        self.assertFalse(result["approvals_created"])
        self.assertFalse(result["pilot_closed"])

    def test_phase16_pre_authorization_package_has_nine_gates_and_never_authorizes(self):
        phase15 = {
            "pilot_authorization_readiness": "NO-GO", "production_authorization_readiness": "NO-GO",
            "evidence_readiness_score": 0, "missing_evidence": ["Approval evidence", "Runtime evidence"],
            "governance_status": "BLOCKED", "risk_summary": {"assessment_status": "Template: not assessed"},
            "compliance_status": {"status": "Not assessed"},
            "executive_packages": {name: {"recommendation": "NO-GO"} for name in ("CEO", "COO", "CIO")},
            "approval_matrix": [], "approval_workflows": [], "actions_performed": [],
        }
        phase14 = {
            "production_gates": [{"gate": f"g{i}", "status": "BLOCKED", "current_evidence": None,
                                  "blockers": ["Unavailable"]} for i in range(1, 9)],
            "pilot_go_no_go": "NO-GO", "production_go_no_go": "NO-GO", "readiness_percent": 0,
            "workstreams": {"pilot_execution_acceptance_plan": {"workflow": ["Requirement", "Approval"]}},
            "executive_packages": {name: {"recommendation": "NO-GO"} for name in ("CEO", "COO", "CIO")},
        }

        builder = getattr(operations, "_build_phase16_authorization_package", None)
        self.assertIsNotNone(builder, "Phase 16 authorization package builder is missing")
        result = builder(phase15, phase14)

        self.assertEqual(result["package_type"], "Phase 16 Controlled Pilot Authorization & Operational Cutover Readiness")
        self.assertEqual(len(result["production_gates"]), 9)
        self.assertTrue(all(gate["status"] == "BLOCKED" for gate in result["production_gates"]))
        self.assertEqual(result["pilot_authorization"], "Not Authorized")
        self.assertEqual(result["production_authorization"], "Not Authorized")
        self.assertEqual(set(result["executive_decision_board"]), {"CEO", "COO", "CIO", "Governance Board"})
        self.assertTrue(result["read_only"])
        self.assertFalse(result["authorizations_created"])
        self.assertFalse(result["cutover_executed"])
        self.assertFalse(result["runtime_executed"])
        self.assertFalse(result["rls_enabled"])

    def test_phase14_execution_plan_contains_nine_fail_closed_gates(self):
        phase13 = {
            "pilot_go_no_go": "NO-GO",
            "production_go_no_go": "NO-GO",
            "operational_readiness_percent": 0,
            "operational_blockers": ["Migration 24", "No approved models"],
            "ownership_signoff_workflow": {"status": "Ready For Approval",
                "candidate_validation": {"expected_candidates": 9, "observed_candidates": 9,
                    "exact_guid_matches": 9, "unresolved": 0}, "approval_state": "Not submitted"},
            "ownership_approval_package": {"read_only": True},
            "ownership_rollback_package": {"read_only": True},
            "migration_approval_package": {"approval_package_status": "Ready For DBA Approval",
                "validation": {"migration_already_applied": False, "dependencies_ready": True},
                "execution_performed": False},
            "provider_governance": {"providers": [
                {"provider_label": name, "governance_state": "NotRecorded"}
                for name in ("Azure OpenAI", "OpenAI", "Google Vertex AI", "Anthropic")
            ], "provider_approval_performed": False},
            "model_governance_center": {"lifecycle_counts": {"Approved": 0}, "approval_performed": False},
            "certification_readiness": {"gap_analysis": [{"role": role, "ready_count": 0}
                for role in ("AI Business Analyst", "AI Solution Architect", "AI Data Analyst",
                             "Software Developer", "AI QA Engineer")], "certifications_created": False},
            "adapter_deployment_readiness": {"live_probes_performed": False},
            "pilot_runbook": {"pilot_executed": False},
            "executive_domains": [{"domain": key, "status": "BLOCKED", "evidence": {},
                "blockers": ["Missing verified readiness evidence"], "recommendation": "NO-GO"}
                for key in ("governance_readiness", "ownership_readiness", "workforce_readiness",
                    "certification_readiness", "model_readiness", "adapter_readiness",
                    "runtime_readiness", "rls_readiness")],
            "executive_views": {name: {"view": name, "recommendation": "NO-GO"}
                for name in ("CEO", "COO", "CIO")},
            "actions_performed": [],
            "controls_changed": False,
        }

        builder = getattr(operations, "_build_phase14_execution_plan", None)
        self.assertIsNotNone(builder, "Phase 14 execution plan builder is missing")
        result = builder(phase13)

        self.assertEqual(result["package_type"], "Phase 14 Controlled Pilot Execution Planning")
        self.assertEqual(len(result["production_gates"]), 8)
        self.assertTrue(all(gate["status"] == "BLOCKED" for gate in result["production_gates"]))
        self.assertEqual(result["pilot_go_no_go"], "NO-GO")
        self.assertEqual(result["production_go_no_go"], "NO-GO")
        self.assertEqual(set(result["executive_packages"]), {"CEO", "COO", "CIO"})
        self.assertEqual(len(result["workstreams"]), 9)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["controls_changed"])
        self.assertFalse(result["migration_executed"])
        self.assertFalse(result["ownership_executed"])
        self.assertFalse(result["provider_or_model_approved"])
        self.assertFalse(result["certifications_issued"])
        self.assertFalse(result["adapter_probed"])
        self.assertFalse(result["pilot_executed"])
        self.assertFalse(result["rls_enabled"])

    def test_phase13_package_is_read_only_and_contains_eight_board_domains(self):
        phase12 = {
            "recommendation": "NO-GO",
            "overall_readiness_percent": 0,
            "operational_blockers": ["Migration 24 deployment", "No approved models"],
            "readiness_domains": {
                name: {"ready": False, "status": "BLOCKED"}
                for name in (
                    "governance_readiness", "ownership_readiness", "workforce_readiness",
                    "certification_readiness", "model_readiness", "adapter_readiness",
                    "runtime_readiness", "rls_readiness",
                )
            },
            "workforce_readiness": {"candidate_classifications": None,
                                    "candidate_classification_status": "Unavailable: Migration 24 not applied"},
            "executive_views": {name: {"view": name} for name in ("CEO", "COO", "CIO")},
            "workstreams": {
                "ownership_remediation": {"candidate_count": 9, "exact_guid_match_count": 9,
                                          "unresolved_count": 0, "approval_package": {"read_only": True},
                                          "rollback_package": {"read_only": True}, "corrections_executed": False,
                                          "operational_gate": "BLOCKED"},
                "migration_deployment": {"validation": {"migration_already_applied": False,
                                                          "static_validation": "PASS",
                                                          "dependencies_ready": True,
                                                          "rollback_path": {"validated": True}},
                                         "execution_performed": False},
                "model_onboarding": {"supported_providers": [
                    {"provider_code": code, "provider_name": name, "registry_status": "NotCreated"}
                    for code, name in (("AZURE_OPENAI", "Azure OpenAI"), ("OPENAI", "OpenAI"),
                                       ("GOOGLE_VERTEX", "Google Vertex AI"), ("ANTHROPIC", "Anthropic"))
                ], "models": [], "proposal_and_review_package": {"read_only": True},
                    "model_approval_performed": False},
                "adapter_activation": {"deployment_package": {"providers": []}, "live_probes_performed": False},
                "certification_campaign": {"matrix": [], "required_evaluation_types": ["Capability", "Safety", "Security", "Governance"],
                                            "evidence_checklist": [], "certifications_created": False},
                "pilot_execution": {"workflow": [], "blockers": ["Runtime not validated"], "executions_created": False},
                "executive_go_no_go": {"readiness_domains": {"rls_readiness": {"status": "BLOCKED"}},
                                        "executive_views": {name: {"view": name} for name in ("CEO", "COO", "CIO")}},
            },
            "actions_performed": [],
            "controls_changed": False,
        }
        model_governance = {
            "lifecycle": [{"Status": "Approved", "ModelCount": 0}],
            "model_usage": [], "approved_models": [], "pending_reviews": 0,
        }
        ownership_archive = {"review_records": [], "ownership_changes_executed_by_review_workflow": False}

        builder = getattr(operations, "_build_phase13_pilot_package", None)
        self.assertIsNotNone(builder, "Phase 13 pilot package builder is missing")
        result = builder(phase12, model_governance, ownership_archive)

        self.assertEqual(result["package_type"], "Phase 13 Controlled Pilot Preparation")
        self.assertEqual(result["pilot_go_no_go"], "NO-GO")
        self.assertEqual(result["production_go_no_go"], "NO-GO")
        self.assertEqual(len(result["executive_domains"]), 8)
        self.assertEqual(set(result["executive_views"]), {"CEO", "COO", "CIO"})
        self.assertIsNone(result["workforce_readiness"]["candidate_classifications"])
        self.assertEqual(len(result["provider_governance"]["providers"]), 4)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["controls_changed"])
        self.assertFalse(result["ownership_execution_performed"])
        self.assertFalse(result["models_approved_by_package"])
        self.assertFalse(result["certifications_created_by_package"])
        self.assertFalse(result["live_probes_performed"])
        self.assertFalse(result["pilot_executed"])

    def test_phase13_route_composes_read_only_sources(self):
        from app.api.operations import phase13_pilot_preparation

        phase12 = {
            "recommendation": "NO-GO", "overall_readiness_percent": 0,
            "operational_blockers": ["Migration 24"], "readiness_domains": {},
            "workforce_readiness": {"candidate_classifications": None,
                                    "candidate_classification_status": "Unavailable: Migration 24 not applied"},
            "executive_views": {name: {"view": name} for name in ("CEO", "COO", "CIO")},
            "workstreams": {
                "ownership_remediation": {"candidate_count": 9, "exact_guid_match_count": 9,
                    "unresolved_count": 0, "operational_gate": "BLOCKED",
                    "approval_package": {}, "rollback_package": {}},
                "migration_deployment": {"validation": {"static_validation": "PASS",
                    "dependencies_ready": True, "migration_already_applied": False,
                    "rollback_path": {"validated": True}}},
                "model_onboarding": {"supported_providers": [], "models": [], "proposal_and_review_package": {}},
                "adapter_activation": {}, "certification_campaign": {"matrix": [],
                    "required_evaluation_types": [], "evidence_checklist": []},
                "pilot_execution": {"blockers": []},
                "executive_go_no_go": {"readiness_domains": {"rls_readiness": {}}},
            },
        }
        model_governance = {"lifecycle": [], "model_usage": [], "approved_models": [], "pending_reviews": 0}
        archive = {"review_records": [], "ownership_changes_executed_by_review_workflow": False}
        db = Mock()

        with patch("app.api.operations.phase12_activation_readiness", return_value=phase12), \
             patch("app.api.operations.model_governance_dashboard", return_value=model_governance), \
             patch("app.api.operations.ownership_remediation_audit_package", return_value=archive):
            result = phase13_pilot_preparation(db)

        self.assertEqual(result["production_go_no_go"], "NO-GO")
        self.assertFalse(result["controls_changed"])
        self.assertEqual(result["actions_performed"], [])
        db.execute.assert_not_called()

    def test_phase12_package_is_fail_closed_and_keeps_missing_metrics_unavailable(self):
        phase11 = {
            "generated_at_utc": "2026-10-26T00:00:00+00:00",
            "go_no_go": "NO-GO",
            "overall_readiness_percent": 12.5,
            "sections": {"governance_readiness": {"ready": True}},
            "blocking_items": ["Migration 24 deployment", "No approved models"],
            "migration_validation": {"static_validation": "PASS", "dependencies_ready": True,
                                     "migration_already_applied": False, "required_columns": [],
                                     "rollback_path": {"validated": True}},
            "ownership_approval": {"summary": {"candidate_count": 9, "exact_guid_match_count": 9,
                                                "unresolved_count": 0, "expected_count_validated": True}},
            "ownership_rollback": {"read_only": True, "automatic_rollback": False},
            "model_onboarding": {"supported_provider_onboarding": [], "models": [], "approval_automatic": False},
            "model_approval_evidence": {"read_only": True},
            "adapter_deployment": {"providers": [], "provider_calls_performed": False},
            "certification_campaign": {"campaigns": [], "agents_activated": False,
                                       "skills_or_certifications_changed": False},
            "launch_readiness": {
                "model_status": {"approved_count": 0},
                "adapter_status": {"configured_count": 0, "healthy_count": 0},
                "certification_status": {"campaign_ready_agents": 0, "campaign_agents": 0,
                    "active_skill_coverage": {"coverage_percent": 0},
                    "active_certification_coverage": {"coverage_percent": 0}},
                "runtime_status": {"assignments_ready": 0, "queue_ready": 0,
                    "execution_ready": 0, "deliverables_ready": 0},
                "ownership_status": {"coverage_percent": 80},
                "rls_status": {"status": "Disabled", "enabled_predicate_coverage_percent": 0},
            },
            "runtime_readiness_report": {"assignments_ready": 0, "queue_ready": 0,
                                         "execution_ready": 0, "deliverables_ready": 0},
            "execution_blocker_report": {"blockers": ["Runtime not validated"]},
            "activation_runbook": {"read_only": True, "checklists": {}},
            "deployment_checklist": [],
            "rollback_checklist": [],
        }
        workforce = {
            "reuse_migration_available": False,
            "candidate_classifications": None,
            "workforce_requests_by_status": {"PendingApproval": 2},
            "active_agents": 1,
            "total_agents": 56,
            "certified_active_agents": 0,
            "workforce_utilization_percent": 0.0,
        }
        executive_views = {name: {"view": name, "recommendation": "NO-GO", "blockers": ["Unavailable evidence"]}
                           for name in ("CEO", "COO", "CIO")}

        package_builder = getattr(operations, "_build_phase12_activation_package", None)
        self.assertIsNotNone(package_builder, "Phase 12 activation package builder is missing")
        result = package_builder(phase11, workforce, executive_views)

        self.assertEqual(result["package_type"], "Phase 12 Operational Activation Readiness")
        self.assertEqual(result["recommendation"], "NO-GO")
        self.assertIsNone(result["workforce_readiness"]["candidate_classifications"])
        self.assertEqual(result["workforce_readiness"]["candidate_classification_status"], "Unavailable: Migration 24 not applied")
        self.assertFalse(result["actions_performed"])
        self.assertFalse(result["controls_changed"])
        self.assertEqual(set(result["executive_views"]), {"CEO", "COO", "CIO"})
        self.assertIn("migration_deployment", result["workstreams"])
        self.assertIn("pilot_execution", result["workstreams"])

    def test_phase12_route_reads_current_workforce_state_without_mutations(self):
        from app.api.operations import phase12_activation_readiness

        phase11 = {
            "go_no_go": "NO-GO", "overall_readiness_percent": 0,
            "blocking_items": ["Migration 24"], "sections": {},
            "migration_validation": {"static_validation": "PASS", "dependencies_ready": True,
                                     "migration_already_applied": False, "rollback_path": {"validated": True}},
            "ownership_approval": {"summary": {"candidate_count": 9, "exact_guid_match_count": 9,
                                                "unresolved_count": 0, "expected_count_validated": True}},
            "ownership_rollback": {}, "model_onboarding": {"models": [], "supported_provider_onboarding": []},
            "model_approval_evidence": {}, "adapter_deployment": {"providers": []},
            "certification_campaign": {"campaigns": []},
            "launch_readiness": {"certification_status": {
                "campaign_ready_agents": 0, "campaign_agents": 0,
                "active_skill_coverage": {"coverage_percent": None},
                "active_certification_coverage": {"certified_agents": 0, "coverage_percent": None},
            }, "model_status": {"approved_count": 0},
                "adapter_status": {"configured_count": 0, "healthy_count": 0},
                "ownership_status": {"coverage_percent": 0},
                "rls_status": {"status": "Disabled", "enabled_predicate_coverage_percent": 0}},
            "runtime_readiness_report": {"assignments_ready": 0, "queue_ready": 0,
                                         "execution_ready": 0, "deliverables_ready": 0,
                                         "ownership_coverage_percent": 0},
            "execution_blocker_report": {"blockers": ["Runtime not validated"]},
            "activation_runbook": {}, "deployment_checklist": [], "rollback_checklist": [],
        }
        workforce_result = Mock()
        workforce_result.mappings.return_value.one.return_value = {
            "TotalAgents": 56, "ActiveAgents": 1, "ActiveUtilization": 0,
        }
        request_result = Mock()
        request_result.mappings.return_value.all.return_value = [{"Status": "PendingApproval", "RecordCount": 2}]
        db = Mock()
        db.execute.side_effect = [workforce_result, request_result]
        views = {name: {"view": name, "recommendation": "NO-GO"} for name in ("CEO", "COO", "CIO")}

        with patch("app.api.operations.phase11_deployment_package", return_value=phase11), \
             patch("app.api.operations.executive_readiness", side_effect=lambda name, _db: views[name]):
            result = phase12_activation_readiness(db)

        self.assertEqual(result["workforce_readiness"]["total_agents"], 56)
        self.assertEqual(result["overall_readiness_percent"], 0)
        self.assertEqual(result["workforce_readiness"]["workforce_requests_by_status"]["PendingApproval"], 2)
        self.assertIsNone(result["workforce_readiness"]["workforce_readiness_percent"])
        self.assertFalse(result["controls_changed"])
        self.assertEqual(db.execute.call_count, 2)
        self.assertFalse(any(any(token in str(call.args[0]).upper() for token in ("INSERT", "UPDATE", "DELETE", "ALTER"))
                             for call in db.execute.call_args_list))

    def test_migration_24_validator_is_static_and_checks_contract(self):
        script = """
        IF OBJECT_ID('dbo.WorkforceReuseAssessment','U') IS NULL
        CREATE TABLE dbo.WorkforceReuseAssessment(
          CONSTRAINT UQ_WorkforceReuseAssessment_Project_Role_Agent UNIQUE(ProjectID,RoleCode,AgentID),
          CONSTRAINT CK_WorkforceReuseAssessment_MatchScore CHECK (MatchScore BETWEEN 0 AND 100),
          CONSTRAINT CK_WorkforceReuseAssessment_Classification CHECK (Classification IN ('Ready Candidate')),
          CONSTRAINT CK_WorkforceReuseAssessment_Status CHECK (AssessmentStatus IN ('Assigned'))
        );
        IF EXISTS (SELECT 1 FROM sys.check_constraints) ALTER TABLE X DROP CONSTRAINT X;
        IF EXISTS (SELECT 1 FROM sys.check_constraints) ALTER TABLE X DROP CONSTRAINT Y;
        """

        result = validate_migration_24_script(script)

        self.assertEqual(result["static_validation"], "PASS")
        self.assertFalse(result["database_dry_run_executed"])
        self.assertFalse(result["migration_applied"])
        self.assertFalse(result["rollback_sql_present"])

    def test_checked_in_migration_24_passes_static_validation_only(self):
        result = validate_migration_24_script(_migration_24_source())

        self.assertEqual(result["static_validation"], "PASS")
        self.assertTrue(result["create_is_guarded"])
        self.assertTrue(result["constraint_replacement_is_guarded"])
        self.assertFalse(result["database_dry_run_executed"])
        self.assertFalse(result["migration_applied"])

    def test_migration_validation_route_only_reads_dependency_metadata(self):
        dependencies = Mock()
        dependencies.mappings.return_value.all.return_value = [
            {"TableName": name, "Present": 1} for name in ("Project", "Task", "WorkforceRoleProfile", "Agent")
        ]
        migration_result = Mock()
        migration_result.scalar_one.return_value = 0
        db = Mock()
        db.execute.side_effect = [dependencies] + [Mock(scalar_one=Mock(return_value=1)) for _ in range(6)] + [migration_result]

        result = validate_migration_24(db)

        self.assertFalse(result["migration_applied"])
        self.assertTrue(result["dependencies_ready"])
        self.assertFalse(result["database_dry_run_executed"])
        self.assertEqual(db.execute.call_count, 8)
        self.assertFalse(any("INSERT" in str(call.args[0]).upper() or "ALTER" in str(call.args[0]).upper() for call in db.execute.call_args_list))

    def test_migration_validation_reports_missing_required_columns_and_checksum(self):
        dependency_result = Mock()
        dependency_result.mappings.return_value.all.return_value = [
            {"TableName": name, "Present": 1} for name in ("Project", "Task", "WorkforceRoleProfile", "Agent")
        ]
        column_results = [Mock(scalar_one=Mock(return_value=1)) for _ in range(6)]
        column_results[1] = Mock(scalar_one=Mock(return_value=0))
        applied_result = Mock(scalar_one=Mock(return_value=0))
        db = Mock()
        db.execute.side_effect = [dependency_result, *column_results, applied_result]

        result = validate_migration_24(db)

        self.assertFalse(result["dependencies_ready"])
        self.assertEqual(result["missing_columns"], ["WorkforceRoleProfile.RequiredSkillsJson"])
        self.assertEqual(len(result["script_sha256"]), 64)
        self.assertGreater(result["go_batch_count"], 0)
        self.assertFalse(result["database_execution_performed"])

    def test_ownership_review_writes_audit_only(self):
        owner_id = uuid.uuid4()
        candidate = {
            "table": "Requirement", "record_id": str(uuid.uuid4()),
            "legacy_created_by": str(owner_id), "candidate_user_id": str(owner_id),
            "matched_user_id": str(owner_id), "matched_email": "owner@example.test",
            "owner_active": True, "resolvable_exact_guid": True, "recommended_action": "UPDATE",
        }
        with patch("app.api.operations.ownership_remediation_report", return_value={"rows": [candidate], "total_null_owner_rows": 1, "resolvable_exact_guid_rows": 1}):
            db = Mock()
            result = record_ownership_review(
                OwnershipReviewDecision(decision="ApprovedForManualChange", reason="Reviewed exact GUID evidence.", evidence="Identity record ticket SEC-2026-88.", change_ticket="CHG-2026-88"),
                db,
                {"sub": str(uuid.uuid4())},
            )

        self.assertTrue(result["audit_recorded"])
        self.assertFalse(result["ownership_sql_executed"])
        self.assertFalse(result["ownership_records_changed"])
        self.assertEqual(db.execute.call_count, 1)
        self.assertIn("INSERT dbo.AuditLog", str(db.execute.call_args.args[0]))
        db.commit.assert_called_once()

    def test_certification_campaign_flags_missing_profiles_without_creating_them(self):
        profiles = Mock()
        profiles.mappings.return_value.all.return_value = []
        agents = Mock()
        agents.mappings.return_value.all.return_value = []
        db = Mock()
        db.execute.side_effect = [profiles, agents]

        result = certification_campaign(db)

        self.assertEqual(len(result["campaigns"]), 5)
        self.assertTrue(all(row["role_profile_status"] == "NotInstalled" for row in result["campaigns"]))
        self.assertFalse(result["agents_activated"])
        self.assertFalse(result["skills_or_certifications_changed"])
        self.assertEqual(db.execute.call_count, 2)
        self.assertFalse(any("INSERT" in str(call.args[0]).upper() or "UPDATE" in str(call.args[0]).upper() for call in db.execute.call_args_list))

    def test_activation_runbook_is_read_only_and_preserves_no_go(self):
        launch = {
            "as_of_utc": "2026-10-26T00:00:00+00:00",
            "recommendation": "NO-GO", "blockers": ["No approved models"],
        }
        db = Mock()
        with patch("app.api.operations._phase10_launch_snapshot", return_value=launch):
            result = activation_runbook(db)

        self.assertTrue(result["read_only"])
        self.assertEqual(result["recommendation"], "NO-GO")
        self.assertIn("model_onboarding", result["checklists"])
        self.assertIn("rollback", result["checklists"])
        self.assertFalse(any(call.args and ("INSERT" in str(call.args[0]).upper() or "UPDATE" in str(call.args[0]).upper()) for call in db.execute.call_args_list))

    def test_phase10_launch_snapshot_consolidates_blockers_without_control_changes(self):
        db = Mock()
        ownership = {"candidate_count_validated": True, "manual_review_rows": 0, "total_null_owner_rows": 9, "resolvable_exact_guid_rows": 9}
        deployment = {"providers": [{"configuration_status": "NotConfigured"}]}
        campaign = {"campaigns": [{"agents": []}]}
        readiness = {
            "runtime": {"assignments_ready": 0, "queue_ready": 0, "execution_ready": 0, "deliverables_ready": 0},
            "security": {"rls_enabled": False, "predicate_coverage_percent": 0, "ownership_coverage_percent": 85},
            "phase8": {
                "phase7_migration_applied": False,
                "ownership": {"coverage_percent": 85},
                "runtime_ownership": {"coverage_percent": 0},
            },
        }
        models = {
            "lifecycle": [{"Status": "Pending", "ModelCount": 0}],
            "pending_reviews": 0,
            "approval_sla": {"configured": False, "target_hours": None, "status": "NotConfigured"},
        }
        certs = {
            "active_agent_certification_coverage": {"certified_agents": 0, "active_agents": 1, "coverage_percent": 0},
            "active_agent_skill_coverage": {"agents_meeting_required_active_skills": 0, "active_agents_with_role_requirements": 1, "coverage_percent": 0},
        }
        adapters = [{"health_status": "NotChecked"}]
        with patch("app.api.operations.ownership_remediation_report", return_value=ownership), \
             patch("app.api.operations.adapter_deployment_package", return_value=deployment), \
             patch("app.api.operations.certification_campaign", return_value=campaign), \
             patch("app.api.operations.validate_migration_24", return_value={
                 "static_validation": "PASS", "dependencies_ready": True,
                 "rollback_path": {"validated": True}, "migration_already_applied": False,
             }), \
             patch("app.api.operations._phase9_readiness_snapshot", return_value=readiness), \
             patch("app.api.operations.model_governance_dashboard", return_value=models), \
             patch("app.api.operations.certification_dashboard", return_value=certs), \
             patch("app.api.operations.list_execution_adapters", return_value=adapters):
            result = _phase10_launch_snapshot(db)

        self.assertEqual(result["recommendation"], "NO-GO")
        self.assertEqual(result["ownership_status"]["exact_guid_matches"], 9)
        self.assertEqual(result["rls_status"]["status"], "Disabled")
        self.assertFalse(result["actions_performed"])
        db.execute.assert_not_called()

    def test_phase11_package_contains_eight_readiness_domains_and_preserves_no_go(self):
        migration = {
            "static_validation": "PASS", "dependencies_ready": True,
            "rollback_path": {"validated": True, "path": "preserve table and roll back app"}, "migration_already_applied": False,
        }
        ownership = {"summary": {"candidate_count": 9, "unresolved_count": 0}, "verification_report": []}
        rollback = {"rollback_sql": "-- review only"}
        models = {"providers": [], "models": [], "pending_proposals": 0}
        campaign = {"campaigns": []}
        runbook = {"checklists": {}}
        launch = {
            "recommendation": "NO-GO",
            "ownership_status": {"candidate_count": 9, "exact_guid_matches": 9, "unresolved_records": 0, "coverage_percent": 80, "candidate_set_validated": True},
            "adapter_status": {"configured_count": 0, "healthy_count": 0},
            "model_status": {"approved_count": 0, "pending_reviews": 0},
            "certification_status": {"campaign_ready_agents": 0, "campaign_agents": 0,
                                     "active_skill_coverage": {"coverage_percent": 0},
                                     "active_certification_coverage": {"certified_agents": 0}},
            "runtime_status": {"assignments_ready": 0, "assignments_total": 0, "queue_ready": 0, "execution_ready": 0, "deliverables_ready": 0, "missing_tables": []},
            "rls_status": {"status": "Disabled", "enabled_predicate_coverage_percent": 0},
        }
        phase8 = {
            "ownership": {"coverage_percent": 80},
            "runtime_ownership": {"coverage_percent": 0},
            "rls": {"enabled": False, "policy_coverage_percent": 0},
        }
        audit_result = Mock()
        audit_result.mappings.return_value.first.return_value = None
        db = Mock()
        db.execute.return_value = audit_result

        with patch("app.api.operations.validate_migration_24", return_value=migration), \
             patch("app.api.operations.export_ownership_approval_package", return_value=ownership), \
             patch("app.api.operations.export_ownership_rollback_package", return_value=rollback), \
             patch("app.api.operations.model_onboarding_package", return_value=models), \
             patch("app.api.operations.model_approval_evidence_package", return_value={"read_only": True}), \
             patch("app.api.operations.adapter_deployment_package", return_value={"providers": []}), \
             patch("app.api.operations.certification_campaign", return_value=campaign), \
             patch("app.api.operations.activation_runbook", return_value=runbook), \
             patch("app.api.operations._phase10_launch_snapshot", return_value=launch), \
             patch("app.api.operations.phase8_readiness", return_value=phase8):
            result = phase11_deployment_package(db)

        self.assertEqual(len(result["sections"]), 8)
        self.assertEqual(result["overall_readiness_percent"], 12.5)
        self.assertTrue(result["sections"]["governance_readiness"]["ready"])
        self.assertFalse(result["migration_applied"])
        self.assertEqual(result["go_no_go"], "NO-GO")
        self.assertFalse(result["migration_applied"])
        self.assertFalse(result["remediation_executed"])
        self.assertFalse(result["model_approved_by_package"])
        self.assertFalse(result["agent_activated_by_package"])
        self.assertFalse(result["rls_enabled_by_package"])
        self.assertIn("overall_readiness_percent", result)
        self.assertIn("execution_blocker_report", result)
        self.assertFalse(any("UPDATE dbo." in str(call.args[0]) or "INSERT dbo." in str(call.args[0]) for call in db.execute.call_args_list))

    def test_adapter_deployment_package_is_diagnostic_only(self):
        db = Mock()
        providers = [{
            "provider_code": "OPENAI", "provider_name": "OpenAI", "config": None,
            "health_status": "NotChecked",
        }]
        with patch("app.api.operations.list_execution_adapters", return_value=providers):
            result = adapter_deployment_package(db)

        self.assertFalse(result["provider_calls_performed"])
        self.assertFalse(result["runtime_enabled"])
        self.assertFalse(result["providers"][0]["credential_verified"])
        self.assertIn("adapter configuration missing", result["providers"][0]["blockers"])
        db.execute.assert_not_called()

    def test_adapter_configuration_rejects_raw_secret_values(self):
        with self.assertRaises(ValidationError):
            AdapterConfiguration(
                endpoint_url="https://api.openai.com",
                deployment_name="default",
                model_catalog_id=uuid.uuid4(),
                secret_reference="sk-live-raw-secret-value",
            )
        valid = AdapterConfiguration(
            endpoint_url="https://api.openai.com",
            deployment_name="default",
            model_catalog_id=uuid.uuid4(),
            secret_reference="azure-kv://openai-api-key",
        )
        self.assertEqual(valid.secret_reference, "azure-kv://openai-api-key")

    def test_report_generates_updates_only_for_exact_app_user_guid_matches(self):
        owner_id = uuid.uuid4()
        resolvable = {
            "RecordID": uuid.uuid4(), "LegacyOwner": str(owner_id),
            "CandidateUserID": owner_id, "MatchedUserID": owner_id,
            "MatchedEmail": "user@example.test", "OwnerIsActive": True,
        }
        unresolved = {
            "RecordID": uuid.uuid4(), "LegacyOwner": "legacy-user-name",
            "CandidateUserID": None, "MatchedUserID": None,
            "MatchedEmail": None, "OwnerIsActive": None,
        }
        db = Mock()
        db.execute.side_effect = [
            Mock(mappings=Mock(return_value=Mock(all=Mock(return_value=[resolvable])))),
            Mock(mappings=Mock(return_value=Mock(all=Mock(return_value=[unresolved])))),
            Mock(mappings=Mock(return_value=Mock(all=Mock(return_value=[])))),
            Mock(mappings=Mock(return_value=Mock(all=Mock(return_value=[])))),
        ]

        report = ownership_remediation_report(db)

        self.assertTrue(report["is_read_only"])
        self.assertFalse(report["automatically_applied"])
        self.assertEqual(report["total_null_owner_rows"], 2)
        self.assertEqual(report["resolvable_exact_guid_rows"], 1)
        self.assertEqual(report["manual_review_rows"], 1)
        self.assertIn(str(owner_id), report["generated_update_script"])
        self.assertNotIn(str(unresolved["RecordID"]), report["generated_update_script"])
        self.assertIn(str(owner_id), report["generated_rollback_script"])
        self.assertFalse(report["automatically_applied"])
        self.assertEqual(report["candidate_validation"], "count_mismatch_requires_review")
        self.assertIn("dbo.Issue", str(db.execute.call_args_list[3].args[0]))
        self.assertEqual(db.execute.call_count, 4)

    def test_guid_candidate_requires_explicit_equality_before_sql_generation(self):
        candidate_id, other_user_id = uuid.uuid4(), uuid.uuid4()
        mismatched = {
            "RecordID": uuid.uuid4(), "LegacyOwner": str(candidate_id),
            "CandidateUserID": candidate_id, "MatchedUserID": other_user_id,
            "MatchedEmail": "other@example.test", "OwnerIsActive": True,
        }
        empty = Mock(mappings=Mock(return_value=Mock(all=Mock(return_value=[]))))
        db = Mock()
        db.execute.side_effect = [
            Mock(mappings=Mock(return_value=Mock(all=Mock(return_value=[mismatched])))),
            empty, empty, empty,
        ]

        report = ownership_remediation_report(db)

        self.assertFalse(report["rows"][0]["resolvable_exact_guid"])
        self.assertEqual(report["manual_review_rows"], 1)
        self.assertNotIn(str(other_user_id), report["generated_update_script"])

    def test_no_null_owners_returns_non_executable_comment(self):
        db = Mock()
        empty = Mock(mappings=Mock(return_value=Mock(all=Mock(return_value=[]))))
        db.execute.side_effect = [empty, empty, empty, empty]

        report = ownership_remediation_report(db)

        self.assertEqual(report["total_null_owner_rows"], 0)
        self.assertEqual(report["generated_update_script"], "-- No exact-GUID owner candidates found.")
        self.assertFalse(report["automatically_applied"])
        self.assertFalse(report["exact_guid_candidate_count_validated"])

    def test_nine_exact_guid_candidates_are_count_validated(self):
        rows = []
        for _ in range(9):
            owner_id = uuid.uuid4()
            rows.append({
                "RecordID": uuid.uuid4(), "LegacyOwner": str(owner_id),
                "CandidateUserID": owner_id, "MatchedUserID": owner_id,
                "MatchedEmail": "owner@example.test", "OwnerIsActive": True,
            })
        empty = Mock(mappings=Mock(return_value=Mock(all=Mock(return_value=[]))))
        populated = Mock(mappings=Mock(return_value=Mock(all=Mock(return_value=rows))))
        db = Mock()
        db.execute.side_effect = [populated, empty, empty, empty]

        report = ownership_remediation_report(db)

        self.assertEqual(report["resolvable_exact_guid_rows"], 9)
        self.assertTrue(report["exact_guid_candidate_count_validated"])
        self.assertTrue(report["candidate_count_validated"])
        self.assertEqual(report["candidate_validation"], "validated")
        self.assertEqual(report["generated_update_script"].count("UPDATE dbo.Requirement"), 9)
        self.assertEqual(report["generated_rollback_script"].count("UPDATE dbo.Requirement"), 9)
        self.assertFalse(report["automatically_applied"])

    def test_missing_adapter_secret_records_configuration_incomplete(self):
        db = Mock()
        config_result = Mock()
        config_result.mappings.return_value.first.return_value = {
            "AdapterConfigID": uuid.uuid4(), "Status": "Configured",
            "EndpointUrl": "https://api.openai.com", "DeploymentName": "default",
            "ModelCatalogID": uuid.uuid4(), "SecretReference": "",
        }
        db.execute.side_effect = [config_result, Mock(), Mock()]

        result = record_adapter_health_check("OPENAI", db, {"sub": "operator"})

        self.assertEqual(result["status"], "ConfigurationIncomplete")
        self.assertFalse(result["network_probe_performed"])
        health_insert = str(db.execute.call_args_list[1].args[0])
        self.assertIn("ExecutionAdapterHealthCheck", health_insert)
        self.assertIn("ConfigurationIncomplete", db.execute.call_args_list[1].args[1]["status"])
        db.commit.assert_called_once()

    def test_real_provider_probe_result_is_recorded_without_secret_value(self):
        config_result = Mock()
        config_result.mappings.return_value.first.return_value = {
            "AdapterConfigID": uuid.uuid4(), "Status": "Configured",
            "EndpointUrl": "https://api.openai.com", "DeploymentName": "unused",
            "ModelCatalogID": uuid.uuid4(), "SecretReference": "env://OPENAI_API_KEY",
            "ModelStatus": "Approved", "ProviderStatus": "Active",
        }
        db = Mock()
        db.execute.side_effect = [config_result, Mock(), Mock()]
        probe_result = Mock(status="Healthy", details="Authenticated provider API request succeeded.", http_status=200)

        with patch("app.api.operations.configured_secret_resolver") as resolver, patch(
            "app.api.operations.probe_provider", return_value=probe_result
        ) as probe:
            resolver.return_value.resolve.return_value = "do-not-log-this-secret"
            result = record_adapter_health_check("OPENAI", db, {"sub": "operator"})

        self.assertEqual(result["status"], "Healthy")
        self.assertTrue(result["network_probe_performed"])
        self.assertNotIn("do-not-log-this-secret", str(db.execute.call_args_list[2]))
        probe.assert_called_once_with("OPENAI", "https://api.openai.com", "unused", "do-not-log-this-secret")
        db.commit.assert_called_once()

    def test_ownership_approval_package_is_read_only_and_contains_risk_and_checklist(self):
        empty = Mock(mappings=Mock(return_value=Mock(all=Mock(return_value=[]))))
        db = Mock()
        db.execute.side_effect = [empty, empty, empty, empty]

        with patch("app.api.operations.phase8_readiness", return_value={"ownership": {"coverage_percent": 81.2}}):
            package = export_ownership_approval_package(db)

        self.assertTrue(package["read_only"])
        self.assertFalse(package["auto_apply"])
        self.assertEqual(package["summary"]["recommendation"], "NO-GO")
        self.assertEqual(package["summary"]["ownership_coverage_percent"], 81.2)
        self.assertIn("candidate_resolution_percent", package["summary"])
        self.assertIn("rollback_sql", package)
        self.assertTrue(package["approval_checklist"])
        self.assertEqual(db.execute.call_count, 4)

    def test_rls_review_package_never_enables_rls(self):
        db = Mock()
        with patch("app.api.operations.phase8_readiness", return_value={
            "as_of_utc": "2026-10-26T00:00:00+00:00",
            "recommendation": "NO-GO", "ownership": {"coverage_percent": 50, "valid_rows": 1, "total_rows": 2, "tables": {}},
            "runtime_ownership": {"coverage_percent": None, "tables": {}, "missing_tables": ["AgentExecution"]},
            "rls": {"enabled": False, "policy_coverage_percent": 0, "tables": [], "will_enable_rls": False},
            "checks": {"historical_ownership_coverage_100_percent": False},
        }):
            package = export_rls_readiness_package(db)

        self.assertFalse(package["enable_rls"])
        self.assertIn("deployment_checklist", package)
        self.assertIn("rollback_checklist", package)
        self.assertFalse(package["predicate_coverage"]["enabled"])
        db.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
