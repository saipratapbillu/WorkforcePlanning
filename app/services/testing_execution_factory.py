"""Test planning and synthetic quality simulation; never executes test assets."""

from __future__ import annotations

from typing import Any


TEST_DOMAINS = ("unit", "integration", "security", "performance", "uat")


def _artifact_paths(code_package: dict[str, Any] | None) -> set[str]:
    if not isinstance(code_package, dict):
        return set()
    result = set()
    for item in code_package.get("files", []):
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            result.add(item["path"])
    return result


def _criterion_count(project_package: dict[str, Any]) -> int:
    return sum(len(feature.get("acceptance_criteria", []))
               for feature in project_package.get("feature_catalog", [])) + sum(
        len(story.get("acceptance_criteria", []))
        for story in project_package.get("user_story_catalog", []))


def build_testing_execution_package(
    technical_delivery_package: dict[str, Any] | None,
    project_package: dict[str, Any] | None,
    delivery_package: dict[str, Any] | None,
    code_package: dict[str, Any] | None,
) -> dict[str, Any]:
    """Produce test plans and synthetic forecasts from artifact metadata only."""
    technical = technical_delivery_package if isinstance(technical_delivery_package, dict) else {}
    artifacts = technical.get("artifacts", {}) if isinstance(technical.get("artifacts", {}), dict) else {}
    test_design = artifacts.get("testing_blueprint", {}) if isinstance(artifacts.get("testing_blueprint", {}), dict) else {}
    security_design = artifacts.get("security_blueprint", {}) if isinstance(artifacts.get("security_blueprint", {}), dict) else {}
    project = project_package if isinstance(project_package, dict) else {}
    delivery = delivery_package if isinstance(delivery_package, dict) else {}
    paths = _artifact_paths(code_package)

    test_asset_count = sum(path.startswith("tests/") or "/tests/" in path for path in paths)
    source_test_assets = [path for path in paths if "test" in path.lower() or "spec" in path.lower()]
    stories = project.get("user_story_catalog", [])
    features = project.get("feature_catalog", [])
    criteria_count = _criterion_count(project)
    endpoints = artifacts.get("api_catalog", {}).get("endpoints", []) if isinstance(artifacts.get("api_catalog"), dict) else []
    entities = artifacts.get("database_blueprint", {}).get("entities", []) if isinstance(artifacts.get("database_blueprint"), dict) else []

    planned_categories = {
        "unit": bool(test_design.get("unit_tests")),
        "integration": bool(test_design.get("integration_tests")) and bool(endpoints or entities),
        "security": bool(test_design.get("security_tests")) and bool(security_design.get("authorization_design")),
        "performance": bool(test_design.get("performance_tests")),
        "uat": bool(test_design.get("uat_scenarios")) and bool(stories or features),
    }
    if code_package is not None:
        asset_categories = {
            "unit": any("unit" in path.lower() or path.endswith("test_models.py") or path.endswith(".test.js") or "ValidationTests" in path for path in paths),
            "integration": any("integration" in path.lower() for path in paths),
            "security": any("security" in path.lower() for path in paths),
            "performance": any("performance" in path.lower() or "k6" in path.lower() for path in paths),
            "uat": any("uat" in path.lower() for path in paths),
        }
        planned_categories = {key: planned_categories[key] and asset_categories[key] for key in TEST_DOMAINS}
    covered_count = sum(planned_categories.values())
    coverage_percent = round(100 * covered_count / len(TEST_DOMAINS), 1)

    strategy = {
        "approach": "Risk-based test planning with isolated synthetic scenarios; no test execution is performed.",
        "test_levels": [
            {"level": "Unit", "focus": "Validation, domain behavior, error mapping, and pure transformations"},
            {"level": "Integration", "focus": "API/database transactions, tenant scoping, identity, and audit contracts"},
            {"level": "Security", "focus": "Authentication, authorization, input validation, data handling, and secret hygiene"},
            {"level": "Performance", "focus": "Load, stress, volume, and degradation scenarios after targets are approved"},
            {"level": "UAT", "focus": "Business outcomes and story acceptance criteria with accountable reviewers"},
        ],
        "execution_environment": "NOT_CREATED",
        "test_data": "Synthetic and minimized; production data is prohibited for this plan.",
        "human_review_required": True,
    }
    coverage_map = {
        "coverage_percent": coverage_percent,
        "covered_domains": [domain for domain in TEST_DOMAINS if planned_categories[domain]],
        "uncovered_domains": [domain for domain in TEST_DOMAINS if not planned_categories[domain]],
        "mapped_acceptance_criteria": criteria_count,
        "planned_features": len(features), "planned_user_stories": len(stories),
        "api_operations_in_scope": len(endpoints), "data_entities_in_scope": len(entities),
        "source_test_assets": sorted(source_test_assets),
        "asset_count": test_asset_count,
        "basis": "Design/artifact mapping coverage, not executed code coverage.",
    }

    unit_count = len(test_design.get("unit_tests", []))
    unit_test_report = {
        "execution_status": "NOT_EXECUTED",
        "planned_scenarios": test_design.get("unit_tests", []),
        "simulated_pass_rate_percent": 85.0 if unit_count else None,
        "simulated_failure_rate_percent": 15.0 if unit_count else None,
        "observed_pass_rate_percent": None,
        "coverage_forecast_percent": 70.0 if unit_count else None,
        "pass_rate_basis": "SIMULATED_FORECAST_NOT_OBSERVED",
        "coverage_basis": "Placeholder planning forecast; coverage requires instrumented execution.",
        "execution_count": 0,
    }

    integration_scenarios = [
        {"scenario_id": f"INT-{index:02d}", "scenario": f"Contract and persistence behavior for {endpoint.get('method', 'operation')} {endpoint.get('path', 'planned interface')}",
         "success_criteria": ["Contract validates", "Authorization boundary holds", "Failure is handled without partial unauthorized state"],
         "status": "PLANNED_NOT_EXECUTED"}
        for index, endpoint in enumerate(endpoints, start=1)
    ]
    integration_scenarios.extend([
        {"scenario_id": "INT-IDENTITY", "scenario": "Identity and tenant claims are validated before data access",
         "success_criteria": ["Invalid identity rejected", "Cross-tenant access denied", "Actor is derived server-side"], "status": "PLANNED_NOT_EXECUTED"},
        {"scenario_id": "INT-AUDIT", "scenario": "Sensitive transition and audit writer behavior",
         "success_criteria": ["Actor/action/resource/correlation recorded", "Failure does not report success", "No secret values logged"], "status": "PLANNED_NOT_EXECUTED"},
    ])
    integration_report = {
        "execution_status": "NOT_EXECUTED",
        "integration_matrix": [{"source": "API", "target": "Persistence", "scenarios": max(len(endpoints), 1)},
                               {"source": "Identity", "target": "Authorization", "scenarios": 1},
                               {"source": "Application", "target": "Audit", "scenarios": 1}],
        "scenarios": integration_scenarios,
        "simulated_success_rate_percent": 80.0 if integration_scenarios else None,
        "observed_success_rate_percent": None,
        "basis": "Scenario readiness estimate only; no service, database, or integration was called.",
    }

    security_tests = list(test_design.get("security_tests", []))
    security_tests.extend([
        "Authentication: missing, invalid, expired, wrong-issuer, and revoked credentials are denied.",
        "Authorization: wrong-role, wrong-resource, and cross-tenant access are denied server-side.",
        "Input validation: malformed, oversized, injection-shaped, and unexpected fields are rejected.",
    ])
    security_findings = [
        {"finding_id": "SEC-SIM-01", "severity": "HIGH", "title": "Identity provider is not configured in generated scaffold",
         "evidence": "Generated source explicitly fails closed pending approved identity integration.",
         "remediation": "Configure issuer/audience/signature/revocation validation and add negative auth tests."},
        {"finding_id": "SEC-SIM-02", "severity": "HIGH", "title": "Tenant-scoped persistence and authorization adapters are placeholders",
         "evidence": "Generated repositories intentionally reject use until reviewed adapters are bound.",
         "remediation": "Implement tenant-bound repository queries and test cross-tenant denial."},
    ]
    security_report = {
        "execution_status": "NOT_EXECUTED",
        "authentication_tests": [item for item in security_tests if "authentication" in item.lower() or "identity" in item.lower()],
        "authorization_tests": [item for item in security_tests if "authorization" in item.lower() or "tenant" in item.lower()],
        "input_validation_tests": [item for item in security_tests if "input" in item.lower() or "injection" in item.lower()],
        "findings": security_findings,
        "simulated_security_status": "BLOCKED_BY_UNCONFIGURED_SECURITY_ADAPTERS",
        "observed_findings": None,
    }

    performance_design = test_design.get("performance_tests", [])
    performance_report = {
        "execution_status": "NOT_EXECUTED",
        "load_tests": [{"scenario": "Expected steady-state workload", "target_rps": None, "target_p95_ms": None,
                        "precondition": "Service owner must provide workload and latency SLOs."}],
        "stress_tests": [{"scenario": "Increase concurrency to agreed saturation boundary", "pass_criteria": "Graceful degradation and bounded resource use"}],
        "volume_tests": [{"scenario": "Exercise expected data volume and retention window", "pass_criteria": "Approved query and storage SLOs are met"}],
        "planned_performance_scenarios": performance_design,
        "performance_forecast": {"latency_ms": None, "throughput_rps": None, "resource_utilization_percent": None,
                                 "status": "UNAVAILABLE_NO_BASELINE_OR_EXECUTION",
                                 "basis": "No workload profile, environment, SLO, or benchmark evidence supplied."},
    }

    uat_scenarios = []
    for index, story in enumerate(stories, start=1):
        uat_scenarios.append({
            "scenario_id": f"UAT-{index:03d}", "story_id": story.get("story_id"),
            "business_scenario": story.get("description", story.get("title", "Review planned user outcome")),
            "acceptance_criteria": story.get("acceptance_criteria", []),
            "reviewer": "Business owner or delegated product reviewer",
            "status": "PLANNED_NOT_EXECUTED",
        })
    uat_report = {
        "execution_status": "NOT_EXECUTED",
        "business_scenarios": uat_scenarios,
        "acceptance_criteria_count": sum(len(item["acceptance_criteria"]) for item in uat_scenarios),
        "passed": 0, "failed": 0, "pending": len(uat_scenarios),
        "observed_acceptance_rate_percent": None,
    }

    defects = [
        {"defect_id": "DEF-SIM-01", "title": "Authentication integration remains unavailable", "severity": "Critical", "priority": "P1",
         "expected": True, "source": "Generated security adapter is fail-closed placeholder",
         "remediation": "Implement verified identity integration and negative authorization tests before considering release."},
        {"defect_id": "DEF-SIM-02", "title": "Persistence behavior is not implemented", "severity": "High", "priority": "P1",
         "expected": True, "source": "Generated repository raises until an approved adapter is supplied",
         "remediation": "Implement tenant-scoped persistence, transactions, and audit integration; then run integration tests."},
    ]
    defect_report = {"mode": "EXPECTED_DEFECTS_NOT_OBSERVED_DEFECTS", "expected_defects": defects,
                     "observed_defects": None, "severity_counts": {"Critical": 1, "High": 1}}

    coverage_points = sum(planned_categories.values())
    simulated_pass_rate = unit_test_report["simulated_pass_rate_percent"] or 0
    quality_score = round(coverage_percent * 0.4 + simulated_pass_rate * 0.2
                          + (100 if integration_scenarios else 0) * 0.1
                          + (0 if security_findings else 100) * 0.2
                          + (100 if uat_scenarios else 0) * 0.1, 1)
    blockers = [
        "Test execution status is NOT EXECUTED; no observed pass/failure or coverage results exist.",
        "Identity and tenant-scoped persistence adapters are unconfigured in generated templates.",
        "Performance baselines and service-level objectives are not supplied.",
        "UAT scenarios have not been accepted or executed by business reviewers.",
    ]
    release_assessment = {
        "status": "NOT READY",
        "simulated_status": "NOT READY",
        "simulated_quality_score": quality_score,
        "observed_quality_score": None,
        "blockers": blockers,
        "release_authorized": False,
        "basis": "Simulated design quality only. READY is impossible until real test evidence and independent release approvals are recorded.",
    }
    quality_dashboard = {
        "design_coverage_percent": coverage_percent,
        "simulated_code_coverage_forecast_percent": unit_test_report["coverage_forecast_percent"],
        "observed_code_coverage_percent": None,
        "risk_status": "HIGH",
        "quality_score_simulated": quality_score,
        "quality_score_observed": None,
        "readiness": "NOT READY",
        "execution_status": "NOT_EXECUTED",
    }
    test_execution_package = {
        "unit_test_report": unit_test_report, "integration_report": integration_report,
        "security_report": security_report, "performance_report": performance_report,
        "uat_report": uat_report, "defect_report": defect_report,
        "quality_dashboard": quality_dashboard, "release_assessment": release_assessment,
    }
    return {
        "package": "Autonomous Testing Execution Simulation Package",
        "status": "SIMULATION_ONLY",
        "analysis_mode": "ARTIFACT_METADATA_ANALYSIS_NO_TEST_EXECUTION",
        "testing_strategy": strategy,
        "test_coverage_map": coverage_map,
        **test_execution_package,
        "test_execution_package": test_execution_package,
        "controls": {"tests_executed": False, "code_executed": False,
                     "environment_created": False, "ci_cd_executed": False,
                     "deployment_performed": False, "persistence": False,
                     "release_authorized": False},
        "interpretation": "All pass/fail, coverage, performance, and quality values are synthetic planning estimates; no test was run and no observed result is claimed.",
    }