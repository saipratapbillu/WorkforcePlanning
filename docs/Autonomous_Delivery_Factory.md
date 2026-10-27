# Autonomous Delivery Factory

## Purpose and controls

The Delivery Factory transforms the transient Project Factory package into an execution blueprint, capacity and sprint forecasts, unassigned role recommendations, release plan, risk register, readiness dashboard, scenarios, and executive summary. It is deterministic planning and simulation only. It creates no project/task/sprint records, makes no assignments, executes no work, and performs no deployment.

The package is attached as `workforce_blueprint.delivery_execution_package` during requirement creation. Workforce reviewers can request a preview using `POST /workforce/factory/delivery-plan`; the Workforce Planning page downloads the response as JSON. The route rebuilds the project blueprint in memory and does not query or mutate the database.

## Forecast semantics

- Epic dependencies are topologically ordered. Unknown epic IDs and dependency cycles are rejected. The critical path is the longest predecessor chain using estimated epic duration.
- Capacity demand uses a planning conversion of 6 effort hours per story point. Per-role capacity values are generic assumptions, not roster or calendar data. Skill gaps and live availability are explicitly unavailable without workforce evidence.
- Historical velocity is `null`. The base velocity inherits the Project Factory planning assumption; a constrained case models 70% of that assumed velocity. Neither is an observed delivery rate.
- Sprint sequence, completion, resource constraints, delay, and risk-event outcomes are simulation scenarios. They change no plan state and have no calendar completion date.
- Role recommendations map proposed disciplines to work-item IDs and all remain `NOT_ASSIGNED`.
- Release waves, rollback steps, and gates are proposals. Deployment and release decisions remain separate authorized actions.
- Operational readiness score is deliberately 0 while execution, live capacity, approvals, and release evidence are unavailable. Planning completeness is reported separately so a complete plan is not confused with execution readiness.

## Package contract

The package includes `delivery_blueprint`, `capacity_forecast`, `sprint_simulation`, `agent_execution_plan`, `release_plan`, `risk_register`, `project_health`, `delivery_dashboard`, `execution_simulator`, and `executive_delivery_package`. Every output is planning evidence; control flags explicitly deny project/task creation, assignments, runtime, deployment, persistence, and approval authority.

Risk categories include schedule, workforce, dependency, technology, and governance risk. Current severities are conservative template assessments, not live risk measurements. Validate with project, security, operations, and governance owners.

## Validation

Run `python -m pytest tests/test_delivery_factory.py tests/test_project_factory_planner.py -q` for package structure, dependency-cycle rejection, assumption labels, no-assignment controls, and API preview behavior. The full project test suite remains the release check. The tests execute only the planner code; generated project plans are never sent to execution services.