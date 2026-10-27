"""Deterministic, recommendation-only workforce factory planning."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.services.project_factory_planner import build_project_delivery_package
from app.services.delivery_factory import build_delivery_execution_package
from app.services.agent_lifecycle_factory import build_agent_lifecycle_package
from app.services.assignment_factory import build_assignment_package
from app.services.testing_execution_factory import build_testing_execution_package
from app.services.code_factory import build_code_package
from app.services.build_factory import build_release_artifact_package
from app.services.deployment_factory import build_deployment_package
from app.services.hosting_factory import build_hosting_package
from app.services.operations_factory import build_operations_package
from app.services.approval_sandbox import build_approval_sandbox_package
from app.services.autonomy_factory import build_autonomy_package
from app.services.autonomous_enterprise import build_autonomous_enterprise_package
from app.services.executive_command_center import build_executive_command_center
from app.services.blueprint_explorer import build_blueprint_explorer


REQUIRED_CERTIFICATIONS = ("Capability", "Safety", "Security", "Governance")

ROLE_CATALOG: dict[str, dict[str, Any]] = {
    "business_analyst": {
        "role_name": "AI Business Analyst", "team": "Product and Analysis", "experience": "3+ years in business or systems analysis",
        "responsibilities": ["Clarify business outcomes", "Decompose requirements and acceptance criteria", "Maintain traceability and assumptions"],
        "skills": [("RequirementAnalysis", "Domain", 5), ("ProcessMapping", "Domain", 4), ("DataLiteracy", "Technical", 3)],
        "tools": ["Requirements management", "Process modeling"], "certifications": ["Capability", "Safety", "Governance"],
    },
    "solution_architect": {
        "role_name": "AI Solution Architect", "team": "Architecture and Engineering", "experience": "5+ years in solution or enterprise architecture",
        "responsibilities": ["Define target architecture and interfaces", "Review non-functional requirements", "Identify security and delivery risks"],
        "skills": [("SolutionArchitecture", "Technical", 5), ("APIEngineering", "Technical", 4), ("SecurityArchitecture", "Security", 4)],
        "tools": ["Architecture repository", "API design tooling"], "certifications": ["Capability", "Safety", "Security", "Governance"],
    },
    "data_analyst": {
        "role_name": "AI Data Analyst", "team": "Data and AI", "experience": "3+ years in analytics, data quality, or BI",
        "responsibilities": ["Profile and validate data", "Define metrics and analytical outputs", "Document lineage and limitations"],
        "skills": [("DataAnalysis", "Domain", 5), ("Python", "Technical", 4), ("DataGovernance", "Governance", 4)],
        "tools": ["Python", "SQL", "Business intelligence platform"], "certifications": ["Capability", "Safety", "Governance"],
    },
    "backend_developer": {
        "role_name": "AI Backend Developer", "team": "Architecture and Engineering", "experience": "3+ years in backend/API development",
        "responsibilities": ["Implement service endpoints", "Add validation, authorization, and tests", "Maintain API and data contracts"],
        "skills": [("BackendDevelopment", "Technical", 5), ("APIEngineering", "Technical", 5), ("SecureCoding", "Security", 4)],
        "tools": ["Version control", "API test tooling", "Automated test runner"], "certifications": ["Capability", "Safety", "Security", "Governance"],
    },
    "frontend_developer": {
        "role_name": "AI Frontend Developer", "team": "Architecture and Engineering", "experience": "3+ years in accessible web application development",
        "responsibilities": ["Implement responsive user workflows", "Apply accessibility and input-safety practices", "Test browser behavior and API integration"],
        "skills": [("FrontendDevelopment", "Technical", 5), ("Accessibility", "Domain", 4), ("ClientSecurity", "Security", 4)],
        "tools": ["Browser developer tools", "Version control", "Accessibility test tooling"], "certifications": ["Capability", "Safety", "Security", "Governance"],
    },
    "qa_engineer": {
        "role_name": "AI QA Engineer", "team": "Quality and Assurance", "experience": "3+ years in software quality engineering",
        "responsibilities": ["Create risk-based test coverage", "Validate acceptance criteria and regressions", "Report reproducible defects"],
        "skills": [("QualityTesting", "Technical", 5), ("TestAutomation", "Technical", 4), ("RiskAnalysis", "Governance", 3)],
        "tools": ["Test management", "Automated test runner", "Defect tracking"], "certifications": ["Capability", "Safety", "Security", "Governance"],
    },
    "security_engineer": {
        "role_name": "AI Security Engineer", "team": "Quality and Assurance", "experience": "4+ years in application or cloud security",
        "responsibilities": ["Review threat model and access boundaries", "Validate secure configuration and negative tests", "Track findings to verified remediation"],
        "skills": [("SecurityReview", "Security", 5), ("ThreatModeling", "Security", 5), ("GovernanceControls", "Governance", 4)],
        "tools": ["Threat modeling", "Static analysis", "Security test tooling"], "certifications": ["Capability", "Safety", "Security", "Governance"],
    },
    "devops_engineer": {
        "role_name": "AI DevOps Engineer", "team": "Platform and Operations", "experience": "4+ years in cloud platform or delivery engineering",
        "responsibilities": ["Define deployment and observability plans", "Validate rollback and environment controls", "Maintain infrastructure automation"],
        "skills": [("CloudEngineering", "Technical", 5), ("CI_CD", "Technical", 4), ("OperationalReadiness", "Governance", 4)],
        "tools": ["Cloud platform", "CI/CD", "Infrastructure as code", "Monitoring"], "certifications": ["Capability", "Safety", "Security", "Governance"],
    },
    "project_manager": {
        "role_name": "AI Project Manager", "team": "Delivery Leadership", "experience": "4+ years in delivery or program management",
        "responsibilities": ["Maintain scope, dependencies, and delivery plan", "Track risks, decisions, and changes", "Escalate blocked work to accountable owners"],
        "skills": [("ProjectPlanning", "Domain", 5), ("RiskManagement", "Governance", 4), ("StakeholderCommunication", "Domain", 4)],
        "tools": ["Project planning", "Risk register", "Decision log"], "certifications": ["Capability", "Safety", "Governance"],
    },
    "product_owner": {
        "role_name": "AI Product Owner", "team": "Product and Analysis", "experience": "4+ years in product ownership or product management",
        "responsibilities": ["Prioritize outcomes and acceptance criteria", "Resolve product trade-offs with accountable stakeholders", "Validate delivered value against approved scope"],
        "skills": [("ProductManagement", "Domain", 5), ("ValuePrioritization", "Domain", 4), ("GovernanceControls", "Governance", 3)],
        "tools": ["Product roadmap", "Backlog management", "Analytics"], "certifications": ["Capability", "Safety", "Governance"],
    },
}

TECHNOLOGY_SKILLS = {
    ".net": ("DotNetDevelopment", "Backend implementation and secure API patterns"),
    "angular": ("AngularDevelopment", "Component architecture, accessibility, and client security"),
    "python": ("PythonDevelopment", "Python implementation, testing, and dependency hygiene"),
    "azure ai": ("AzureAIIntegration", "Responsible AI integration, evaluation, and data handling"),
    "copilot studio": ("CopilotStudioDesign", "Conversation design, connectors, and governance"),
    "react": ("ReactDevelopment", "React component design, accessibility, and client security"),
    "openai": ("OpenAIIntegration", "Responsible provider integration, evaluation, and data handling"),
    "anthropic": ("AnthropicIntegration", "Responsible provider integration, evaluation, and data handling"),
}


def _technology_key(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {"dotnet": ".net", "asp.net": ".net", "azure ai services": "azure ai"}
    return aliases.get(normalized, normalized)


def infer_technology_changes(text: str) -> list[str]:
    """Detect only technologies in the bounded, supported technology catalog."""
    normalized = text.lower()
    return [display for key, display in (
        (".net", ".NET"), ("angular", "Angular"), ("python", "Python"),
        ("react", "React"), ("azure ai", "Azure AI"), ("copilot studio", "Copilot Studio"),
        ("openai", "OpenAI"), ("anthropic", "Anthropic"),
    ) if key in normalized]


def _has_any(text: str, *terms: str) -> bool:
    for term in terms:
        prefix = r"(?<!\w)" if term and term[0].isalnum() else ""
        suffix = r"(?!\w)" if term and term[-1].isalnum() else ""
        if re.search(f"{prefix}{re.escape(term)}{suffix}", text, flags=re.IGNORECASE):
            return True
    return False


def _selected_roles(text: str) -> list[str]:
    selected = {"business_analyst", "solution_architect", "qa_engineer", "project_manager", "product_owner"}
    if _has_any(text, "data", "analytics", "business intelligence", "reporting", "python"):
        selected.add("data_analyst")
    if _has_any(text, "api", "backend", "service", ".net", "python"):
        selected.add("backend_developer")
    if _has_any(text, "frontend", "front-end", "web", "website", "portal", "angular", "ui"):
        selected.add("frontend_developer")
    if _has_any(text, "security", "secure", "privacy", "authentication", "authorization"):
        selected.add("security_engineer")
    if _has_any(text, "cloud", "azure", "deploy", "infrastructure", "ci/cd", "devops"):
        selected.add("devops_engineer")
    return [key for key in ROLE_CATALOG if key in selected]


def _certification_framework() -> dict[str, Any]:
    tiers = {
        "Bronze": {"scope": "Supervised role fundamentals", "training": ["Role charter", "Safety and governance fundamentals"], "evaluations": ["Knowledge check", "Sandbox task review"]},
        "Silver": {"scope": "Bounded independent task delivery", "training": ["Role-specific workflow", "Security and evidence handling"], "evaluations": ["Capability evaluation", "Safety evaluation", "Reviewed work sample"]},
        "Gold": {"scope": "Complex work with peer review", "training": ["Advanced role practice", "Risk and escalation scenarios"], "evaluations": ["Capability evaluation", "Security evaluation", "Governance evaluation", "Independent portfolio review"]},
        "Platinum": {"scope": "Lead and mentor within explicitly approved boundaries", "training": ["Leadership, auditability, and incident exercises"], "evaluations": ["All current evaluations", "Independent panel review", "Periodic renewal"]},
    }
    return {"tiers": tiers, "required_evaluations": list(REQUIRED_CERTIFICATIONS),
            "issued_automatically": False, "decision_authority": "Authorized independent certification workflow"}


def _build_technical_delivery_package(
    *, title: str, description: str, domain: str | None,
    roles: list[dict[str, Any]], technologies: list[str], priority: str | None,
) -> dict[str, Any]:
    source = f"{title} {description} {' '.join(technologies)}".lower()
    data_product = _has_any(source, "data", "analytics", "report", "dashboard", "database", "warehouse")
    workflow_app = _has_any(source, "portal", "web", "website", "frontend", "front-end", "application", "app", "user interface", "ui")
    integration = _has_any(source, "integration", "integrate", "integrated", "third-party", "external", "api", "connector", "payment", "identity provider")
    sensitive = _has_any(source, "personal", "customer", "employee", "patient", "financial", "payment", "health", "sensitive")
    regulated = _has_any(source, "regulated", "compliance", "health", "financial", "payment", "gdpr", "hipaa")
    cloud = _has_any(source, "cloud", "azure", "aws", "hosting", "deploy", "infrastructure")

    business_domain = domain or (
        "Healthcare" if _has_any(source, "health", "patient", "clinical") else
        "Finance" if _has_any(source, "finance", "financial", "payment", "bank") else
        "Human Resources" if _has_any(source, "employee", "human resources", "onboarding", "workforce") else
        "Data and Analytics" if data_product else "General Business"
    )
    solution_type = ("Web application with API and data services" if workflow_app and data_product else
                    "Web application with API services" if workflow_app else
                    "Data and analytics solution" if data_product else
                    "Integration/API solution" if integration else "Business workflow solution")
    complexity = "High" if integration and (data_product or sensitive) else "Medium" if (workflow_app or integration or data_product) else "Low"
    assessed_priority = priority or (
        "High" if _has_any(source, "urgent", "high priority", "critical", "as soon as possible") else "Medium"
    )

    executive = {
        "business_domain": business_domain, "solution_type": solution_type,
        "complexity": complexity, "priority": assessed_priority,
        "priority_basis": "Requester-selected priority" if priority else "Keyword heuristic; confirm with requester.",
        "dependencies": [
            "Confirm business owner, users, and measurable acceptance outcomes",
            "Confirm source systems, data ownership, and integration access",
            "Approve security, privacy, retention, and operational requirements",
        ],
        "risks": [
            {"risk": "Unvalidated requirements or assumptions", "level": "Medium", "mitigation": "Review scope and acceptance criteria with accountable stakeholders."},
            *([{"risk": "Sensitive or regulated data may be in scope", "level": "High", "mitigation": "Complete privacy, data classification, residency, and retention review before design approval."}] if sensitive or regulated else []),
            *([{"risk": "External integrations introduce availability and data-sharing dependencies", "level": "Medium", "mitigation": "Confirm contracts, authentication, rate limits, failure modes, and data-processing terms."}] if integration else []),
        ],
        "executive_assessment": f"A {complexity.lower()}-complexity {solution_type.lower()} is proposed for the {business_domain} domain. Validate scope, dependencies, and risks before authorization.",
        "basis": "Deterministic keyword rules over requester-provided text; not an AI model assessment or a validated business decision.",
    }

    architecture = {
        "architecture_style": "Modular client-server application; validate modular monolith versus distributed services against scale, availability, and team constraints.",
        "components": [
            {"name": "User experience", "responsibility": "Accessible user workflows and status presentation."},
            {"name": "Application/API layer", "responsibility": "Authentication, authorization, validation, and business use cases."},
            {"name": "Domain services", "responsibility": "Requirement-specific rules and integration orchestration."},
            {"name": "Persistence layer", "responsibility": "Transactional records, query boundaries, and retention controls."},
            {"name": "Observability and audit", "responsibility": "Correlated security events, health, metrics, and operational evidence."},
        ],
        "services": ["Identity/session boundary", "Core business service", "API facade", "Persistence adapter", "Audit/observability service"],
        "interfaces": ["Browser-to-API HTTPS interface", "Service-to-database interface", "Versioned external integration interface where required"],
        "integration_points": technologies or (["External systems to be identified and approved"] if integration else []),
        "backend_design": {
            "service_boundaries": ["Request/API boundary", "Domain application services", "Persistence adapters", "Integration adapters where needed"],
            "responsibilities": ["Validate inputs and enforce server-side authorization", "Keep transaction boundaries explicit", "Emit correlated audit/operational events", "Return stable versioned response and error contracts"],
            "failure_handling": ["Bound timeouts and retries", "Use idempotency for retried writes", "Fail closed when authorization or required evidence is unavailable"],
        },
        "proposed": True,
    }

    entities = [
        {"name": "User", "purpose": "Authenticated principal and access subject."},
        {"name": "Requirement", "purpose": "Submitted business need and lifecycle status."},
        {"name": "Project", "purpose": "Approved delivery scope derived from a requirement."},
        {"name": "Task", "purpose": "Traceable unit of planned delivery work."},
        {"name": "AuditEvent", "purpose": "Append-oriented record of sensitive decisions and transitions."},
    ]
    if data_product:
        entities.extend([
            {"name": "DataSource", "purpose": "Registered source and ownership/classification metadata."},
            {"name": "MetricOrDataset", "purpose": "Governed analytical definition and lineage reference."},
        ])
    if integration:
        entities.append({"name": "IntegrationConnection", "purpose": "Non-secret reference to approved integration configuration and status."})
    relationships = ["User 1-to-many Requirement (creator/owner)", "Requirement 1-to-zero-or-one Project", "Project 1-to-many Task", "User/actor 1-to-many AuditEvent"]
    if data_product:
        relationships.append("DataSource 1-to-many MetricOrDataset")
    if integration:
        relationships.append("Project 1-to-many IntegrationConnection references")
    database = {
        "entities": entities,
        "tables": [{"table": re.sub(r"(?<!^)(?=[A-Z])", "_", item["name"]).lower(), "entity": item["name"]} for item in entities],
        "relationships": relationships,
        "keys": ["Use immutable surrogate primary keys; enforce foreign keys for declared relationships; add tenant/company key to every business row when multi-tenant."],
        "indexes": ["Index foreign keys and lifecycle/status filters", "Add unique constraints for idempotency/business keys only after domain rules are confirmed"],
        "retention_rules": ["Classify data and define statutory/business retention with the data owner", "Retain audit records under an approved immutable retention policy", "Do not store secrets or unnecessary sensitive payloads"],
        "assumptions": ["Entity names and relationships are proposals, not existing schema claims.", "Data classification, volume, tenancy, and retention periods require owner review."],
        "proposed": True,
    }

    api_endpoints = [
        {"method": "POST", "path": "/api/v1/requirements", "purpose": "Submit a validated business requirement", "request_model": "RequirementCreate", "response_model": "RequirementSummary"},
        {"method": "GET", "path": "/api/v1/requirements/{requirement_id}", "purpose": "Read an authorized requirement", "request_model": "RequirementId", "response_model": "RequirementDetail"},
        {"method": "GET", "path": "/api/v1/projects/{project_id}", "purpose": "Read authorized project status and task summary", "request_model": "ProjectId", "response_model": "ProjectSummary"},
    ]
    if integration:
        api_endpoints.append({"method": "POST", "path": "/api/v1/integrations/{integration_id}/events", "purpose": "Receive validated integration events", "request_model": "IntegrationEvent", "response_model": "AcceptedOperation"})
    api_catalog = {
        "versioning": "Prefix public contracts with /api/v1; establish compatibility and deprecation policy.",
        "endpoints": api_endpoints,
        "contract_requirements": ["Schema validation and bounded request sizes", "Consistent error envelope and correlation ID", "Idempotency for retried state-changing requests", "Pagination/filter limits for collection reads"],
        "common_request_model": {"correlation_id": "UUID", "idempotency_key": "Optional opaque key for retried writes", "payload": "Endpoint-specific validated model"},
        "request_models": {"RequirementCreate": ["title: string", "description: string", "priority: Low|Medium|High|Critical"]},
        "response_models": {"RequirementSummary": ["requirement_id: UUID", "title: string", "status: lifecycle state", "created_at_utc: ISO-8601", "correlation_id: UUID"],
                    "ErrorResponse": ["code: stable error code", "detail: safe message", "correlation_id: UUID"]},
        "common_response_model": {"resource_id": "UUID", "status": "Lifecycle status", "created_at_utc": "ISO-8601 timestamp", "correlation_id": "UUID"},
        "proposed": True,
    }

    screens = [
        {"name": "Requirement intake", "forms": ["Problem, outcome, users, systems, constraints, priority"], "journey": "Draft, review, submit, track"},
        {"name": "Project workspace", "forms": ["Task updates subject to authorization"], "journey": "Review scope, tasks, dependencies, risks, and status"},
        {"name": "Operations dashboard", "forms": [], "journey": "Review delivery health, alerts, and audit-linked status"},
    ]
    if data_product:
        screens.append({"name": "Analytics dashboard", "forms": ["Date range and approved dimension filters"], "journey": "Explore authorized metrics with source and freshness context"})
    dashboards = [{"name": "Operations dashboard", "metrics": ["Project/task status", "Open risks and blockers", "Audit-linked operational health"]}]
    if data_product:
        dashboards.append({"name": "Analytics dashboard", "metrics": ["Approved business metrics", "Data freshness", "Source lineage"]})
    ui = {"screens": screens, "forms": [form for screen in screens for form in screen["forms"]],
          "dashboards": dashboards, "navigation": ["Home", "Requirements", "Projects", "Operations", "Profile"],
          "user_journeys": ["Submit and track a requirement", "Review approved project scope", "Monitor task and operational status"],
          "accessibility": ["Keyboard-operable controls", "Semantic labels and error announcements", "Responsive layout and contrast verification"],
          "proposed": True}

    security = {
        "authentication_design": "Authentication: use the approved identity provider, secure session/token validation, expiry, revocation, and step-up for sensitive actions.",
        "authorization_design": ["Enforce role and resource-level authorization server-side on every endpoint.", "Scope reads and writes to the authenticated user's organization/tenant and permitted resources.", "Separate visibility from decision authority; deny by default."],
        "audit_requirements": ["Record actor, action, resource, outcome, timestamp, and correlation ID for sensitive transitions.", "Protect audit integrity and restrict access; never log credentials or raw secrets."],
        "data_classification": "Provisional: treat requirement content as confidential until the data owner classifies it; elevate to sensitive when personal, financial, health, or regulated data is detected.",
        "threat_review": ["Abuse of authorization boundaries", "Injection and unsafe input handling", "Sensitive data disclosure", "Credential/secret exposure", "Integration spoofing and replay"],
        "proposed": True,
    }
    testing = {
        "unit_tests": ["Requirement validation and domain rules", "Authorization policy decisions", "Data transformation and error mapping"],
        "integration_tests": ["API-to-database transactions", "Identity and tenant scoping", "Integration timeout/retry and idempotency" if integration else "API contract and persistence behavior"],
        "uat_scenarios": ["Requester submits and tracks requirement", "Authorized reviewer validates project scope", "Unauthorized cross-user/tenant read is denied"],
        "security_tests": ["Negative role/resource authorization tests", "Input validation and injection tests", "Secret and sensitive-data logging checks"],
        "performance_tests": ["Baseline latency and throughput under expected workload", "Concurrency and database query saturation", "Degraded dependency and recovery behavior"],
        "acceptance_gates": ["All critical tests pass", "No unresolved critical security findings", "Traceable requirements and approved evidence"],
        "proposed": True,
    }
    deployment = {
        "hosting_architecture": "Proposed managed application hosting behind TLS and a controlled ingress; select vendor, region, and topology after security and capacity review." if cloud else "Hosting provider and topology are undecided; compare managed hosting options after security, availability, and capacity requirements are confirmed.",
        "database_hosting": "Managed relational database with private connectivity, encryption, backups, and least-privilege access; engine/region are undecided.",
        "storage_design": "Use managed object storage only if approved artifacts are required; encrypt, classify, and apply retention/lifecycle rules.",
        "monitoring_design": ["Application health and dependency telemetry", "Security/audit alerting", "Service-level indicators and actionable on-call routing"],
        "backup_strategy": ["Set recovery-point and recovery-time objectives with the service owner", "Encrypt and access-control backups", "Test restore and document evidence before production approval"],
        "deployment_status": "DESIGN_ONLY_NO_INFRASTRUCTURE_CREATED",
        "proposed": True,
    }

    role_names = {role["role_name"] for role in roles}
    requested_alignments = [
        ("Architect", "AI Solution Architect", "Architecture and interface decisions"),
        ("Developers", "AI Backend Developer", "Service and API design"),
        ("Frontend", "AI Frontend Developer", "User experience design"),
        ("QA", "AI QA Engineer", "Verification and UAT design"),
        ("Security", "AI Security Engineer", "Threat, authorization, and audit design"),
        ("DevOps", "AI DevOps Engineer", "Hosting, monitoring, backup, and release design"),
    ]
    alignment = []
    for discipline, role_name, contribution in requested_alignments:
        needed = (discipline in {"Architect", "Developers", "QA", "Security", "DevOps"}
                  or discipline == "Frontend" and workflow_app
                  )
        if needed:
            alignment.append({"discipline": discipline, "proposed_role": role_name,
                              "factory_role_available": role_name in role_names,
                              "needed_for_scope": (discipline != "Frontend" or workflow_app),
                              "contribution": contribution, "headcount": 1 if (discipline != "Frontend" or workflow_app) else 0,
                              "status": "PROPOSED_NOT_ASSIGNED"})
    workforce = {
        "required_agents": len(alignment), "role_alignment": alignment,
        "available_agents": "Requires authenticated live roster assessment",
        "skills_gap": "Requires role-specific live skill evidence comparison",
        "capacity_gap": "Requires current workload and availability evidence",
        "assignment_status": "NOT_ASSIGNED",
        "note": "Role demand is a planning estimate; use Agent Factory previews and existing governed assignment workflows for candidate assessment.",
    }

    artifacts = {
        "executive_assessment": executive,
        "architecture_blueprint": architecture,
        "database_blueprint": database,
        "api_catalog": api_catalog,
        "ui_blueprint": ui,
        "security_blueprint": security,
        "testing_blueprint": testing,
        "deployment_blueprint": deployment,
        "workforce_plan": workforce,
    }
    return {
        "workflow": ["Requirement", "AI CEO Analysis", "Architecture", "Database Design", "Backend Design",
                     "Frontend Design", "API Design", "Security Design", "Testing Design", "Deployment Design"],
        "status": "PLANNING_ONLY",
        "generated_from": {"title": title, "domain_input": domain, "technology_inputs": technologies},
        "analysis_mode": "DETERMINISTIC_HEURISTIC_DRAFT_REQUIRES_HUMAN_VALIDATION",
        "artifacts": artifacts,
        "open_questions": ["Confirm business owner, users, scope, and acceptance criteria.",
                           "Confirm data classification, tenancy, residency, retention, and availability targets.",
                           "Confirm preferred technology stack, integration contracts, and hosting region."],
        "controls": {"code_generated": False, "infrastructure_created": False, "deployed": False,
                     "runtime_started": False, "database_schema_created": False,
                     "api_implemented": False, "agents_assigned": False,
                     "approval_authority_granted": False, "persistence": False},
    }


def build_factory_blueprint(*, title: str, description: str, technology_changes: list[str] | None = None,
                            domain: str | None = None, priority: str | None = None) -> dict[str, Any]:
    """Produce a deterministic workforce blueprint; it does not create lifecycle records."""
    technologies = list(dict.fromkeys(item.strip() for item in (technology_changes or []) if item.strip()))
    source_text = " ".join([title, description, *technologies]).lower()
    role_keys = _selected_roles(source_text)
    roles = []
    skills_by_name: dict[str, dict[str, Any]] = {}
    teams: dict[str, list[str]] = defaultdict(list)
    tools: set[str] = set()
    for role_key in role_keys:
        profile = ROLE_CATALOG[role_key]
        tools.update(profile["tools"])
        teams[profile["team"]].append(profile["role_name"])
        skill_items = [{"name": name, "category": category, "priority": priority}
                       for name, category, priority in profile["skills"]]
        for skill in skill_items:
            entry = skills_by_name.setdefault(skill["name"], {**skill, "roles": []})
            entry["priority"] = max(entry["priority"], skill["priority"])
            entry["roles"].append(profile["role_name"])
        roles.append({
            "role_code": role_key.upper(), "role_name": profile["role_name"],
            "team": profile["team"], "agent_type": "Specialist",
            "required_certifications": profile["certifications"],
            "required_skills": skill_items, "required_tools": profile["tools"],
            "required_integrations": technologies,
            "job_description": {
                "role_name": profile["role_name"],
                "purpose": f"Deliver the {title.strip()} outcome within approved scope and governance controls.",
                "responsibilities": profile["responsibilities"],
                "required_skills": skill_items,
                "required_experience": profile["experience"],
                "success_metrics": ["Acceptance criteria met", "Evidence and traceability complete", "No unresolved critical control findings"],
                "kpis": ["First-pass acceptance rate", "On-time milestone rate", "Verified quality and governance findings"],
                "certifications": profile["certifications"],
                "reporting_structure": "Reports to the authorized project delivery lead; escalates governance decisions to accountable human owners.",
                "tools": profile["tools"],
            },
        })

    technology_updates = []
    for technology in technologies:
        key = _technology_key(technology)
        skill_name, training = TECHNOLOGY_SKILLS.get(key, (f"{technology}Proficiency", "Validate approved training and evaluation criteria with the skill owner."))
        skills_by_name[skill_name] = {"name": skill_name, "category": "AI" if "ai" in key or "copilot" in key else "Technical",
                                      "priority": 4, "roles": [role["role_name"] for role in roles]}
        tools.add(technology)
        technology_updates.append({
            "technology": technology, "jd_updates": [f"Add {technology} to relevant role tools and integration context."],
            "skill_matrix_updates": [skill_name],
            "certification_updates": [f"Add a reviewed {technology} evaluation to the applicable certification path."],
            "upskilling_plan": {"training": training, "practice": f"Complete a sandbox exercise using {technology}.",
                                "verification": "Independent evidence-backed assessment; no certification is issued by this plan."},
        })

    skill_matrix = sorted(skills_by_name.values(), key=lambda item: (-item["priority"], item["category"], item["name"]))
    assignment_weights = {"skill_match": 35, "certification_match": 25, "availability": 15,
                          "capacity": 15, "project_experience": 5, "performance": 5}
    technical_delivery_package = _build_technical_delivery_package(
        title=title.strip(), description=description.strip(), domain=domain,
        roles=roles, technologies=technologies, priority=priority,
    )
    project_delivery_package = build_project_delivery_package(
        title=title.strip(), description=description.strip(), priority=priority,
        technical_delivery_package=technical_delivery_package,
    )
    delivery_execution_package = build_delivery_execution_package(project_delivery_package)
    testing_execution_package = build_testing_execution_package(
        technical_delivery_package, project_delivery_package, delivery_execution_package, None,
    )
    build_code_metadata = build_code_package(technical_delivery_package, "python")
    build_execution_package = build_release_artifact_package(
        build_code_metadata, testing_execution_package, project_delivery_package,
    )
    deployment_execution_package = build_deployment_package(
        build_execution_package, testing_execution_package, project_delivery_package,
    )
    hosting_execution_package = build_hosting_package(
        deployment_execution_package, technical_delivery_package,
    )
    operations_execution_package = build_operations_package(
        hosting_execution_package, delivery_execution_package,
    )
    blueprint = {
        "framework": "Autonomous Agent Factory Blueprint",
        "analysis_mode": "DETERMINISTIC_RULE_BASED_NOT_AI_INFERENCE",
        "requirement": {"title": title.strip(), "description": description.strip(), "domain": domain,
                        "technology_changes": technologies},
        "teams": [{"team": name, "roles": role_names} for name, role_names in sorted(teams.items())],
        "roles": roles,
        "skill_matrix": skill_matrix,
        "certification_framework": _certification_framework(),
        "required_tools": sorted(tools),
        "required_integrations": technologies,
        "upskilling_plan": {"technology_updates": technology_updates,
                            "automatic_profile_update": False,
                            "note": "This blueprint recommends profile updates; approved role profiles are not mutated."},
        "workforce_plan": {"required_agents": len(roles), "available_agents": "Not assessed by blueprint endpoint",
                            "skills_gap": "Requires live roster assessment", "capacity_gap": "Requires live roster assessment",
                            "staffing_recommendation": "Review role demand against the read-only workforce dashboard."},
        "technical_delivery_package": technical_delivery_package,
        "project_delivery_package": project_delivery_package,
        "delivery_execution_package": delivery_execution_package,
        "testing_execution_package": testing_execution_package,
        "build_execution_package": build_execution_package,
        "code_execution_package": build_code_metadata,
        "deployment_execution_package": deployment_execution_package,
        "hosting_execution_package": hosting_execution_package,
        "operations_execution_package": operations_execution_package,
        "assignment_framework": {"weights_percent": assignment_weights,
            "hard_gates": ["active status", "all required skills at threshold", "all current required certifications", "available task capacity"],
            "assignment_performed": False, "reasoning": "Rank candidates only from server-verified skill, evaluation, capacity, experience, and performance evidence."},
        "replacement_framework": {"trigger": "Agent becomes unavailable or fails an assignment readiness gate",
            "selection": "Re-rank eligible candidates using the assignment framework and preserve task-specific approvals.",
            "replacement_performed": False},
        "retirement_framework": {"signals": ["documented obsolescence", "no recent eligible use", "expired or withdrawn skills/certifications"],
            "required_checks": ["active assignments and executions", "credential and permission revocation plan", "data retention and audit review", "owner approval"],
            "retirement_performed": False},
        "workforce_director": {"role": "AI Workforce Director", "scope": ["prepare role blueprints", "monitor readiness and capacity", "recommend skill development", "rank assignment/replacement candidates", "flag retirement review candidates"],
            "authority": "NONE", "lifecycle_mutations_enabled": False},
        "lifecycle_actions": {"mode": "BLUEPRINT_ONLY", "agent_records_created": False,
            "agents_assigned": False, "agents_activated": False, "certifications_issued": False,
            "agents_retired": False, "persistence": False},
        "readiness_percent": None,
        "readiness_status": "Unavailable until live workforce and evidence data are assessed",
    }
    blueprint["agent_lifecycle_package"] = build_agent_lifecycle_package(blueprint)
    blueprint["assignment_recommendation_package"] = build_assignment_package(blueprint)
    blueprint["approval_sandbox_package"] = build_approval_sandbox_package(blueprint)
    blueprint["autonomy_execution_package"] = build_autonomy_package(blueprint)
    blueprint["autonomous_enterprise_package"] = build_autonomous_enterprise_package(blueprint)
    blueprint["executive_command_center"] = build_executive_command_center(blueprint)
    blueprint["blueprint_explorer"] = build_blueprint_explorer(blueprint)
    return blueprint


def rank_assignment_candidates(candidates: list[dict[str, Any]], required_skills: dict[str, int],
                              required_certifications: tuple[str, ...] = REQUIRED_CERTIFICATIONS) -> list[dict[str, Any]]:
    """Score server-sourced candidates while preserving hard eligibility gates."""
    weights = {"skill_match": 35, "certification_match": 25, "availability": 15,
               "capacity": 15, "project_experience": 5, "performance": 5}
    ranked = []
    for candidate in candidates:
        skills = candidate.get("skills", {})
        skill_score = round(100 * sum(min(max(float(skills.get(name, 0)), 0), level) / level
                                      for name, level in required_skills.items()) / max(len(required_skills), 1), 1)
        certifications = set(candidate.get("certifications", []))
        cert_score = round(100 * len(certifications.intersection(required_certifications))
                           / max(len(required_certifications), 1), 1)
        available = candidate.get("available") is True
        capacity = max(0.0, min(100.0, float(candidate.get("capacity_percent", 100))))
        projects = max(0, int(candidate.get("completed_projects", 0)))
        performance = candidate.get("performance_score")
        components = {"skill_match": skill_score, "certification_match": cert_score,
                      "availability": 100.0 if available else 0.0, "capacity": 100.0 - capacity,
                      "project_experience": min(projects / 3, 1) * 100,
                      "performance": max(0.0, min(100.0, float(performance))) if performance is not None else None}
        known_weight = sum(weights[key] for key, value in components.items() if value is not None)
        score = round(sum(value * weights[key] for key, value in components.items() if value is not None)
                      / max(known_weight, 1), 1)
        blockers = []
        if skill_score < 100:
            blockers.append("Required skills are not fully evidenced at the role threshold")
        missing_certs = sorted(set(required_certifications) - certifications)
        if missing_certs:
            blockers.append("Missing required certifications: " + ", ".join(missing_certs))
        if not available:
            blockers.append("Candidate is not currently available")
        if capacity >= 100:
            blockers.append("No remaining capacity is evidenced")
        ranked.append({"agent_id": candidate.get("agent_id"), "score": score,
                       "score_components": components, "missing_score_dimensions": [
                           key for key, value in components.items() if value is None],
                       "eligible_for_authorized_assignment": not blockers, "blockers": blockers,
                       "assignment_performed": False})
    return sorted(ranked, key=lambda item: (-item["eligible_for_authorized_assignment"], -item["score"], str(item["agent_id"])))