# Autonomous Agent Creation Engine

## Purpose and safety boundary

This phase transforms the transient Workforce Blueprint into agent lifecycle planning artifacts. It is simulation only. The generated `agent_lifecycle_package` is attached to requirement creation responses and can be previewed with `POST /workforce/factory/agent-lifecycle-plan`.

The engine performs no database access or writes. It does not create agent records, provision credentials, issue certifications, activate agents, assign work, modify workforce/project/task tables, or execute runtime activities. All control flags are false, authority is `NONE`, and action permission is false. Simulated IDs prefixed with `SIM-AGENT-` are stable plan identifiers, not database IDs.

## Package artifacts

- Agent catalog lists all ten supported role families. Roles outside the current Workforce Blueprint are labeled `NOT_REQUIRED_BY_WORKFORCE_BLUEPRINT`; only in-scope roles receive detailed proposed profiles.
- Profiles include simulated ID, name/type/category, purpose/objectives, JD summary/responsibilities/deliverables/success metrics/KPIs/reporting/tools/governance duties, and skill matrix.
- Skills are categorized Technical, Domain, Security, Governance, or AI with a required level, criticality, and training path. Role baselines include AI safety, governance controls, and secure data handling. Technology-specific skills are added for .NET, Python, Angular, React, Azure AI, Copilot Studio, OpenAI, and Anthropic when identified.
- Certification paths define Bronze/Silver/Gold/Platinum training, independent evaluation, expiry, and renewal rules. Every path remains `NOT_ISSUED`.
- Lifecycle blueprints cover Created, Provisioned, Certified, Active, Assigned, Paused, and Retired, with entry/exit criteria, governance gates, and required evidence. No state transition occurs.
- Upskilling proposals list skill gaps, training, JD/certification changes, and leave approved profiles unchanged.
- Assignment readiness and replacement plans are recommendation-only. With no candidate roster, current certification freshness, availability, capacity, or project history supplied, readiness is `null`/unverified and replacement candidates are unavailable.
- Governance profiles define risk, responsibility, security classification, human ownership, approval, and audit requirements. The Workforce Director report summarizes creation, skill/certification coverage, capacity, assignment, replacement, and retirement readiness without operational authority.

## Future Level 3 boundary

The package records Level 3 Supervised Agent Provisioning Sandbox as a disabled future phase. Enabling it requires a separately approved policy and authenticated review workflow, proposal/approval separation, idempotent audited provisioning, negative authorization tests, and an invariant that no agent activates until independently approved. This phase does not make or prepare a database mutation.

## Validation

Run `python -m pytest tests/test_agent_lifecycle_factory.py tests/test_requirement_creation_ownership.py -q`. Tests cover all ten catalog roles, scoped profiles, stable simulated IDs, skills/certification/lifecycle structures, technology upskilling, unavailable candidate readiness, and no-write/no-issue/no-assignment guarantees.