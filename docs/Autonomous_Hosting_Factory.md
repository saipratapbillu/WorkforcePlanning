# Autonomous Hosting Factory

## Scope and authority

The Hosting Factory transforms the Deployment Factory package and technical architecture metadata into Azure-oriented hosting options, data/security/network/observability/recovery plans, readiness checks, risks, dashboards, and scenario forecasts. It is planning and simulation only; no Azure API, cloud provider, runtime, CI/CD system, or infrastructure service is contacted.

Requirement creation includes `hosting_execution_package` in its transient workforce blueprint. Workforce reviewers can also call `POST /workforce/factory/hosting-plan` and download the result from Workforce Planning. Hosting choices and all environment details remain proposals. No subscription, resource group, region, hostname, address range, identity, secret, or service configuration is assumed as verified.

The companion Operations Factory consumes this plan to propose monitoring, SRE, incident, change, recovery, capacity, cost, patch, and runbook practices; see [Autonomous Operations Factory](Autonomous_Operations_Factory.md). It does not configure telemetry or connect ticketing/alert systems.

Authority is `NONE`; action permission and persistence are false. The plan does not create environments, provision App Service/Container Apps/AKS/Functions/VMs, create data services, configure Key Vault/identity/networking/monitoring, or deploy.

## Hosting options and recommendation

The planner lists App Service, Container Apps, AKS, Functions, and Virtual Machines. It makes a conditional recommendation only when architecture metadata has a clear signal: conventional web/API -> App Service; API/service without orchestration signal -> Container Apps; explicit Kubernetes/orchestration requirement -> AKS; event-driven/scheduled with no web surface -> Functions; host-specific legacy requirement -> Virtual Machines. Missing/ambiguous architecture returns `recommended_option: null` and `UNCONFIRMED`. Human architecture, security, cost, and operations review is required before selecting a platform.

## Plans

- Development, QA, UAT, and Production each carry configuration, dependencies, security, and network requirements. All remain `NOT_CREATED`.
- Data hosting describes SQL option review, storage classification/encryption/retention, backup, retention, and recovery. No database or storage engine/region/tier is selected without owner input.
- Security covers Key Vault requirements, managed identity scope, certificates, and secret references. No secret values are included or accessed.
- Networking covers topology, private endpoint candidates, DNS, firewall, and traffic flows. Addressing and rules are placeholders pending network-owner review.
- Observability covers monitoring, logging, tracing, and metrics without creating a workspace or instrumenting code.
- Disaster recovery requires business-approved RTO/RPO. They remain `null`; backup, restore, and failover are not configured or tested.
- Success/failure/recovery/blocked scenarios are forecasts only. Hosting readiness remains blocked or partial until architecture, build/test evidence, identity, network, recovery, security, and cloud environment evidence are independently validated.

## Validation

Run `python -m pytest tests/test_hosting_factory.py tests/test_agent_factory.py tests/test_requirement_creation_ownership.py -q` for package, recommendation, readiness, and no-cloud-action contracts. These tests invoke only local planning functions; they never call Azure or provision resources.
