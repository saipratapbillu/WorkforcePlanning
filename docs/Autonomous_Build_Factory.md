# Autonomous Build Factory

## Scope and boundary

The Build Factory analyzes generated source-package strings, test-planning metadata, and the project package to produce an artifact manifest, dependency compatibility report, synthetic compilation assessment, version/release plan, quality gates, risks, dashboard, and readiness assessment. It is planning and static metadata analysis only.

No compiler, package manager, registry/network resolver, container engine, CI/CD system, publisher, deployment target, or infrastructure API is invoked. Source code is not returned in the build report; the manifest contains paths, sizes, and SHA-256 hashes of the in-memory source templates. No package is written, built, reserved, or published.

## Build analysis

- Artifact completeness checks required backend, frontend, database, API, security, test, and DevOps paths from the generated source manifest.
- Dependency analysis parses only declared requirements, package manifests, and .NET project references. It does not install or resolve packages. Compatibility remains `UNVERIFIED_STATIC_DECLARATIONS`; missing lockfiles and undeclared framework versions are risks.
- Compilation assessment scans source strings for known template placeholders and missing required assets. Build-success probability is a synthetic heuristic, not an observed result or calibrated probability. `execution_status` remains `NOT_COMPILED` and the observed build result is `null`.
- Artifact plans describe application, container, database, and configuration packaging. Container build, DDL application, package publication, and infrastructure creation remain false.
- Semantic version input is validated and returned as a proposal. Release/build numbers are not reserved; build number is `SIMULATED-NOT-ALLOCATED`.
- Quality gates include source completeness, dependency declarations, executed test evidence, observed compilation, security configuration, and release approval. In the current no-execution phase the release gate cannot be `READY`.

## API and outputs

`POST /workforce/factory/build-plan` requires `WORKFORCE_MANAGER` or `PLATFORM_OWNER`. It builds the source and test packages in memory, then returns only build metadata and the release plan. `POST /requirements` also includes a default Python `build_execution_package` generated during requirement planning; no source file contents are included in that response artifact.

The companion deployment planner consumes this build plan and test metadata to propose environments, waves, rollback gates, and readiness; see [Autonomous Deployment Factory](Autonomous_Deployment_Factory.md). It does not create hosting or infrastructure or call cloud APIs.

The response contains `build_blueprint`, `artifact_manifest`, `dependency_analysis`, `compilation_assessment`, `artifact_plans`, `version_plan`, `release_package_plan`, `quality_gates`, `build_risk_report`, `build_dashboard`, `build_readiness_assessment`, and `build_execution_package`. Control flags explicitly remain false for compilation, container build, CI/CD, publication, infrastructure, deployment, and persistence.

## Validation

Run `python -m pytest tests/test_build_factory.py tests/test_agent_factory.py -q` for manifest/dependency/version/readiness contracts. The tests execute only the planner; they do not compile generated source, resolve dependencies, build containers, or run pipelines.
