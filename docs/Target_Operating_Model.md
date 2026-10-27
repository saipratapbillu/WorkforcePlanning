# AI Workforce OS Target Operating Model

**Status:** The organizational role catalog, recommended reporting hierarchy, quality-gate registry, and escalation ladder are configured by `sql/08_governed_organization_and_quality_gates.sql`. These are target-policy records, not proof that every workflow gate, agent, escalation timer, or autonomous action is implemented. The catalog is a starting point for review by the Owner, department heads, HR, Security, Legal/Privacy, and Finance.

## Non-Negotiable Controls

1. No work proceeds without validated requirements, risk, ownership, and acceptance criteria.
2. High-impact decisions, agent lifecycle, policy changes, budget exceptions, and production release require their designated human approval.
3. Every handoff requires a deliverable, validation evidence, QA outcome, security review when applicable, logged risks, audit event, and required approval.
4. An originating agent cannot provide the independent quality, security, audit, or executive approval of its own work.
5. Agent recommendations are advisory unless a separately approved, bounded automation policy exists. Agents never make employment decisions or self-activate.
6. Escalation targets and response times are configured as policy proposals; timers, notifications, and escalation execution require a runtime workflow service.

## Organization Registry

The role catalog encodes `RoleCode`, position, department, grade, manager role, organization layer, job description, responsibilities, required skill thresholds, approval scope, quality gates, and a maximum recommended autonomy level. It includes:

- Governance: Owner/Super Admin (account authority outside the AI catalog), AI Chief of Staff.
- Executive board: AI CEO, CTO, COO, CFO, CHRO, and CISO.
- PMO: PMO Director, Program Manager, Project Manager, and Delivery Lead.
- Business analysis: Business Architect, Business Analyst, and Process Analyst.
- Architecture: Enterprise Architect, Solution Architect, Data Architect, and Integration Architect.
- Engineering: Technical Lead, Full Stack Developer, Backend Specialist, Frontend Specialist, Database Specialist, Integration Specialist, DBA, Data Engineer, and Data Analyst.
- Data and analytics: Data Engineer, BI Specialist, Data Scientist, and Data Analyst.
- Quality: QA Director, Test Architect, Test Engineer, Automation Tester, QA Engineer, and independent Quality Reviewer.
- DevOps: DevOps Architect, DevOps Engineer, and Cloud Engineer.
- Support and operations: L1/L2/L3 Support, Incident Commander, Root Cause Analyst, and Knowledge Manager.
- Cross-functional governance: Problem Solver, AI Auditor, Risk Officer, and Security Engineer.

Some delivery roles intentionally appear in more than one organizational concern; use one canonical role code where possible and create aliases only with explicit governance. The current registry has canonical role codes that overlap with the phase-two workforce profile names; migration updates those profile rows rather than creating duplicate codes.

The displayed AI job descriptions are original role charters, not scraped or copied global job postings. HR/legal must review role requirements for jurisdiction, fairness, accessibility, employment classification, and local policy before using them for human recruiting. The catalog describes roles; it does not instantiate agents or employees.

## Reporting Model

- Owner/Super Admin retains final governance authority and visibility.
- AI Chief of Staff reports to Owner and coordinates monitoring and escalation.
- CEO, CTO, COO, CFO, CHRO, and CISO report to the Chief of Staff in the proposed model.
- PMO reports through COO; technology architecture and engineering through CTO; Finance through CFO; HR and workforce through CHRO; Security through CISO; independent quality through QA Director; audit and risk retain independent challenge paths.
- The registry `ReportsToRoleCode` records recommended reporting, not live agent-manager assignment. Actual agent hierarchy remains explicit agent records and must be governed separately.

## Gated Requirement-to-Outcome Flow

1. Requirement validation by Business Analyst: problem, measurable outcome, stakeholder, data, acceptance criteria, assumptions, and open questions.
2. CEO assessment: strategic fit, value, priority recommendation, and business risks.
3. CTO/architecture review: solution options, technical fit, integration, security architecture, and technical risks.
4. CFO review: cost estimate, ROI assumptions, budget limits, and financial risks.
5. COO/Delivery Lead planning: decomposition, dependencies, effort, qualified workforce, and schedule assumptions.
6. Business and executive approval: named decision-makers record decisions and rationale; risk policy determines additional levels.
7. Project Factory creates only a planned project and tasks after the active approval policy passes.
8. Delivery Lead owns the approved project plan and task handoffs. A task starts only with qualified active staffing, a Delivery Lead, completed prerequisites, and required inputs.
9. Development handoff includes the requirement, design, assumptions, risks, acceptance criteria, and decision history.
10. QA self-review, peer review, independent Quality Review, Security/CISO review, and Auditor/Governance review collect evidence before the applicable release gate.
11. Executive and Owner sign-off apply when policy marks the work high-risk, strategic, exception-bound, or production-bound.
12. DevOps/Cloud release and L1/L2/L3 support handoff remain disabled until independent production and rollback controls are implemented.

## Gate Registry

`GovernanceGateProfile` configures the ordered gate name, accountable role, applicability, blocking behavior, human-approval requirement, and required evidence. Current seeded gates include requirement validation, CEO assessment, CTO architecture, CFO cost, COO delivery plan, business approval, security review, governance review, self-review, peer review, independent quality review, executive sign-off, Owner sign-off, production security, and support handoff.

The registry is not yet consumed as a general workflow engine. In addition to the requirement and staffing controls, the live application now has a discrete task runtime that enforces agent activation/provider/evaluation checks, approved requirement and human approval, active assignment and role skills/capacity, task-scoped Security evidence for High/Critical tasks, active Delivery Lead, and completed dependencies. It does not enforce CTO/CFO/COO stages, all seven quality stages, Owner policy by arbitrary gate, release gates, or the registry sequence. Do not infer that the registry itself drives these checks.

