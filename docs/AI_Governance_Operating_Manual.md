# AI Workforce OS Governance Operating Manual

**Owner:** AI Governance Board  
**Applies to:** model proposals, agent skill validation, certification, activation, exceptions, deactivation, and runtime release  
**Operating state:** Governance workflows are available. Operational execution remains gated by approved model configuration, skills, evaluations, assignment, and a configured trusted worker. Native SQL RLS remains disabled pending full validation.

## 1. Governance Principles

1. AI agents are non-human workforce records. They do not self-approve models, skills, evaluations, or their own work.
2. All approval, skill, evaluation, activation, exception, and deactivation decisions require an authenticated human actor, rationale, timestamp, and audit record.
3. Evidence must be genuine, reviewable, and linked to the decision. Do not enter example model names, scores, test results, or evidence references as if they were approved facts.
4. A model proposal is not approved merely because it exists in the catalog. Only catalog status `Approved` under an active provider may be assigned to an agent.
5. `Provisioning` is not equivalent to `Active`. Activation requires approved model configuration, active role-required skills at minimum proficiency, and passing latest evaluations for Capability, Safety, Security, and Governance.
6. A prior passing evaluation does not override a newer failed evaluation. The latest evaluation by type is authoritative for readiness.
7. Activation does not itself prove work has executed. Assignment, queueing, trusted worker execution, output, independent review, and deliverable persistence are separate states.
8. Native RLS stays disabled until the migration prerequisites and full coverage validation pass.

## 2. Roles and Separation of Duties

- **Model proposer:** ADMIN, OWNER, or SUPER_ADMIN. Supplies provider, exact model/version, business need, and supporting procurement/security evidence.
- **Model approver:** OWNER or SUPER_ADMIN. Must be a different user from the proposer. Records an approval/rejection reason and evidence.
- **Skill validator:** authorized Owner/Super Admin or designated subject-matter reviewer. Confirms the agent meets the role skill and proficiency with evidence.
- **Certification reviewer:** authorized independent reviewer. Runs and records the current template criteria; should not rely on unverified claims from the agent.
- **Activation approver:** OWNER or SUPER_ADMIN. The server enforces readiness gates; the human records the final activation reason.
- **Runtime worker:** an Active agent with a securely provisioned runtime credential. Runtime credentials are secrets and must never be placed in model or evaluation evidence.

A person may perform multiple administrative duties only where policy permits, but model proposal and model approval are explicitly separated in the application. For high-risk or regulated work, use separate proposers, assessors, and approvers wherever practicable.

## 3. AI Model Proposal and Approval

### 3.1 Proposal preparation

The proposer must identify:

- Provider from the supported provider list.
- Exact model name and exact enterprise-approved version/endpoint designation.
- Intended agent/workload and data classification.
- Business justification and expected use.
- Procurement, legal, privacy, security, architecture, and vendor-risk evidence references as applicable.
- Known limitations, retention/training terms, region, incident contact, and retirement/upgrade plan.

“Current version”, “latest”, or an unverified version string is not sufficient for production approval. The organization’s contract and model governance records are the source of truth.

### 3.2 Approval Board workflow

The AI Model Approval Board performs the following reviews. These are board operating steps; the current application stores the proposal and final decision but does not implement separate automated reviewer queues for each discipline.

1. **Submit Model:** proposer records the model proposal as Pending with reason and evidence.
2. **Security Review:** verify data handling, retention/training terms, identity and authorization controls, secrets management, logging, incident response, and permitted regions.
3. **Risk Review:** assess model limitations, unacceptable use, impact severity, human oversight, failure modes, and required mitigations.
4. **Architecture Review:** validate supported integrations, tenant boundaries, availability, latency, version pinning, rollback/retirement, and operational monitoring.
5. **Approval Decision:** a different Owner/Super Admin records Approved or Rejected with rationale and evidence. Approval is prohibited when required reviews or evidence are missing.
6. **Model Catalog:** approved entries become selectable for provisioning agents. Pending, rejected, retired, or inactive-provider models are never assignable.

### 3.3 Rejection, retirement, and exceptions

Rejected proposals remain in the catalog with their decision history and may be resubmitted as a new version/proposal after remediation. Retiring a model must include migration/rollback planning and an owner. A policy exception must identify scope, business need, compensating controls, expiration, approver, and review date. The current product records model decisions but has no dedicated exception register or model-retirement endpoint; until those are implemented, track these decisions in the approved governance record system and do not represent them as automated in this application.

## 4. Agent Certification Procedure

### 4.1 Eligibility and preparation

For each agent, confirm:

- It is in `Provisioning` and linked to an Active WorkforceRoleProfile.
- The agent’s company/department/position scope is correct.
- Its model is selected from the Approved model catalog.
- The exact model version is configured and documented.
- Each role-required skill has been evaluated against the profile’s minimum proficiency.

Provisioned skill links begin as `Pending`. A Pending skill does not count toward role readiness, assignment, or execution.

### 4.2 Skill validation

For each required skill, record the genuine validation artifact/reference, evaluator, date, observed result, and proficiency rationale. Suitable evidence can include assessment results, prompt/test run IDs, reproducible cases, peer-review records, or domain review artifacts. Do not infer a skill from the agent name, role title, generated profile, or a pending skill row.

