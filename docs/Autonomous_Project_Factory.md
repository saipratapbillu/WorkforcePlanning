# Autonomous Project Factory

## Scope and boundary

The Project Factory is a deterministic planning service that converts a requirement and its technical delivery blueprint into a proposed project structure. It returns a `project_delivery_package` within the Agent Factory response, so `POST /requirements` includes it automatically. Authorized workforce reviewers can also call `POST /workforce/factory/project-blueprint` to regenerate the same kind of preview.

The planner does not use a model, persist plans, create Project/Epic/Feature/Story/Task/Sprint records, assign agents, execute runtime work, or deploy. The word “Autonomous” describes generation of planning artifacts only; it does not grant authority to advance delivery lifecycle state.

The companion delivery simulation is returned as `workforce_blueprint.delivery_execution_package`; see [Autonomous Delivery Factory](Autonomous_Delivery_Factory.md). It derives sequence, critical path, capacity assumptions, sprint scenarios, risk, release gates, and readiness without changing this project plan or creating work items.

## Package contents

- Project charter: vision, goals, objectives, outcomes, success measures, priority, scope and assumptions.
- Epic catalog: stable proposed IDs, descriptions, priorities, and predecessor dependencies.
- Feature catalog: feature descriptions, priorities, and acceptance criteria.
- User story catalog: story statements, positive integer story points, value bands, acceptance criteria, and dependencies.
- Task catalog: development, testing, security, deployment-readiness, and documentation task outlines linked to stories/features/epics.
- Sprint plan: estimated sprint count and planned points using an explicit assumed 20 points per two-week sprint. Historical velocity and available hours remain unavailable until measured team data exists.
- WBS: Project → Epic → Feature → Story → Task hierarchy, deliverables, dependencies, and unscheduled milestones.
- Workforce mapping: Architect, Developer, QA, Security, DevOps, and Business Analyst contributions mapped to proposed work-item IDs. All rows remain `NOT_ASSIGNED`.
- Governance package: risks, assumptions, dependencies, constraints, and review/approval requirements.

Stable IDs are generated from fixed template order for deterministic replays. They are proposal identifiers only, not database keys. Acceptance criteria and story points are starter estimates requiring product-owner review. Sprint capacity and velocity are not live forecasts.

## API

`POST /workforce/factory/project-blueprint` requires `WORKFORCE_MANAGER` or `PLATFORM_OWNER`. It accepts the same bounded requirement title, description, technology, domain, and optional priority inputs as the existing factory blueprint API. It performs no database access or writes.

`POST /requirements` includes `workforce_blueprint.project_delivery_package` in its response. The existing requirement persistence and approval behavior remains unchanged; the project package is transient and is not stored separately.

## Controls and verification

The response is marked `PLANNING_ONLY`. Control flags for project/epic/feature/story/task/sprint creation, assignments, runtime, deployment, and persistence are false. To create real work items later would require separate schema design, idempotency, authorization, audit, dependency validation, approval, capacity controls, and lifecycle tests.

Run `python -m pytest tests/test_project_factory_planner.py tests/test_requirement_creation_ownership.py -q` for package and requirement-create contracts. The tests validate stable IDs, catalog coverage, estimate assumptions, workforce links, and no-mutation flags; they do not create or execute project work.