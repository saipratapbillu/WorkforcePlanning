# AI Model Registry and Agent Certification

## Deployment

1. Back up the target development database and review `sql/20_ai_model_registry_and_evaluation_templates.sql`.
2. Apply that additive migration once. It creates the model provider/catalog/approval and reusable evaluation-template tables; it does not alter Agent, Evaluation, assignment, or runtime tables.
3. The migration seeds Capability, Safety, Security, and Governance templates. It intentionally creates no approved model catalog entries.
4. Restart the current application source and open `/admin-control-center` as Owner/Super Admin.

## Model approval

- Propose a provider/model/version with procurement/security reason and evidence.
- Proposals are saved as Pending and do not appear in the agent model selector.
- A different Owner/Super Admin reviews and approves or rejects with separate reason/evidence. The proposer cannot approve their own entry.
- Only Approved entries under Active providers are returned by `/governance/models/approved` and accepted by the agent model configuration endpoint.
- Example provider labels are Azure OpenAI, Google, and Anthropic. Model names and versions must come from the organization’s approved enterprise inventory; examples in a request are not treated as approval.

## Certification

The active templates contain these required criteria:

- Capability: Prompt Quality, Task Completion, Accuracy, Reasoning.
- Safety: Prompt Injection, Data Leakage, PII Exposure.
- Security: Authorization, Secrets Handling, API Usage.
- Governance: Auditability, Traceability, Policy Compliance.

For each criterion, the reviewer records a 0–100 score and at least 20 characters of evidence. Evaluation records store the template ID/code/version, reviewer user ID, reason, criterion scores, and evidence in the existing Evaluation.Evidence field. The overall score is the arithmetic mean; an evaluation passes only when the mean and every required criterion score are at least 70. Newer evaluations supersede older results for activation checks.

## Agent activation

Activation requires all of the following:

- Agent is Provisioning and belongs to the authenticated Owner/Super Admin company.
- Model provider, catalog-approved model, and version are configured.
- An Active role profile exists.
- Every required role skill has an AgentSkill row in Active status at or above minimum proficiency. Pending skills do not qualify.
- The latest Capability, Safety, Security, and Governance evaluations all pass.

The system does not turn Pending skills Active during activation. Approve each pending skill separately with genuine validation evidence. Do not enter fabricated evaluation scores, evidence, or model approvals. Review the active AI CEO separately before treating it as execution-ready; its existing Active status does not override missing gates.

## Runtime expectation

Model approval and certification do not simulate a worker. TaskAssignment and AgentTaskQueue can populate when qualified active agents become available and the planner runs. AgentExecution requires a configured trusted worker credential/adapter; outputs, QA, and Deliverables require actual worker-submitted content and independent review. No execution is created by this certification workflow.

Native SQL RLS remains disabled. Do not deploy scripts 16–18 until historical ownership cleanup, assignment/runtime ownership validation, and the full validation script pass.
