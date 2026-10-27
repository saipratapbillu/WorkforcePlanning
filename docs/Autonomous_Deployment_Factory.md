# Autonomous Deployment Factory

## Scope and safety

The Deployment Factory transforms build, test, and project planning packages into environment, release-wave, rollback, infrastructure-readiness, security-gate, risk, dashboard, and scenario artifacts. It is planning and simulation only.

`POST /workforce/factory/deployment-plan` requires `WORKFORCE_MANAGER` or `PLATFORM_OWNER`. It builds source/build/test metadata in memory and returns only a deployment plan. The Workforce Planning UI can download this report, and requirement creation includes the default Python deployment simulation package automatically. The planner makes no cloud API calls and does not create environments or infrastructure.

Authority is `NONE`; action permission and persistence are false. Deployment, CI/CD, runtime, rollback, and cloud-call controls all remain false. Release readiness is currently `NOT READY` because compilation, test execution, environment/infrastructure evidence, rollback validation, and release approvals are absent.

## Environments and release waves

Development, QA, UAT, and Production plans list configuration, dependencies, and security requirements, but each environment status remains `NOT_CREATED`. Names, hostnames, regions, identity providers, networks, secret references, and SLOs are not invented.

The proposed wave order is Development verification → QA → UAT → Production promotion. Each wave includes prerequisite dependencies and a rollback checkpoint. Waves are unscheduled. The Production wave is explicitly blocked until all release gates are independently verified and authorized.

## Rollback and infrastructure readiness

Rollback scenarios cover application acceptance/health failure, database migration/data issues, and security/identity regressions. Procedures require preserving evidence, stopping promotion, using an independently reviewed restore/rollback runbook, and obtaining accountable owner review. No rollback has been executed or tested.

Database, storage, identity, and networking readiness are separately reported. Identity is blocked while provider validation is unconfigured; database/storage/network details require environment-specific design and approval. `infrastructure_created` remains false.

## Security, compliance, risk, and dashboards

Security and compliance checklists include identity validation, tenant/RBAC testing, data classification/privacy/retention, audit, vulnerability evidence, regulatory review, and release approval. Dependency, environment, release, and rollback risks are conservative planning risks, not observed incidents or cloud assessments.

The dashboard reports environment status, proposed wave completion, risk counts, rollback-plan/test status, and readiness. Success/rollback/blocked scenarios are deterministic forecasts only; they do not model a live service or change any state.

## Validation

Run `python -m pytest tests/test_deployment_factory.py -q` for package shape, missing-evidence blockers, scenario/control flags, and API composition. Tests exercise only the local planning function; no cloud, deployment, runtime, or CI/CD system is contacted.
