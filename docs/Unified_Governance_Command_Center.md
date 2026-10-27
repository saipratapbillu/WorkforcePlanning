# Unified Governance Command Center

## Purpose and access

`GET /operations/governance-command-center` consolidates the Phase 17 operational monitor with a 30-capability reference catalog. It is restricted to the existing Executive/Platform Owner roles and can be exported from the Platform Owner Admin Control Center.

The package maps each capability to an API reference, dashboard surface, test file, documentation file, and relevant production gate. Capability status comes from the Phase 17 gate monitor: `READY` requires recorded `Approved` gate evidence, `BLOCKED` means a known gate is not approved/ready, and `UNVERIFIED` means no corresponding verified gate is available. Source references are traceability pointers, not proof that UAT passed.

Each capability also links to the audit monitor and identifies its governance control reference. Audit coverage is marked mapped but unverified at the per-capability level unless a source explicitly proves completeness. The Operations Readiness tab shows a compact current command summary; separate downloads provide the full 30-capability package and UAT matrix.

Operational readiness is derived from the count of actually approved production gates divided by the current gate denominator. Pilot and production authorization are passed through from recorded Phase 17 state. No approval or readiness is inferred from implementation presence.

## Authorization and data boundaries

The command package exposes only evidence already returned by the authorized Phase 17 monitor. It performs no operational writes, approval decisions, remediation, activation, probes, or runtime calls. It does not broaden the underlying role/visibility scope.

## UAT package

`GET /operations/uat-readiness` provides 21 requested-area scenarios covering authentication through production readiness, including preconditions, acceptance criteria, evidence requirements, API/UI/test/documentation/audit/governance mappings, and a synthetic-data-only matrix. Every scenario is marked `Not Run` and `Not Accepted` by default. `READY FOR FORMAL UAT EXECUTION (NOT RUN)` is possible only when pilot authorization is recorded and evidence coverage reaches 100%; it still does not mean UAT has passed. The package does not create fixtures or test records. A mapped test file is not a test execution result; acceptance requires actual UAT execution and evidence.

UAT readiness remains blocked while authorization/evidence gates are blocked. Defects use P0–P3 definitions, with P0 requiring immediate test stop and escalation.

## Verification

Run `python -m pytest -q` before release. Use an authorized role to export both packages. Confirm all 21 UAT areas have traceability fields, but do not interpret `Source Mapped` as `Passed` or as evidence that a scenario was executed.
