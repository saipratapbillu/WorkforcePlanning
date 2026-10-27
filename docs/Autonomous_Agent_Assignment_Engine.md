# Autonomous Agent Assignment Engine

## Scope and controls

The engine builds an assignment recommendation package from the Project Factory plan, Delivery Factory sequence, Workforce Blueprint, Agent Lifecycle Blueprint, and optional candidate evidence. It does not persist plans, assign agents, activate or provision agents, execute runtime work, or mutate projects, tasks, or workforce records.

`POST /workforce/factory/assignment-plan` is restricted to `WORKFORCE_MANAGER` and `PLATFORM_OWNER`. It rebuilds the project and delivery inputs server-side. Optional candidate attributes are caller-supplied claims for provisional comparison only; they are not independently validated by this preview endpoint. No database or roster query is performed. The Workforce Planning UI can download a no-candidate recommendation package; in that case candidate scores, available capacity, and verified readiness remain unavailable.

## Matching and capacity

Candidate comparison uses skill match (30%), certification match (20%), availability (15%), capacity (15%), project fit (10%), technology fit (5%), and performance (5%). Missing dimensions are excluded from the weighted score and listed as unverified. A score based on caller-supplied claims is labeled `PROVISIONAL_CALLER_SUPPLIED_EVIDENCE`; it is not evidence that the underlying skill, certification, or capacity is true/current. A performance reference allows a provisional performance component to be calculated, but `performance_evidence_verified` remains false.

Candidate readiness never becomes `READY` in this preview because evidence is not independently verified. At best, a candidate is `PARTIALLY_READY` as a provisional claim when supplied fields meet the local checks. The verified assignment-readiness score remains `null`, verified status is `UNVERIFIED`, and `can_project_be_staffed` remains false. Claimed capacity is reported separately from verified available capacity; reserved capacity is also marked caller-supplied/unverified. Historical performance only contributes when a reference is supplied and remains explicitly unverified.

Required hours are estimates from the planned task catalog and fixed task-type assumptions. Since no work calendar or live resource query is performed, utilization and verified available capacity remain unavailable. Missing role candidates produce explicit skill/certification/capacity gaps and an upskilling recommendation.

## Package

The response contains:

- Assignment blueprint with work-item recommendations and proposed team composition.
- Match results with score, components, missing/unverified dimensions, blockers, and `NOT_ASSIGNED` status.
- Capacity plan with required effort, unverified claimed capacity, and skill gaps.
- Assignment readiness with `NOT_READY`/`PARTIALLY_READY`, never verified readiness.
- Replacement primary/secondary/fallback candidate slots, or unavailable when no evidence is supplied.
- Workforce Director dashboard for readiness, coverage, utilization, capacity, skill gaps, and replacement readiness.
- Execution readiness report that only reports staffable when independently verified evidence exists; this preview has no such verification path, so authorization remains false.

Every response sets authority to `NONE`, action permission to false, persistence to false, and all assignment/activation/provisioning/runtime/project/task mutation flags to false. A separate authorized workflow remains required for any actual state transition.

## Validation

Run `python -m pytest tests/test_assignment_factory.py -q` for roster-free behavior, candidate scoring, hard readiness gaps, unknown-performance handling, API input bounds, and no-action controls. Tests validate recommendations only; they never assign a candidate.
