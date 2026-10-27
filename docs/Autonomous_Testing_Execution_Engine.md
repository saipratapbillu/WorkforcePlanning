# Autonomous Testing Execution Engine

## Scope and safety

The engine analyzes technical/project/delivery blueprint fields and source-package file metadata to produce test strategy, coverage mapping, scenario catalogs, synthetic quality forecasts, expected defects, dashboards, and a release assessment. It does not import, compile, execute, or invoke generated test assets; it does not create an environment, run CI/CD, deploy, persist results, or authorize release.

`POST /workforce/factory/test-simulation` is restricted to `WORKFORCE_MANAGER` and `PLATFORM_OWNER`. It builds the blueprint and source file map in memory, passes only metadata/content paths to the test planner, and returns the test report package without raw source files. The Workforce Planning UI can download this report-only JSON.

## Report semantics

- `execution_status` is always `NOT_EXECUTED`; observed pass rate, failure rate, and code coverage are `null`.
- Simulated pass/failure and code coverage are synthetic forecasts, explicitly labeled `SIMULATED_FORECAST_NOT_OBSERVED`. Design coverage measures whether planned test domains and corresponding test assets exist; it is not statement or branch coverage.
- Integration and UAT scenarios are plans, not test results. Security findings describe known generated-template blockers, not vulnerabilities discovered by a scan.
- Performance targets remain unset until workload/SLO baselines are approved. Load, stress, and volume cases are scenario definitions only.
- Defects are expected template/readiness issues. They are not observed failures.
- Release assessment is capped at `NOT READY` or `PARTIALLY READY`; it cannot report `READY` without real execution evidence and independent approvals. The current fail-closed templates make the simulated release assessment `NOT READY`.

## Package contents

The response contains testing strategy, test coverage map, unit report, integration matrix/scenarios, authentication/authorization/input validation plan, security findings, load/stress/volume plans, performance forecast, business UAT matrix, expected defect register, quality dashboard, release quality gate, and an aggregate test execution package. All controls for test execution, code execution, environment creation, CI/CD execution, deployment, persistence, and release authorization are false.

## Validation

Run `python -m pytest tests/test_testing_execution_factory.py -q` for package shape, synthetic metric labels, release gate behavior, missing-input handling, API behavior, and no-execution assertions. These tests run only the planner itself; they never run generated source or tests.