## Quality And Handoff Evidence

Each deliverable should carry:

- Inputs and source requirement/version.
- Output artifact and owner.
- Assumptions and unresolved questions.
- Risk/issue references and mitigation status.
- Acceptance criteria and test results.
- Security and privacy review results when in scope.
- Required approval decisions, actors, timestamps, and rationales.
- Next action, accountable recipient, and escalation deadline.

A gate passes only after the configured required evidence exists and the independent reviewer is authorized. Missing evidence, critical defects, rejected decisions, or security holds block handoff.

## Escalation Registry

`EscalationPolicyProfile` proposes L1 -> L2 -> L3 -> department/PMO -> executive/Chief of Staff -> Owner for unresolved work, overdue decisions, critical risk, or major incidents. The initial response windows in the migration are configuration proposals only. No SLA clock, paging, escalation notification, or auto-reassignment is implemented yet.

## Agent Lifecycle And Autonomy

Agent creation, retirement, security policy changes, governance changes, organization changes, budget threshold exceptions, strategic/high-risk projects, critical escalations, and production exceptions require Owner/Super Admin approval. The approved sequence should be:

1. Role profile and business case approved by CHRO/department head and Owner policy.
2. Human recruiting/candidate decision where a human role is being hired; never delegate employment decisions to AI.
3. Agent technical configuration in a sandbox with approved model/provider and secrets managed server-side.
4. Skill verification, threat review, tool/permission allowlisting, cost/token ceilings, and passed Capability, Safety, Security, and Governance evaluations.
5. Human activation approval and monitored limited autonomy. Workforce approval now creates a non-active Agent record in `Provisioning`; it does not configure a model or activate skills.
6. Ongoing quality, cost, workload, incident, and performance monitoring; suspend/retire only through audited control.

A recruiting approval creates a role-derived Agent row in `Provisioning` and Pending AgentSkill records. It does not configure model credentials, authorize tool permissions, pass evaluations, assign work, or activate the agent. Activation requires an approved provider, configured model/version, passed Capability, Safety, Security, and Governance evaluations, and an explicit reasoned Owner/Super Admin activation action. If any check fails, durable blocker records are created and Owner/Super Admins are notified; activation remains blocked. After authorized activation, the planner automatically links an eligible Delivery Lead and assigns qualified role tasks while respecting capacity and dependencies. A project or recruiting approval does not execute code or authorize tools.

The repository has no built-in agent model invocation loop or isolated code-edit/test runtime. Task assignment after activation is automatic and dependency-aware. A governed pull queue, per-agent hashed worker credentials, execution leases/heartbeats, bounded retries, output/hash retention, structural-only validation, independent reviewer decision, QA defect records, escalations, notifications, and audit events are implemented in the runtime API. The API fails closed when no trusted execution adapter is injected; it does not itself produce code or run tools. Independent QA is a manual Admin/Owner/Super Admin decision, not a full QA/test pipeline. Do not claim autonomous software development until a sandboxed trusted worker, artifact checkpointing, actual test execution, role-appropriate independent QA/security gates, and adversarial security tests are deployed.

Runtime migrations must be applied in order: `sql/12_agent_runtime.sql`, then `sql/13_agent_runtime_credentials_defects.sql`. Owner/Super Admins can rotate or revoke credentials for Active agents; the raw token is returned only once. Worker endpoints derive the agent identity from the credential, never from client-supplied AgentID. Queue claims are pull-based and require an external worker; FastAPI starts no background runtime loop. Blocked eligibility is recorded as a task/queue escalation, retries are limited to three claims, expired leases are rejected, and an Owner requeue re-runs the gates before commit. See [Workflows](Workflows.md) for routes and lifecycle details.

## Implementation Status And Next Phases

**Implemented:** local role/JD registry; reporting lines and gate/evidence metadata; escalation policy registry; Owner/Super Admin-approved, idempotent company organization bootstrap; department/position creation when missing; one Agent record per role in non-active Provisioning state; pending role-skill links; Delivery Lead and role-based project planning; unique pending workforce requisitions; skill/capacity candidate matching; task sequencing/dependencies; prerequisite and assigned-agent start gates; runtime queue/execution/output/QA/retry/escalation persistence and APIs; hashed worker credential rotation/revocation; task completion/release after an authenticated review decision; audit events; Workforce Center and tracker views.

The approved HR demo bootstrap is complete: 56 role profiles mapped, 49 Agent records created, 7 existing role agents reused, 55 agents in `Provisioning`, and the pre-existing AI CEO remains the only Active role agent. The reporting hierarchy resolves to one root, AI Chief of Staff; six HR project requisitions are linked to their canonical role agents. Agent skills are Pending, no HR project task is assigned, and no execution has started.

The activation gate requires provider, model, and version configuration; passed `Capability`, `Safety`, `Security`, and `Governance` evaluations; and an explicit reasoned Owner/Super Admin activation action. Failed attempts are persisted in `AgentActivationBlocker`, audited, and sent as in-app Owner/Super Admin notifications. The six HR project's agents currently have four open blocker categories each (24 notifications total); none is Active and no task is assigned.

**Still required before claiming the pasted target model is fully operational:** runtime multi-executive assessment orchestration, configurable gate engine consuming `GovernanceGateProfile`, independent seven-stage QA evidence workflow and real test execution, owner-scoped policy exceptions, executive board and Chief of Staff monitoring, SLA timers, human candidate/employee onboarding, fair-role evaluation and legal review, a trusted isolated task/deploy worker and execution adapter, production release approvals, notification outbox/retries, workload/fairness and cost accounting, and adversarial security testing. The database migrations have not been applied merely by adding these scripts to the repository; deploy them explicitly before enabling the endpoints.
