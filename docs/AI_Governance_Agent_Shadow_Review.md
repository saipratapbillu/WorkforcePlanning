# AI Governance Agent Shadow Review

## Architecture

The shadow-review framework registers the 14 requested governance personas: AI CEO, AI Governance Board, AI Security Officer, AI Compliance Officer, AI Data Steward, AI Enterprise Architect, AI Change Advisory Board, AI Risk Officer, AI Workforce Director, AI Certification Authority, AI Release Manager, AI Runtime Controller, AI Audit Officer, and AI Production Readiness Assessor.

The current implementation is a deterministic evidence-policy evaluator, not an LLM or a deployed autonomous agent. It consumes the read-only Phase 17 operational snapshot and evaluates role-specific existing gates and evidence sources. It performs no database writes, model calls, external network calls, approval decisions, certification, activation, release, or runtime action.

## API and outputs

`GET /operations/ai-governance/shadow-review` is restricted to the existing Executive and Platform Owner roles. It returns:

- Role, scope, evidence findings, blockers, and a non-binding recommendation.
- Policy version, generation timestamp, and SHA-256 evidence snapshot fingerprint.
- `authority: NONE`, `confidence_score: null` (uncalibrated), and flags showing persistence/operations are disabled.
- Overall `ESCALATE: EVIDENCE INCOMPLETE` while any role reports blocked or unverified evidence.

Each of the 14 role reviews also includes:

- `evidence_completeness_score`: percentage of required findings with verified evidence, not a prediction.
- `decision_confidence_band`: LOW/MEDIUM/HIGH derived only from evidence completeness. It is not a calibrated probability.
- `risk_rating` and `impact_rating`: conservative policy classifications based on role impact and observed blocked/unverified gates.
- `escalation_criteria`: explicit missing evidence, blocked gates, unverified sources, and threshold reasons.

## Controlled eligibility policy

The centralized policy registry defines stable policy ID, version, owner, domain, required evidence, minimum completeness, risk and impact thresholds, and escalation rules for Migration, Ownership, Provider, Model, Certification, Workforce, Adapter, Runtime, Security, and Release. The registry currently contains ten domain policies. The current autonomy maturity is **Level 2: Eligibility Assessment**; Levels 3–5 are disabled.

The framework evaluates proposal eligibility for those eight domains. Eligibility requires complete evidence, risk and impact within the configured thresholds, explicitly verified governance-violation and policy-exception checks with empty results, and every domain-specific check. Low-risk release additionally requires rollback availability, passed tests, passed security review, complete audit trail, change approval, and release approval evidence. Certification requires skill evidence, evaluations, governance requirements, and independent review. Model review requires an approved provider, approved policies, passing evaluations, risk/security assessments, and independent review.

Evidence completeness is the fraction of required findings marked VERIFIED. Evidence freshness is calculated only when every evidence item contains a parseable source timestamp and an explicitly supplied approved freshness limit; otherwise freshness is `UNVERIFIED` and confidence remains LOW. Future timestamps are treated as unverified. The risk score is an evidence-gap indicator (100 minus completeness), not a loss probability; impact score uses a documented ordinal role-impact mapping. Decision assurance checks consistency, evidence structure/fingerprint, reasoning presence, and recommendation conflicts; it does not prove source truth or model correctness.

When a required check is absent, unverified, false, or above threshold, the result is `ESCALATE` with reason codes and Info/Warning/Critical escalation records. When all checks pass, the maximum result is `ELIGIBLE_FOR_AUTHORIZED_REVIEW`; `authority` remains `NONE`, `action_allowed` remains false, and no decision is stored. The policy therefore identifies review candidates but does not autonomously certify agents, approve models/providers, release software, or override human/authorized gates.

Recommendations are limited to `BLOCKED`, `UNVERIFIED`, `RECOMMEND_REVIEW`, or escalation. The framework never emits `APPROVED`, `AUTHORIZED`, or `CERTIFIED`. The evidence fingerprint supports reproducible comparison but is not a durable decision ID or immutable decision record. Confidence is uncalibrated; no confidence score or probability is fabricated.

The Admin Control Center displays the shadow status and provides a JSON export. It does not offer an approval control.

## Assurance analytics and Level 3 gate

`GET /operations/ai-governance/assurance-platform` adds deterministic same-snapshot replay, decision reliability dimensions (recommendation stability, replay consistency, evidence sensitivity, and policy consistency), evidence fragility simulations, policy coverage analysis, and a governance drift lab. Every perturbation runs against a deep copy in memory and is labeled `simulation_only`; it cannot mutate the source snapshot, create approvals, execute actions, or persist a result.

Policy coverage is counted per required artifact, not per domain or generic gate. Only a `policy_evidence` record whose required-artifact name exactly matches and whose status is `VERIFIED`, source, `evidence_id`, and current `policy_version` all match counts as available. Missing, stale-version, or coarsely mapped evidence remains missing. Evidence fragility reports recommendation changes after evidence removal, expiry, incompleteness, and conflict simulations; its score describes this current-snapshot sensitivity, not production reliability.

The drift lab simulates policy-version, evidence, and risk changes. These are scenario comparisons, not historical drift. Historical decisions, trends, and longitudinal drift remain `Unavailable` because persistence is disabled. A stable same-snapshot replay or unchanged recommendation under perturbation does not establish evidence truth or readiness.

Level 3 readiness remains a non-authorizing assessment. It requires complete verified policy-artifact coverage, 100% verified and fresh evidence, reliable replay, traceability, independently verified audit completeness, verified reversibility, and no open governance escalation. Missing or unverified prerequisites keep Level 3 blocked or partially ready. Approval, certification, activation, release, migration, ownership, adapter, and runtime controls remain outside this framework.

## Why this is not autonomous authorization

Current governance endpoints intentionally enforce authorized role decisions and those actions can change approvals, requirements, models, ownership review evidence, agent lifecycle, adapters, or runtime. Certification and workforce status can influence operational eligibility and agent assignment. Automatically deciding these outcomes without independent controls could grant consequential capabilities or affect people and production. Removing those gates would require a separately approved autonomy policy, validated decision model and calibration, threat model, separation-of-duties design, appeal/override process, durable decision schema, audit-retention rules, operational monitoring, and staged safety validation. This implementation does not grant AI personas write authority and does not claim a production-grade AI model exists; current model governance reports zero approved models.

Before any durable AI decision record is introduced, design and approve an additive schema and retention policy, then write records through a dedicated, authenticated workflow. Do not treat the transient shadow response as a stored decision.

## Verification

`tests/test_governance_agent_framework.py` verifies all 14 personas, deterministic evidence fingerprinting, missing-evidence escalation, absence of approval authority, and no database writes at the route boundary. Run `python -m pytest -q` before release.
