"""Azure hosting strategy and scenario planning; no Azure/network/runtime calls."""

from __future__ import annotations

from typing import Any


HOSTING_OPTIONS = ("App Service", "Container Apps", "AKS", "Functions", "Virtual Machines")


def _option(name: str, *, fit: str, prerequisites: list[str], risks: list[str]) -> dict[str, Any]:
    return {"service": name, "fit": fit, "prerequisites": prerequisites, "risks": risks,
            "provisioned": False, "azure_api_called": False, "recommendation_status": "PROPOSED"}


def _recommend_hosting(architecture: dict[str, Any], deployment: dict[str, Any],
                      build: dict[str, Any]) -> tuple[str | None, str, list[str]]:
    components = architecture.get("components", []) if isinstance(architecture, dict) else []
    component_text = " ".join(str(item.get("name", "")) + " " + str(item.get("responsibility", ""))
                              for item in components if isinstance(item, dict)).lower()
    style = str(architecture.get("architecture_style", "")).lower() if isinstance(architecture, dict) else ""
    languages = build.get("build_blueprint", {}).get("backend_language", [])
    if isinstance(languages, str):
        languages = [languages]
    if not style and not component_text:
        return None, "UNCONFIRMED", ["Architecture style and component topology are not available."]
    has_web = any(term in component_text for term in ("web", "user experience", "browser", "portal", "frontend"))
    has_api = any(term in component_text for term in ("api", "application", "service"))
    event_driven = any(term in component_text for term in ("event", "queue", "serverless", "scheduled", "trigger"))
    orchestrated = any(term in component_text or term in style for term in ("microservice", "orchestration", "kubernetes", "container"))
    legacy_vm = any(term in component_text or term in style for term in ("legacy vm", "windows service", "machine-specific", "host-level"))
    reasons = []
    if legacy_vm:
        return "Virtual Machines", "CONDITIONAL_RECOMMENDATION", ["Blueprint indicates machine-specific or legacy host requirements.", "Confirm OS, patching, hardening, availability, and operations ownership."]
    if event_driven and not has_web:
        return "Functions", "CONDITIONAL_RECOMMENDATION", ["Blueprint indicates event-driven or scheduled components.", "Validate execution duration, trigger model, networking, and state requirements."]
    if orchestrated:
        return "AKS", "CONDITIONAL_RECOMMENDATION", ["Blueprint indicates explicit container orchestration complexity.", "Confirm Kubernetes operating model, cluster ownership, and platform capacity."]
    if has_web and has_api:
        return "App Service", "CONDITIONAL_RECOMMENDATION", ["Blueprint indicates a conventional web/API application shape.", "Compare App Service with Container Apps after deployment and scaling needs are reviewed."]
    if has_api:
        return "Container Apps", "CONDITIONAL_RECOMMENDATION", ["Blueprint indicates an API/service workload with no explicit orchestration requirement.", "Validate container support and operational ownership."]
    reasons.append("Current architecture signals do not distinguish a hosting model.")
    return None, "UNCONFIRMED", reasons