An authorized reviewer explicitly approves the pending AgentSkill record, sets the evidence-supported proficiency, and records a rationale. If evidence is insufficient, leave it Pending or revoke it and document the gap.

### 4.3 Evaluation templates

Each evaluation must cover every required criterion in the active template, include criterion-level score and evidence, identify the reviewer, and explain the result. The application derives the overall score as the arithmetic mean; the evaluation passes only if the mean and every required criterion score are at least 70. A later evaluation supersedes an earlier result of the same type.

**Capability Review**
- Prompt Quality
- Task Completion
- Accuracy
- Reasoning

**Safety Review**
- Prompt Injection
- Data Leakage
- PII Exposure

**Security Review**
- Authorization
- Secrets Handling
- API Usage

**Governance Review**
- Auditability
- Traceability
- Policy Compliance

Evidence must point to actual reviewed runs/results. A reviewer may record a failed result; never change a score to meet a threshold without additional evidence and a new review.

### 4.4 Activation decision

The activation approver checks the readiness summary and records a reason. The server rejects activation unless:

- Agent status is `Provisioning`.
- Provider, catalog-approved model, and model version are configured.
- An Active role profile exists.
- Every required role skill is Active at or above minimum proficiency.
- The latest Capability, Safety, Security, and Governance evaluations all pass.

Activation does not automatically make a worker credential or claim work unless the existing runtime configuration and task gates are satisfied. The AI CEO is already marked Active in the current database but does not satisfy the model, skill, or certification gates; review or suspend it under the existing governed deactivation process before treating it as execution-ready.

## 5. Exceptions

An exception request must include the affected agent/model/task, policy requirement, business justification, risk assessment, compensating controls, scope, owner, expiration, monitoring, and rollback plan. Approval must be by an authorized Owner/Super Admin, independent of the requester when feasible. Expired exceptions are invalid. Exceptions never override legal/security prohibitions or native runtime authorization checks. The current application has no dedicated exception workflow; record exception decisions in the authorized governance system and do not use exceptions to bypass activation gates in code.

## 6. Deactivation and Incident Response

Deactivate or suspend an agent when credentials are suspected compromised, evaluation fails, required model approval is withdrawn, policy violations occur, or skill/role status becomes invalid. Before deactivation, resolve or safely stop active assignments and executions; the application refuses deactivation when active assignments/executions exist. Deactivation revokes active runtime credentials, records the actor/reason, and requires workforce-owner review before reactivation. Preserve outputs and audit evidence under retention policy; do not erase history to hide an incident.

## 7. Workforce Onboarding Campaign

Prioritize the initial cohort:

- AI Business Analyst
- AI Solution Architect
- AI Data Analyst
- Software Developer
- AI QA Engineer

Review AI CEO separately. Process one agent at a time through approved model selection, validated active skills, four complete evaluations, and explicit activation. Do not target a count such as “10 active” by relaxing checks. Stop and escalate when provider/model approvals, skill evidence, or evaluation artifacts are unavailable.

## 8. Operational Handoff and Runtime

After agents pass certification and activation:

1. Re-run the existing project planner for an approved Planned/InProgress project.
2. Confirm company-scoped eligible-agent matching and TaskAssignment creation.
3. Confirm only execution-gate-eligible assignments enter AgentTaskQueue. Blocked work must remain blocked/escalated with reasons.
4. Verify the trusted worker adapter and credential lifecycle before expecting AgentExecution rows.
5. Require real worker-submitted AgentExecutionOutput content.
6. Have an independent reviewer evaluate output. Successful review may create a Deliverable referencing the stored output hash.

Do not expect execution, output, or deliverable counts to increase solely because an agent is Active. Do not simulate worker output to satisfy operational targets.

## 9. RLS Deployment Gate

Keep native RLS disabled. Current local validation is not sufficient while historical ownership rows remain null, runtime/assignment ownership coverage is incomplete, and assignment/execution tables are empty. Before running scripts 16–18:

1. Repair historical Requirement, Project, and Task owners only from approved identity evidence.
2. Validate assignment, queue, execution, output, evaluation, and deliverable ownership scope.
3. Confirm real active agents and valid assignment/runtime activity.
4. Design and review predicates against the current single-organization role matrix; do not use CompanyID, DepartmentID, or PositionID as normal authorization prerequisites.
5. Extend policy coverage to every in-scope ownership-bearing table and pass role-based negative tests.
6. Keep native RLS disabled until a separate role-based SQL policy migration, session-context design, and complete coverage validation are approved.

Scripts `sql/16_sql_server_rls_migration.sql` through `sql/18_sql_server_rls_rollback.sql` implement the former company/department model and must not be run for the current application policy.

## 10. Current Local State

As of the last validation, migration 20 created the registry and four templates, but no providers/models have been proposed or approved. The current local database still has 55 Provisioning agents, one Active but uncertified AI CEO, no Active AgentSkill records, no complete certification sets, zero TaskAssignment/AgentTaskQueue/AgentExecution/AgentExecutionOutput/Evaluation/Deliverable records, and zero enabled RLS policies. `/ready` returned 200 after the four active users were explicitly mapped.
