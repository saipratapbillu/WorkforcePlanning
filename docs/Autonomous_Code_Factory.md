# Autonomous Code Factory

## Scope

`POST /workforce/factory/code-package` returns a JSON file map generated from a server-side SDLC blueprint. It supports `dotnet`, `python`, and `node` backend scaffolds, and includes frontend, database, OpenAPI, security, test, and DevOps assets. The browser can download this response as JSON; the application server does not write those files to the workspace.

The output is a source-artifact starter package for engineering review, not production-ready or approved software. The code factory does not execute generated code or tests, install packages, build images, create infrastructure, start a runtime, deploy, or modify production systems.

## Package contents

- Backend: stack-specific controllers/routes, service, repository interface, model/entity, request DTO, auth/audit adapter seams, project metadata, and starter unit tests.
- Database: additive PostgreSQL DDL, indexes, declared entity table placeholders, constraints guidance, and an intentionally empty seed file. No destructive SQL or business seed data is generated.
- API: OpenAPI 3.1 JSON derived from planned endpoint paths and request/response model names.
- Frontend: React/TypeScript page scaffolding, requirement form, navigation, screens, dashboards, and a generated UI manifest based on the blueprint.
- Security: fail-closed identity/authorization seams, RBAC matrix, audit event contract, and security integration checklist. Secrets are placeholders only.
- Tests: unit starters, integration scenarios, authorization checks, UAT scenarios, and a k6 smoke-test template. The factory does not run them.
- DevOps: language-specific Dockerfile, CI workflow text, `.env.example`, and a Terraform planning placeholder with no provider/resources. These are not applied or invoked.
- Traceability: backend and delivery manifests identify the source blueprint's components, APIs, entities, UI screens, and workforce roles.

## Safety and integration requirements

The generated identity adapters reject requests until a verified identity provider and authorization policy are configured. Persistence and audit adapters likewise fail closed until approved implementations are bound. Do not remove these guards by wiring unverified request claims, tenant IDs, or client-supplied roles.

The database scripts are PostgreSQL-specific, additive templates. The SDLC database blueprint does not establish a dialect, tenancy model, migration order, retention period, backup, or rollback plan. Review entity mapping, keys, foreign keys, tenant filters, retention, and schema evolution before adopting DDL.

OpenAPI paths and generic schemas require reconciliation with approved domain contracts. The frontend is a static starter and does not connect to a real API or identity provider. CI and Docker assets are inert file contents returned in the package. Terraform deliberately declares no resources.

## API

`POST /workforce/factory/code-package` requires `WORKFORCE_MANAGER` or `PLATFORM_OWNER`. Input includes the bounded requirement title/description, up to 20 technology labels (100 characters each), optional domain/priority, and an allowlisted backend language. The response includes `{path, content}` entries and explicit controls confirming no files were written, code executed, infrastructure created, or deployment performed. Never pass arbitrary source templates or output paths to this endpoint.

The companion `POST /workforce/factory/build-plan` analyzes generated package metadata and returns a hash-based artifact manifest, static dependency report, synthetic compilation assessment, version plan, quality gates, and release-package plan. It does not return source files and does not compile, install, build, publish, or deploy anything; see [Autonomous Build Factory](Autonomous_Build_Factory.md).

## Validation

Run `python -m pytest tests/test_code_factory.py -q` for package coverage, language selection, blueprint traceability, OpenAPI JSON/refs, safe paths, and no-execution/no-deployment flags. Run the full repository suite before release. These checks validate the generator and response strings; they do not compile or execute generated artifacts.