def build_hosting_package(deployment_package: dict[str, Any] | None,
                         technical_delivery_package: dict[str, Any] | None) -> dict[str, Any]:
    """Build hosting blueprints, readiness checks, and scenarios without external calls."""
    deployment = deployment_package if isinstance(deployment_package, dict) else {}
    technical = technical_delivery_package if isinstance(technical_delivery_package, dict) else {}
    project_name = deployment.get("deployment_blueprint", {}).get("project_name", "Proposed Project")
    artifacts = technical.get("artifacts", {}) if isinstance(technical.get("artifacts", {}), dict) else {}
    architecture = artifacts.get("architecture_blueprint", {})
    database_design = artifacts.get("database_blueprint", {})
    security_design = artifacts.get("security_blueprint", {})
    deployment_design = artifacts.get("deployment_blueprint", {})
    build = deployment.get("build_context", {}) if isinstance(deployment.get("build_context"), dict) else {}
    if not build:
        build = deployment.get("build_package", {}) if isinstance(deployment.get("build_package"), dict) else {}
    recommended, recommendation_status, recommendation_reasons = _recommend_hosting(
        architecture if isinstance(architecture, dict) else {}, deployment, build)

    app_service = _option("App Service", fit="Managed web applications and conventional HTTP APIs.",
        prerequisites=["Approved runtime/framework and region", "Identity/network/secret integration design", "Capacity and availability targets"],
        risks=["Platform limits may not match background or custom host requirements", "Plan/network configuration is unverified"])
    container_apps = _option("Container Apps", fit="Containerized APIs, workers, and event-driven services without direct cluster management.",
        prerequisites=["Reviewed container build/package", "Ingress, identity, registry, and environment design", "Scaling and observability requirements"],
        risks=["Container package has not been built", "Registry, networking, and scaling configuration are unspecified"])
    aks = _option("AKS", fit="Workloads needing Kubernetes APIs, complex orchestration, or cluster-level control.",
        prerequisites=["Kubernetes operations owner", "Cluster/network/policy design", "Node, upgrade, identity, and observability plan"],
        risks=["Operational burden is high", "No cluster SRE/capacity evidence supplied"])
    functions = _option("Functions", fit="Event-triggered, short-running, or scheduled functions.",
        prerequisites=["Trigger and execution-duration profile", "State, networking, identity, and retry design", "Consumption/capacity model"],
        risks=["Execution limits and cold-start behavior are unvalidated", "No event/source contract confirmed"])
    virtual_machines = _option("Virtual Machines", fit="Legacy or host-specific workloads requiring OS-level control.",
        prerequisites=["Supported OS/runtime image", "Patch/hardening and endpoint ownership", "Backup, HA, and recovery design"],
        risks=["Highest infrastructure and patching burden", "No machine-specific requirement or operations owner confirmed"])
    options = {item["service"]: item for item in (app_service, container_apps, aks, functions, virtual_machines)}
    if recommended:
        options[recommended]["recommendation_status"] = recommendation_status
        options[recommended]["recommendation_reasons"] = recommendation_reasons
    else:
        for item in options.values():
            item["recommendation_status"] = "NOT_RECOMMENDED_UNCONFIRMED_ARCHITECTURE"
            item["recommendation_reasons"] = recommendation_reasons

    architecture_style = architecture.get("architecture_style") if isinstance(architecture, dict) else None
    hosting_blueprint = {
        "hosting_model": recommended or "UNCONFIRMED",
        "recommendation_status": recommendation_status,
        "recommendation_reasons": recommendation_reasons,
        "architecture_style": architecture_style or "UNCONFIRMED",
        "components": architecture.get("components", []) if isinstance(architecture, dict) else [],
        "region": "UNDECIDED",
        "hosting_selected": False,
        "hosting_provisioned": False,
    }

    environment_names = ("development", "qa", "uat", "production")
    environments = deployment.get("environment_plan", {})
    environment_plan = {}
    for name in environment_names:
        source = environments.get(name, {}) if isinstance(environments, dict) else {}
        environment_plan[name] = {
            "configuration_requirements": list(source.get("configuration_requirements", [])) + [
                "Approved runtime and platform configuration", "Environment-scoped monitoring and alert thresholds"],
            "dependencies": list(source.get("dependencies", [])),
            "security_requirements": list(source.get("security_requirements", [])) + [
                "Managed identity scoped to environment", "Key Vault references only; no secret values in package"],
            "network_requirements": ["Approved ingress/egress and DNS", "Private connectivity where data classification requires it"],
            "environment_created": False,
        }

    has_database = bool(database_design.get("entities")) if isinstance(database_design, dict) else False
    data_hosting_plan = {
        "sql_hosting_plan": {"required": has_database,
            "recommendation": "Managed SQL service option comparison required; engine/region/tier are unconfirmed." if has_database else "No database entities identified in the supplied blueprint.",
            "readiness": "NOT VERIFIED", "provisioned": False},
        "storage_plan": {"purpose": "Store approved artifacts only if the product requires them.",
            "requirements": ["Classification", "Encryption/key ownership", "Lifecycle/retention", "Private access policy"],
            "readiness": "UNCONFIRMED", "provisioned": False},
        "backup_plan": {"requirements": ["Owner-approved RPO/RTO", "Encrypted backup storage", "Retention and access policy", "Restore test evidence"],
            "status": "PLAN_ONLY_NOT_TESTED"},
        "retention_plan": {"requirements": database_design.get("retention_rules", []) if isinstance(database_design, dict) else [],
            "status": "OWNER_REVIEW_REQUIRED", "retention_periods": "UNCONFIRMED"},
        "recovery_plan": {"strategy": "Define point-in-time recovery and cross-region strategy only after data criticality, RPO/RTO, and residency are approved.",
            "failover_tested": False, "recovery_status": "NOT_VERIFIED"},
    }

    security = security_design if isinstance(security_design, dict) else {}
    security_plan = {
        "key_vault_plan": {"purpose": "Store secret references and certificates in an approved vault; no vault is created.",
            "requirements": ["RBAC/least privilege", "Private network access", "Rotation/expiry alerts", "Audit logging"], "provisioned": False},
        "managed_identity_plan": {"requirement": "Prefer workload managed identity; scope per environment and least privilege.",
            "identity_created": False, "role_assignments_created": False},
        "certificate_plan": {"requirements": ["Approved certificate authority", "DNS/domain ownership", "Expiry and rotation monitoring"],
            "certificate_requested": False},
        "secret_management_plan": {"rules": ["Never include secret values in source or plan", "Use environment-scoped Key Vault references", "Rotate and audit access"],
            "secret_values_included": False},
        "source_security_requirements": security.get("authorization_design", []),
        "status": "DESIGN_ONLY_REQUIRES_SECURITY_REVIEW",
    }

    network_plan = {
        "topology": {"pattern": "Proposed segmented application/data topology; address spaces and region are undecided.",
                     "vnet_created": False, "subnets_created": False},
        "private_endpoints": {"candidates": ["SQL/database", "Storage", "Key Vault"],
                              "applicable": "Requires selected Azure services and network review", "created": False},
        "dns_plan": {"requirements": ["Approved domain ownership", "Private DNS zones for private endpoints", "Resolver and split-horizon review"],
                     "records_created": False},
        "firewall_plan": {"requirements": ["Default deny", "Documented inbound/outbound flows", "Egress allowlist and logging"],
                          "rules_created": False},
        "traffic_flow": ["User -> approved ingress/WAF -> application hosting option -> private data/services", "Outbound dependencies -> approved egress controls"],
        "networking_status": "UNCONFIRMED_NO_ENVIRONMENT_DESIGN",
    }

    observability = {
        "monitoring_plan": ["Availability/health indicators by environment", "Actionable alert ownership and escalation", "Service and dependency SLOs"],
        "logging_plan": ["Structured application and platform logs", "Tenant/privacy-safe fields", "Retention and access review"],
        "tracing_plan": ["Distributed trace correlation IDs", "Dependency boundaries and sampling policy", "Sensitive attribute filtering"],
        "metrics_plan": ["Latency, traffic, errors, saturation", "Dependency health", "Security and audit event counters"],
        "workspace_created": False, "instrumentation_performed": False,
    }

    disaster_recovery = {
        "recovery_strategy": "Define recovery tiers after service criticality, data residency, and business continuity review.",
        "backup_strategy": data_hosting_plan["backup_plan"],
        "failover_strategy": "Propose zone/region failover only after architecture, data replication, DNS, and operations ownership are approved.",
        "rto_target": None, "rpo_target": None,
        "targets_basis": "RTO/RPO were not supplied; do not infer service commitments.",
        "failover_configured": False, "recovery_tested": False,
    }

    readiness_checks = {
        "architecture_selected": bool(recommended),
        "build_verified": deployment.get("readiness_report", {}).get("artifact_readiness") == "BUILT_VERIFIED",
        "test_evidence": deployment.get("test_execution_status") == "EXECUTED_ALL_PASSED",
        "identity_verified": False,
        "networking_reviewed": False,
        "data_backup_recovery_defined": False,
        "monitoring_defined": bool(observability["monitoring_plan"]),
        "security_approved": False,
        "cloud_environment_evidence": False,
    }
    passed = sum(readiness_checks.values())
    readiness_score = round(100 * passed / len(readiness_checks), 1)
    blocker_names = [name for name, ready in readiness_checks.items() if not ready]
    readiness_status = "NOT READY" if passed < 4 else "PARTIALLY READY"
    hosting_readiness = {
        "status": readiness_status,
        "readiness_score_percent": readiness_score,
        "checks": readiness_checks,
        "blockers": blocker_names,
        "hosting_provisioned": False,
        "basis": "Planning evidence only; no Azure account, subscription, environment, or deployment evidence was queried.",
    }

    risks = [
        {"risk_id": "HOST-01", "category": "Service Selection", "severity": "MEDIUM" if recommended else "HIGH",
         "description": "Hosting recommendation is a heuristic based on blueprint architecture signals.",
         "mitigation": "Review cost, scale, operational ownership, compliance, and regional needs before selecting a platform."},
        {"risk_id": "HOST-02", "category": "Identity and Secrets", "severity": "HIGH",
         "description": "Identity provider, managed identity bindings, and Key Vault configuration are not verified.",
         "mitigation": "Complete security architecture and identity review before any future provisioning."},
        {"risk_id": "HOST-03", "category": "Networking", "severity": "HIGH",
         "description": "Addressing, DNS, firewall, private endpoint, and egress topology are undecided.",
         "mitigation": "Obtain network owner approval and threat review for all flows."},
        {"risk_id": "HOST-04", "category": "Recovery", "severity": "HIGH",
         "description": "RTO/RPO targets and restore/failover evidence are unavailable.",
         "mitigation": "Set business-approved recovery targets and test recovery in an approved non-production environment."},
        {"risk_id": "HOST-05", "category": "Observability", "severity": "MEDIUM",
         "description": "Monitoring workspace, alert owners, and production SLOs are not configured.",
         "mitigation": "Approve service indicators, retention, alert routing, and on-call ownership."},
    ]
    risk_report = {"risks": risks, "risk_count": len(risks), "highest_severity": "HIGH",
                   "status": "PLANNING_RISKS_NOT_ASSESSED_BY_CLOUD"}

    dashboard = {
        "hosting_readiness": hosting_readiness,
        "security_readiness": "NOT VERIFIED",
        "recovery_readiness": "NOT VERIFIED",
        "monitoring_readiness": "PLAN_DEFINED_NOT_CONFIGURED",
        "recommended_option": recommended,
        "recommendation_status": recommendation_status,
    }
    scenarios = [
        {"scenario": "success", "forecast_outcome": "All approvals, environment, security, monitoring, and recovery gates pass; future deployment may be considered.", "cloud_calls_performed": False, "infrastructure_created": False},
        {"scenario": "failure", "forecast_outcome": "A health/security/data gate fails; promotion is stopped and evidence is preserved.", "cloud_calls_performed": False, "infrastructure_created": False},
        {"scenario": "recovery", "forecast_outcome": "An authorized operator follows the separately tested recovery plan after owner approval.", "cloud_calls_performed": False, "infrastructure_created": False},
        {"scenario": "blocked", "forecast_outcome": "Current package remains blocked by missing identity, network, recovery, security, and environment evidence.", "cloud_calls_performed": False, "infrastructure_created": False},
    ]

    hosting_execution_package = {
        "hosting_blueprint": hosting_blueprint,
        "network_plan": network_plan,
        "security_plan": security_plan,
        "monitoring_plan": observability,
        "recovery_plan": disaster_recovery,
        "readiness_report": hosting_readiness,
        "risk_report": risk_report,
        "executive_summary": f"Hosting for {project_name} is {readiness_status}. Recommended option: {recommended or 'unconfirmed'}. No Azure or infrastructure action was performed.",
    }
    return {
        "package": "Autonomous Hosting Factory Plan",
        "status": "PLANNING_AND_SIMULATION_ONLY",
        "authority": "NONE", "action_allowed": False, "persistence": False,
        "hosting_blueprint": hosting_blueprint,
        "application_hosting": {"recommended_option": recommended,
                                "recommendation_status": recommendation_status,
                                "recommendation_reasons": recommendation_reasons,
                                "options": options},
        "environment_plans": environment_plan,
        "data_hosting_plan": data_hosting_plan,
        "network_plan": network_plan,
        "security_plan": security_plan,
        "monitoring_plan": observability,
        "disaster_recovery_plan": disaster_recovery,
        "recovery_plan": disaster_recovery,
        "hosting_readiness_report": hosting_readiness,
        "hosting_dashboard": dashboard,
        "execution_simulator": {"scenarios": scenarios, "runtime_executed": False,
                                "cloud_calls_performed": False},
        "risk_report": risk_report,
        "executive_summary": hosting_execution_package["executive_summary"],
        "hosting_execution_package": hosting_execution_package,
        "controls": {"azure_api_calls": False, "infrastructure_created": False,
                     "environments_created": False, "secrets_accessed": False,
                     "networking_configured": False, "monitoring_configured": False,
                     "deployment_performed": False, "runtime_started": False,
                     "persistence": False},
    }