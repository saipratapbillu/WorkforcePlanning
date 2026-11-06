# AICompany Workforce Retention Export Design

## Status and decision boundary

**Milestone 1.1-G3 design: COMPLETE FOR INDEPENDENT REVIEW.** This is a proposed
retention/export and reset design, not an authorization to export, create a
backup, alter schema, run a migration, or remove records. No export, backup,
restore, migration, or cleanup was executed for this design.

The G1 audit stop is retained as historical evidence. G2 completed the read-only
workforce/RBAC mapping that G1 had stopped before completing. G3 now makes that
evidence reviewable as a specific export design. Neither G2 nor G3 approves
actual export or cleanup. Owner decisions in this plan remain gates.

## Source identity and evidence

The latest read-only identity/state verification was recorded at
`2026-11-04 14:17:02.3288144 +04:00` (`2026-11-04 10:17:02.3288144 UTC`)
against local SQL Server `YOSLTVBILLU02` (machine `YOSLTVBILLU02`), database
`AICompany`, state `ONLINE`. The connection was made through `LocalHost`; the
database owner, original login, and current login were
`POM\Vemanasai.Billu`. That principal is `sysadmin`. It was used for SELECT-only
catalog and data inspection and must not be used for a future export or cleanup.
The connection was disconnected after inspection.

The G2 table/row inventory and workforce record queries are dated
`2026-11-04`; their individual SQL execution timestamps were not retained.
The timestamp above is specifically the later database identity/state
reverification, not a claim that every row count was remeasured at that instant.

The instance was identified in the audit as SQL Server 2022 Developer
`16.0.1000.6`. The repository's local target is `localhost/AICompany`. This
confirms the endpoint and configured development target, but does not prove
data provenance or authorize destructive work. Reconfirm machine, server,
database, state, owner, login, and privileges before any separately authorized
operation; stop on mismatch. Use a dedicated approved least-privilege identity.

Observed inventory: 72 user tables (all `dbo`), 1,135 rows, 120 enabled and
trusted foreign keys, 72 primary keys, 16 unique constraints, 45 check
constraints, 119 indexes, 35 empty tables, no user views, table triggers, or
temporal tables. The completed G2 catalog pass found one identity column,
`AuditLog.AuditLogID`; an earlier preliminary G1 count of six identity columns
was superseded by the deeper catalog inspection. No SQL RLS policies were
found. A migration-history table was not found, so exact migration application
history cannot be proven from the catalog.

## Retention scope and exact proposed allowlist

The default workforce package preserves source records and primary keys from
the eight populated tables listed below. No `SELECT *` is part of the design.
The lists are based on the verified table definitions. Include every listed
column, including null values and status values; preserve identifiers exactly.
Do not parse and rewrite JSON, normalize text, regenerate identifiers, or
silently reconcile divergent fields.

| Export order | Table | Rows | Primary key | Exact included columns | Dependencies and validation |
|---:|---|---:|---|---|---|
| 1 | `dbo.Company` | 1 | `CompanyID` | `CompanyID, CompanyName, Status, CreatedAtUtc` | Reference parent. Preserve PK and all values. |
| 2 | `dbo.Department` | 22 | `DepartmentID` | `DepartmentID, CompanyID, DepartmentName, Status, CreatedAtUtc` | FK `CompanyID -> Company.CompanyID`. Validate every non-null parent. |
| 3 | `dbo.Position` | 64 | `PositionID` | `PositionID, DepartmentID, PositionName, Grade, Status` | FK `DepartmentID -> Department.DepartmentID`. Validate every non-null parent. |
| 4 | `dbo.Skill` | 38 | `SkillID` | `SkillID, Name, Description, Version, InputSchema, OutputSchema, RequiredTools, RequiredPermissions, RiskLevel, Owner, Status` | Reference parent for AgentSkill and AppUserSkill; the latter is outside the package. Preserve empty schema/tool/permission strings exactly. |
| 5 | `dbo.WorkforceRoleProfile` | 56 | `RoleCode` | `RoleCode, PositionName, DepartmentName, Grade, JobDescription, ResponsibilitiesJson, RequiredSkillsJson, ProfileVersion, Status, CreatedAtUtc, ReportsToRoleCode, OrgLayer, ApprovalScope, QualityGatesJson, MaxRecommendedAutonomy` | `ReportsToRoleCode` is text-only, not an FK. Preserve it exactly; validate values against the profile-code set without rewriting them. |
| 6 | `dbo.Agent` | 56 | `AgentID` | `AgentID, CompanyID, DepartmentID, PositionID, AgentName, AgentType, Grade, ManagerAgentID, DirectorAgentID, JobDescription, ResponsibilitiesJson, SecurityRoleID, ApprovalAuthorityID, Model, ModelVersion, PromptVersion, AutonomyLevel, RiskLevel, CostLimitMonthly, TokenLimitDaily, ConcurrentTaskLimit, CurrentWorkload, CreatedDate, LastEvaluationDate, ExpiryDate, Status, CreatedBy, ModifiedDate, ModifiedBy, WorkforceRoleCode, ModelProvider` | FKs to Company, Department, Position, WorkforceRoleProfile and self via ManagerAgentID. DirectorAgentID is not FK-enforced. SecurityRoleID and ApprovalAuthorityID are null in all 56 rows and are not FK-enforced. Validate populated references; preserve nulls and source values. |
| 7 | `dbo.AgentSkill` | 102 | `(AgentID, SkillID)` | `AgentID, SkillID, Proficiency, Status` | FKs to Agent and Skill. All 102 current rows have `Status=Pending`; preserve status and proficiency, do not imply certification. |
| 8 | `dbo.Role` | 3 | `RoleID` | `RoleID, RoleName, RoleLevel, RoleCode, IsActive` | Separate application RBAC catalog. Preserve the three legacy rows verbatim; do not insert canonical rows or infer user assignments. |

### Empty mapping catalogs: schema/count metadata only

The following objects have zero records. Record their schemas and zero counts in
the manifest; there are no mapping/catalog rows to export. Retain the schema in
future design where appropriate, subject to versioned migration review.

| Table | Rows | Primary key | Verified columns |
|---|---:|---|---|
| `dbo.AgentPermission` | 0 | `(AgentID, PermissionID, Environment)` | `AgentID, PermissionID, Environment, ValidFrom, ValidTo, Status` |
| `dbo.AgentTool` | 0 | `(AgentID, ToolID)` | `AgentID, ToolID, ValidFrom, ValidTo, Status` |
| `dbo.AgentKnowledgeAccess` | 0 | `(AgentID, KnowledgeSourceID)` | `AgentID, KnowledgeSourceID, AccessLevel, ValidTo` |
| `dbo.Permission` | 0 | `PermissionID` | `PermissionID, PermissionName, ResourceType, Action, RiskLevel` |
| `dbo.Tool` | 0 | `ToolID` | `ToolID, ToolName, ToolType, Endpoint, RiskLevel, Status, RequiresApproval` |
| `dbo.KnowledgeSource` | 0 | `KnowledgeSourceID` | `KnowledgeSourceID, SourceName, SourceType, Uri, Classification, Owner, Status` |

The catalogs are empty, and there is no `RolePermission` table. Do not infer
permission assignments from role names, agent titles, profile text, code
constants, tool suggestions, or SQL Server grants. If a later approved manifest
adds data-bearing columns/tables, regenerate and review its allowlist first.

### Explicit exclusions

- No `AppUser` rows, authentication fields, password hashes, user PII, or
  AppUser-to-Role assignments are part of the workforce package.
- No credentials, API keys, access tokens, secret values, secret references,
  or authentication material are included. Do not include
  `AgentRuntimeCredential` or runtime/provider configuration values merely
  because they are empty in this snapshot.
- No `AgentActivationBlocker`, audit, approval, requirement, runtime,
  project/task, or operational rows are silently folded into the default
  workforce package. Those require the owner decisions below.
- `Agent.SecurityRoleID` and `Agent.ApprovalAuthorityID` are included only as
  current source fields (all null); they are not interpreted as functional
  workforce roles.

## Agent, role, responsibility, and hierarchy preservation

There are 56 Agent rows and 56 matching `WorkforceRoleProfile` rows. Each
`Agent.WorkforceRoleCode` currently resolves to `WorkforceRoleProfile.RoleCode`
and is backed by an FK. That is the verified functional-role relationship.
Agent functional roles (`WorkforceRoleCode`), organizational reporting
(`ManagerAgentID`, `DirectorAgentID`, `ReportsToRoleCode`), application RBAC
(`Role` / `AppUser.RoleID`), and approval authority (`ApprovalAuthorityID`)
are distinct concepts. Do not merge them or infer between them.

Preserve Agent and profile values as separate records. Both carry job/responsibility
data, and the current AI CEO values conflict:

| Source field | Exact current value |
|---|---|
| `Agent.ResponsibilitiesJson` for AI CEO | `["Requirement intake","Delegation","Portfolio monitoring","Escalation"]` |
| `WorkforceRoleProfile.ResponsibilitiesJson` for `AI_CEO` | `["Assess business value and strategic fit","Prioritize portfolio recommendations","Record assumptions, evidence, risks, and open questions"]` |
| `Agent.JobDescription` for AI CEO | `Executive orchestration only` |
| `WorkforceRoleProfile.JobDescription` for `AI_CEO` | `Owns advisory business strategy, portfolio assessment, and requirement prioritization. Produces a traceable recommendation; cannot approve its own assessment or authorize delivery.` |

Both the Agent and profile JobDescription fields also differ for AI CEO. The
profile's `RequiredSkillsJson` is
`[{"name":"RequirementAnalysis","minimum_proficiency":4},{"name":"PortfolioManagement","minimum_proficiency":4}]`;
Agent has no `RequiredSkillsJson` column. Preserve the two responsibility
representations and job descriptions verbatim. Proposed owner decision: choose
the future authoritative authoring source and an explicit reconciliation process;
until approved, consumers must not silently overwrite either representation.

All 56 agents have populated descriptions and profile responsibilities. One
agent is `Active` (AI CEO); 55 are `Provisioning`. All have high risk and
unconfigured model/version values and no configured provider. There are 102
AgentSkill assignments across 55 agents, all `Pending`. There are no current
AgentPermission, AgentTool, or AgentKnowledgeAccess assignments. Six agents
have four open activation blockers each (24 total): AI Business Analyst,
AI Delivery Lead, AI QA Engineer, AI Security Engineer, HR Workforce
Coordinator, and Software Developer. The blocker codes are
`APPROVED_MODEL_IS_NOT_CONFIGURED`,
`APPROVED_PROVIDER_IS_NOT_CONFIGURED`,
`MODEL_VERSION_IS_NOT_CONFIGURED`, and `PASSED_EVALUATIONS_MISSING`.

55 agents have a ManagerAgentID; six have DirectorAgentID. Populated manager
and director IDs resolve today. ManagerAgentID has an FK; DirectorAgentID
does not. AI CEO currently reports to AI Chief of Staff, an owner-review item.
The profile's ReportsToRoleCode is text-only. Preserve the source graph and
unusual values; do not repair the hierarchy during export.

## Application RBAC findings

The live database has these three active legacy roles:

| RoleID | RoleCode | RoleName | Active | AppUser count (not exported) |
|---|---|---|---|---:|
| `F633127A-2591-446C-A3E7-EF81A9634D65` | `USER` | Business User | Yes | 31 |
| `E825E550-1F5F-4CFC-8576-223EF662E952` | `MANAGER` | People Manager | Yes | 6 |
| `898A231D-E4B1-46D1-9FB0-AE1EC2D6FC84` | `SUPER_ADMIN` | Super Admin | Yes | 2 |

RoleLevel values were not re-emitted in this report; the export must preserve
the database values exactly. All 39 AppUser RoleID values resolved during the
audit, but there is no physical SQL FK from AppUser.RoleID to Role and RoleCode
has no unique constraint. The ORM relationship is not a substitute for those
physical constraints.

`app/security/roles.py` defines canonical application roles
`BUSINESS_USER`, `APPROVER`, `EXECUTIVE`, `WORKFORCE_MANAGER`, and
`PLATFORM_OWNER`; its aliases are `USER -> BUSINESS_USER`,
`MANAGER/DEPARTMENT_HEAD/ADMIN -> WORKFORCE_MANAGER`, and
`OWNER/SUPER_ADMIN -> PLATFORM_OWNER`. The live database contains none of
the five canonical rows. Migration 23 would create/update those rows and
nullable Agent organizational columns. The live schema has `CompanyID` and
`DepartmentID` as NOT NULL and `PositionID` as nullable; no migration-history
table was found. Do not infer migration history or rerun migration 23 as part
of this design.

There is no RolePermission table and Permission has zero rows. No role-
permission assignment is verified. Code-defined role checks and SQL database
grants are separate authorization layers and are not exported as a fabricated
application role-permission matrix.

## Tables requiring owner decision

These are not in the default export allowlist or cleanup authorization. The
counts/purpose/dependencies below are from the 2026-11-04 read-only inventory.
Their disposition requires a named data/business/security/legal owner.

| Table(s) and rows | Purpose/evidence and dependencies | Consequence / proposed treatment | Owner decision |
|---|---|---|---|
| `AgentActivationBlocker` 24 | Open provisioning blockers; FK to retained Agent. | Removing loses activation evidence and readiness explanation. Preserve or export to a separately approved evidence package; do not treat as runtime noise. | Workforce/security owner to decide retention and how blockers affect future activation. |
| `AuditLog` 257 | Audit evidence; no FKs. | Deletion may violate security, legal, or investigation retention. Keep outside workforce export and retain pending policy. | Security/legal records owner to approve retention period and disposition. |
| `Approval` 7; `OrganizationBootstrapRun` 1 | Approval rows have no FK constraints. BootstrapRun has FKs to Approval, Company, Requirement. | Removing can erase human decision/bootstrap provenance; bootstrap row also prevents removing referenced parent rows. | Business/security owner to decide preservation; inspect provenance in a separately authorized review. |
| `WorkforceRequest` 36 | Links to Agent, Project, Task, WorkforceRoleProfile. | Retaining history pulls operational/project parents into scope; deleting may erase recruitment/provisioning decisions. | Workforce owner to decide whether requests are evidence or disposable operations. |
| `Requirement` 14; `RequirementAssessment` 8; `RequirementAssessmentDepartment` 45; `RequirementSkill` 38; `WorkflowExecution` 0 | Requirement links to AppUser; Assessment links to Agent and Requirement; department/skill tables link to assessment/department and requirement/skill; WorkflowExecution links to requirement, assessment, workflow. | Deleting may destroy submitted business scope and AI/human assessment evidence. These rows also have downstream project/bootstrap relationships. | Product/business and audit owners to decide whether to retain or remove each chain. |
| `AppUser` 39; `AppUserAvailability` 18; `AppUserCertification` 6; `AppUserSkill` 35 | Human accounts/role assignments, availability, certifications, skills; AppUser has self-FK ManagerUserID; AppUserSkill also references retained Skill. | Exclude account/authentication data from workforce export. Deletion affects identity, ownership, approval, audit attribution, and workforce evidence. PasswordHash must never be exported. | Identity/privacy and business owners to define account/PII retention separately. |
| `Notification` 73 | Recipient-linked user records, FK to AppUser. | Can contain user-facing history and references; removal must follow records policy and AppUser disposition. | Product/privacy owner to decide retention. |
| `ResourceAssignmentRecommendation` 5; `ProjectTaskAssignment` 2 | Recommendation references AppUser/ProjectDeliveryTask; assignment references AppUser, ProjectDeliveryTask, Recommendation. | Could be approval/provenance evidence; deletion must be child-first and should not be inferred from “operational.” | Workforce/project owner to decide whether recommendation/approval trail is retained. |
| `EscalationPolicyProfile` 6; `EvaluationTemplate` 4; `EvaluationTemplateCriterion` 13; `GovernanceGateProfile` 15; `Policy` 0; `PolicyViolation` 0; `SecurityIncident` 0; `Workflow` 0 | Governance/security configuration or evidence. EvaluationTemplateCriterion references EvaluationTemplate; PolicyViolation references Policy, Agent, Task; SecurityIncident references Agent and Project. | Preserve schema/configuration and review even when empty. Evidence-bearing tables may be subject to retention obligations. | Security/governance owner to classify and approve any future migration or removal. |
| `AIModelApproval` 0; `AIModelCatalog` 0; `AIModelProvider` 0; `ExecutionAdapterConfig` 0; `ExecutionAdapterHealthCheck` 0; `AgentRuntimeCredential` 0 | Empty provider/model/runtime configuration; several point to AppUser or each other. | Keep schema under review; do not export secret references or assume these tables are disposable because empty. | Platform/security owner to approve schema retention and secret-handling policy. |
| All other non-empty records not in default allowlist | The inventory identifies operational, planning, and shared reference records. | Use the per-table disposition and FK graph below; do not execute a cleanup based on classification alone. | Data owner approval remains required. |

## Full table inventory and proposed classification

`EMPTY` is a row-count fact, not a deletion decision. Where a table is empty,
its proposed disposition appears after `EMPTY /`. `REBUILD` is not assigned
to any current table: tenant ownership/RLS or schema redesign must be performed
through separately reviewed versioned migrations, not ad hoc replacement.

| Table | Rows | Proposed class |
|---|---:|---|
| Agent | 56 | RETAIN |
| AgentActivationBlocker | 24 | REVIEW |
| AgentCost | 0 | EMPTY / REMOVE-CANDIDATE |
| AgentExecution | 0 | EMPTY / REMOVE-CANDIDATE |
| AgentExecutionOutput | 0 | EMPTY / REMOVE-CANDIDATE |
| AgentKnowledgeAccess | 0 | EMPTY / RETAIN-SCHEMA |
| AgentMessage | 0 | EMPTY / REMOVE-CANDIDATE |
| AgentPerformance | 0 | EMPTY / REMOVE-CANDIDATE |
| AgentPermission | 0 | EMPTY / RETAIN-SCHEMA |
| AgentRuntimeCredential | 0 | EMPTY / REVIEW |
| AgentRuntimeDefect | 0 | EMPTY / REMOVE-CANDIDATE |
| AgentRuntimeEscalation | 0 | EMPTY / REMOVE-CANDIDATE |
| AgentRuntimeEvent | 0 | EMPTY / REMOVE-CANDIDATE |
| AgentSkill | 102 | RETAIN |
| AgentTaskQueue | 0 | EMPTY / REMOVE-CANDIDATE |
| AgentTool | 0 | EMPTY / RETAIN-SCHEMA |
| AIModelApproval | 0 | EMPTY / REVIEW |
| AIModelCatalog | 0 | EMPTY / REVIEW |
| AIModelProvider | 0 | EMPTY / REVIEW |
| Approval | 7 | REVIEW |
| AppUser | 39 | REVIEW |
| AppUserAvailability | 18 | REVIEW |
| AppUserCertification | 6 | REVIEW |
| AppUserSkill | 35 | REVIEW |
| AuditLog | 257 | REVIEW |
| Budget | 0 | EMPTY / REMOVE-CANDIDATE |
| Company | 1 | RETAIN |
| Decision | 0 | EMPTY / REMOVE-CANDIDATE |
| Deliverable | 0 | EMPTY / REMOVE-CANDIDATE |
| Department | 22 | RETAIN |
| EscalationPolicyProfile | 6 | REVIEW |
| Evaluation | 0 | EMPTY / REVIEW |
| EvaluationTemplate | 4 | REVIEW |
| EvaluationTemplateCriterion | 13 | REVIEW |
| ExecutionAdapterConfig | 0 | EMPTY / REVIEW |
| ExecutionAdapterHealthCheck | 0 | EMPTY / REVIEW |
| GovernanceGateProfile | 15 | REVIEW |
| Issue | 0 | EMPTY / REMOVE-CANDIDATE |
| KnowledgeSource | 0 | EMPTY / RETAIN-SCHEMA |
| Notification | 73 | REVIEW |
| OrganizationBootstrapRun | 1 | REVIEW |
| Permission | 0 | EMPTY / RETAIN-SCHEMA |
| Policy | 0 | EMPTY / REVIEW |
| PolicyViolation | 0 | EMPTY / REVIEW |
| Position | 64 | RETAIN |
| Project | 13 | REMOVE-CANDIDATE |
| ProjectAgent | 0 | EMPTY / REMOVE-CANDIDATE |
| ProjectDeliveryTask | 12 | REMOVE-CANDIDATE |
| ProjectEpic | 7 | REMOVE-CANDIDATE |
| ProjectFeature | 7 | REMOVE-CANDIDATE |
| ProjectSprint | 9 | REMOVE-CANDIDATE |
| ProjectStory | 10 | REMOVE-CANDIDATE |
| ProjectStoryDependency | 4 | REMOVE-CANDIDATE |
| ProjectTask | 0 | EMPTY / REMOVE-CANDIDATE |
| ProjectTaskAssignment | 2 | REMOVE-CANDIDATE |
| Requirement | 14 | REVIEW |
| RequirementAssessment | 8 | REVIEW |
| RequirementAssessmentDepartment | 45 | REVIEW |
| RequirementSkill | 38 | REVIEW |
| ResourceAssignmentRecommendation | 5 | REVIEW |
| Risk | 0 | EMPTY / REMOVE-CANDIDATE |
| Role | 3 | RETAIN |
| SecurityIncident | 0 | EMPTY / REVIEW |
| Skill | 38 | RETAIN |
| Task | 49 | REMOVE-CANDIDATE |
| TaskAssignment | 0 | EMPTY / REMOVE-CANDIDATE |
| TaskDependency | 36 | REMOVE-CANDIDATE |
| Tool | 0 | EMPTY / RETAIN-SCHEMA |
| Workflow | 0 | EMPTY / REVIEW |
| WorkflowExecution | 0 | EMPTY / REMOVE-CANDIDATE |
| WorkforceRequest | 36 | REVIEW |
| WorkforceRoleProfile | 56 | RETAIN |

`REMOVE-CANDIDATE` means only that a table is a possible reset target after
retention, legal, and business approvals. It does not assert that every current
row is synthetic or disposable. Verify record provenance and the source
database's classification before any removal.

## Foreign-key dependency graph and cleanup strategy

The graph is the complete table-level grouping of the catalog's 120 FK
constraints (child table -> referenced parent table). Multiple constraints
between a pair are grouped here; a future approved migration/cleanup package
must use the actual constraint and column metadata, not this summary graph.
All observed FKs were enabled and trusted. Self-references exist on Agent,
AppUser, and Task; no multi-table FK cycle was found.

```text
dbo.Agent -> dbo.Agent, dbo.Company, dbo.Department, dbo.Position, dbo.WorkforceRoleProfile
dbo.AgentActivationBlocker -> dbo.Agent
dbo.AgentCost -> dbo.Agent, dbo.Task
dbo.AgentExecution -> dbo.Agent, dbo.AgentTaskQueue, dbo.Task
dbo.AgentExecutionOutput -> dbo.AgentExecution
dbo.AgentKnowledgeAccess -> dbo.Agent, dbo.KnowledgeSource
dbo.AgentMessage -> dbo.Agent, dbo.Project, dbo.Task
dbo.AgentPerformance -> dbo.Agent
dbo.AgentPermission -> dbo.Agent, dbo.Permission
dbo.AgentRuntimeCredential -> dbo.Agent
dbo.AgentRuntimeDefect -> dbo.Agent, dbo.AgentExecution, dbo.Task, dbo.WorkforceRoleProfile
dbo.AgentRuntimeEscalation -> dbo.Agent, dbo.AgentTaskQueue, dbo.Task
dbo.AgentRuntimeEvent -> dbo.Agent, dbo.AgentExecution, dbo.AgentTaskQueue, dbo.Task
dbo.AgentSkill -> dbo.Agent, dbo.Skill
dbo.AgentTaskQueue -> dbo.Agent, dbo.Task
dbo.AgentTool -> dbo.Agent, dbo.Tool
dbo.AIModelApproval -> dbo.AIModelCatalog, dbo.AppUser
dbo.AIModelCatalog -> dbo.AIModelProvider, dbo.AppUser
dbo.AIModelProvider -> dbo.AppUser
dbo.AppUser -> dbo.AppUser
dbo.AppUserAvailability -> dbo.AppUser
dbo.AppUserCertification -> dbo.AppUser
dbo.AppUserSkill -> dbo.AppUser, dbo.Skill
dbo.Budget -> dbo.Department, dbo.Project
dbo.Decision -> dbo.Project
dbo.Deliverable -> dbo.Project, dbo.Task
dbo.Department -> dbo.Company
dbo.Evaluation -> dbo.Agent, dbo.Task
dbo.EvaluationTemplateCriterion -> dbo.EvaluationTemplate
dbo.ExecutionAdapterConfig -> dbo.AIModelCatalog, dbo.AppUser
dbo.ExecutionAdapterHealthCheck -> dbo.AppUser, dbo.ExecutionAdapterConfig
dbo.Issue -> dbo.AppUser, dbo.Project
dbo.Notification -> dbo.AppUser
dbo.OrganizationBootstrapRun -> dbo.Approval, dbo.Company, dbo.Requirement
dbo.PolicyViolation -> dbo.Agent, dbo.Policy, dbo.Task
dbo.Position -> dbo.Department
dbo.Project -> dbo.AppUser, dbo.Requirement
dbo.ProjectAgent -> dbo.Agent, dbo.Project
dbo.ProjectDeliveryTask -> dbo.ProjectStory
dbo.ProjectEpic -> dbo.AppUser, dbo.Project
dbo.ProjectFeature -> dbo.ProjectEpic
dbo.ProjectSprint -> dbo.Project
dbo.ProjectStory -> dbo.ProjectFeature, dbo.ProjectSprint
dbo.ProjectStoryDependency -> dbo.ProjectStory
dbo.ProjectTaskAssignment -> dbo.AppUser, dbo.ProjectDeliveryTask, dbo.ResourceAssignmentRecommendation
dbo.Requirement -> dbo.AppUser
dbo.RequirementAssessment -> dbo.Agent, dbo.Requirement
dbo.RequirementAssessmentDepartment -> dbo.Department, dbo.RequirementAssessment
dbo.RequirementSkill -> dbo.Requirement, dbo.Skill
dbo.ResourceAssignmentRecommendation -> dbo.AppUser, dbo.ProjectDeliveryTask
dbo.Risk -> dbo.Project
dbo.SecurityIncident -> dbo.Agent, dbo.Project
dbo.Task -> dbo.Agent, dbo.AppUser, dbo.Project, dbo.Task
dbo.TaskAssignment -> dbo.Agent, dbo.Task
dbo.TaskDependency -> dbo.Task
dbo.WorkflowExecution -> dbo.Requirement, dbo.RequirementAssessment, dbo.Workflow
dbo.WorkforceRequest -> dbo.Agent, dbo.Project, dbo.Task, dbo.WorkforceRoleProfile
```

### Per-candidate FK and significance map

“Children” are direct FK-referencing tables that must be resolved first;
“parents” are direct referenced tables. This lists all 28
REMOVE-CANDIDATE tables and their direct table-level dependencies. It does not
prove that any row is disposable. Business/legal/security significance was not
established by schema inspection; an owner must classify the actual records
before removal. Parent tables in RETAIN must never be deleted as a side effect.

| Candidate | Rows | Direct FK children (resolve/delete first) | Direct FK parents (retain or separately resolve) | Consequence / gate |
|---|---:|---|---|---|
| AgentCost | 0 | — | Agent, Task | Cost history; currently empty. Recount and obtain owner approval. |
| AgentExecution | 0 | AgentExecutionOutput, AgentRuntimeDefect, AgentRuntimeEvent | Agent, AgentTaskQueue, Task | Execution evidence; child output/event/defect records precede it. |
| AgentExecutionOutput | 0 | — | AgentExecution | Output/evidence history; currently empty. |
| AgentMessage | 0 | — | Agent, Project, Task | May contain work/evidence content; classify before removal. |
| AgentPerformance | 0 | — | Agent | Workforce evaluation evidence; currently empty. |
| AgentRuntimeDefect | 0 | — | Agent, AgentExecution, Task, WorkforceRoleProfile | Defect/governance evidence; currently empty. |
| AgentRuntimeEscalation | 0 | — | Agent, AgentTaskQueue, Task | Escalation evidence; currently empty. |
| AgentRuntimeEvent | 0 | — | Agent, AgentExecution, AgentTaskQueue, Task | Runtime/audit evidence; currently empty. |
| AgentTaskQueue | 0 | AgentExecution, AgentRuntimeEscalation, AgentRuntimeEvent | Agent, Task | Queue state; resolve all runtime descendants first. |
| Budget | 0 | — | Department, Project | Financial/planning record class; currently empty, owner disposition required. |
| Decision | 0 | — | Project | Project decision record class; currently empty, owner disposition required. |
| Deliverable | 0 | — | Project, Task | Delivery evidence; currently empty, owner disposition required. |
| Issue | 0 | — | AppUser, Project | May contain user/project issue history; classify before removal. |
| Project | 13 | AgentMessage, Budget, Decision, Deliverable, Issue, ProjectAgent, ProjectEpic, ProjectSprint, Risk, SecurityIncident, Task | AppUser, Requirement | Removal erases project scope and has many child dependencies; classify every project and child first. |
| ProjectAgent | 0 | — | Agent, Project | Project/workforce association; currently empty. Agent is retained. |
| ProjectDeliveryTask | 12 | ProjectTaskAssignment, ResourceAssignmentRecommendation | ProjectStory | Assignment/recommendation children first; review recommendations separately. |
| ProjectEpic | 7 | ProjectFeature | AppUser, Project | Project-plan hierarchy; deleting removes planning structure and may affect child features. |
| ProjectFeature | 7 | ProjectStory | ProjectEpic | Project-plan hierarchy; stories must be resolved first. |
| ProjectSprint | 9 | ProjectStory | Project | Sprint planning/history; stories must be resolved first. |
| ProjectStory | 10 | ProjectDeliveryTask, ProjectStoryDependency | ProjectFeature, ProjectSprint | Story/dependency and delivery-task children first. |
| ProjectStoryDependency | 4 | — | ProjectStory (both endpoints) | Dependency edge; remove before either referenced story. |
| ProjectTask | 0 | — | — | Legacy table has no catalog FK edges; confirm application references before any disposition. |
| ProjectTaskAssignment | 2 | — | AppUser, ProjectDeliveryTask, ResourceAssignmentRecommendation | Assignment/approval provenance; owner decision and child-first handling required. |
| Risk | 0 | — | Project | Risk records may be governance evidence; currently empty. |
| Task | 49 | AgentCost, AgentExecution, AgentMessage, AgentRuntimeDefect, AgentRuntimeEscalation, AgentRuntimeEvent, AgentTaskQueue, Deliverable, Evaluation, PolicyViolation, TaskAssignment, TaskDependency, WorkforceRequest, Task (self-reference) | Agent, AppUser, Project, Task (self-reference) | Removal affects operational work and referenced agent/project history; resolve every dependent and task hierarchy first. |
| TaskAssignment | 0 | — | Agent, Task | Workforce assignment evidence; currently empty. |
| TaskDependency | 36 | — | Task (both endpoints) | Task graph edges; remove before referenced tasks. |
| WorkflowExecution | 0 | — | Requirement, RequirementAssessment, Workflow | Workflow execution evidence; currently empty and parent records require separate disposition. |

### Proposed future child-first deletion phases (not executable SQL)

Do not begin these phases until the data owners approve per-table disposition,
the retention manifest, a full backup and restore, and a cleanup change plan.
Preflight must fail closed on target mismatch, unexpected retained records,
schema drift, or an unapproved row set. Keep constraints enabled; do not use
TRUNCATE or disable constraints to bypass dependencies.

1. **Resolve REVIEW tables first.** Either preserve them or obtain explicit
   disposition. In particular, do not remove AgentActivationBlocker,
   AuditLog, Approval, OrganizationBootstrapRun, WorkforceRequest,
   Requirement/assessment chains, AppUser evidence, or recommendations by
   default.
2. **Runtime/task descendants:** if approved and non-empty at execution time,
   clear AgentExecutionOutput, AgentRuntimeEvent, and AgentRuntimeDefect before
   AgentExecution; clear AgentRuntimeEscalation and other queue children before
   AgentTaskQueue; then clear AgentExecution, AgentRuntimeEvent,
   AgentRuntimeDefect, AgentRuntimeEscalation, AgentCost, AgentMessage,
   AgentPerformance, Evaluation, PolicyViolation, TaskAssignment,
   TaskDependency, Deliverable, WorkforceRequest, and AgentTaskQueue before
   their referenced Task/Agent/Project parents. Respect Task's self-parent and
   TaskDependency edges. Resolve each REVIEW row by owner decision before
   deletion. Recount all rows at execution time.
3. **Project plan descendants:** after separate owner disposition, clear
   ProjectStoryDependency and ProjectTaskAssignment before their referenced
   ProjectStory, ProjectDeliveryTask, and ResourceAssignmentRecommendation
   rows. Then clear ResourceAssignmentRecommendation before
   ProjectDeliveryTask, ProjectDeliveryTask before ProjectStory, and
   ProjectStory before ProjectFeature / ProjectSprint. Clear ProjectFeature
   before ProjectEpic, then ProjectEpic and ProjectSprint before Project.
   ProjectTaskAssignment references both ProjectDeliveryTask and
   ResourceAssignmentRecommendation; ProjectDeliveryTask references
   ProjectStory, not ResourceAssignmentRecommendation. Also resolve
   ProjectAgent and remaining approved project children (Budget, Decision,
   Deliverable, Issue, Risk, SecurityIncident) before Project. Do not delete a
   parent while any retained or unresolved child row remains.
4. **Requirement evidence chain:** only after approval, clear
   RequirementAssessmentDepartment and RequirementSkill before
   RequirementAssessment / Requirement; clear WorkflowExecution before its
   Requirement, RequirementAssessment, and Workflow parents. Preserve
   OrganizationBootstrapRun until separately approved because it references
   Approval, Company, and Requirement. No physical FK exists from Approval to
   Requirement despite the Approval.RequirementID column.
5. **Application-user dependent records:** only under a separately approved
   identity-retention operation, clear user-related dependents (including
   Notification, AppUserAvailability, AppUserCertification, AppUserSkill,
   model and adapter records, project/requirement ownership references) before
   AppUser. Account removal is outside this workforce reset design and must not
   cascade into the retained Role catalog by assumption.
6. **Retained-agent boundary:** do not delete Agent, AgentSkill,
   WorkforceRoleProfile, Skill, Company, Department, Position, or Role in the
   operational reset. All children of Agent/Skill/profile that are REVIEW or
   REMOVE-CANDIDATE must be separately dispositioned first. Do not delete
   `AgentActivationBlocker` just to make Agent deletion possible; Agent is
   retained.
7. **Postcondition:** re-count all 72 tables, verify all retained PK sets and
   FKs, and confirm no protected rows were affected. Reseeding is not expected
   for the retained package. If a future approved target includes an identity
   column, record its pre/post identity state explicitly; never reseed
   `AuditLog.AuditLogID` without a separate approved data/identity decision.

Because the graph includes many review tables and non-FK business references,
this sequence is a dependency strategy, not proof that deleting a particular
row is safe. No cleanup script is supplied by this milestone.

## Export format, restore, and validation design

The future package should contain: (1) a signed/immutable manifest with source
identity, snapshot time, schema/version fingerprint, table allowlist, row
counts, PK counts, column SQL types/nullability, FK metadata, and exclusions;
(2) one typed data file per allowlisted table; and (3) a validation report.
Use UTF-8 with explicit type-aware serialization, preserve nulls distinctly
from empty strings, GUID identity, and datetime precision. For JSON-valued
columns, preserve the original SQL string as stored; do not parse/reserialize.
Protect files at rest and in transit with approved encryption and restrictive
ACLs. Never put the export in source control or an unapproved shared location.

Proposed future export/import ordering is the numbered allowlist order above:
Company -> Department -> Position; Skill and WorkforceRoleProfile before Agent;
Agent before AgentSkill; Role is an independent catalog. Restore in the same
parent-before-child order, preserving original PK values. Do not include AppUser
rows or fabricate role assignments. Empty mapping catalogs produce metadata
and zero counts only.

Before any destructive change, require a **separate full database backup** in an
approved, encrypted, access-controlled destination outside the source database
volume and source control. Capture backup identity/time and database metadata;
verify media (`RESTORE VERIFYONLY` where applicable) and, more importantly,
restore it into an isolated non-production database and run integrity/count
checks. A successful media verification alone is not a restore test. Backup
retention, access, and disposal require owner approval. Do not create the backup
in this milestone.

Future restore acceptance checks:

1. Reconfirm exact source and isolated restore-target identities; fail on a
   mismatch. Never restore over AICompany or another unclassified database.
2. Compare manifest row counts and exact primary-key sets for every exported
   table; verify no unexpected columns or tables entered the package.
3. Validate all exported FK edges, including each agent's
   WorkforceRoleCode/profile, Company/Department/Position, manager and director
   links, and AgentSkill links. Report text-only ReportsToRoleCode resolution
   separately from FK integrity.
4. Compare all source/export/restore values with deterministic typed hashes or
   exact value comparison; preserve nulls, original JSON strings, statuses,
   role codes, and all original IDs. Explicitly compare both AI CEO JSON
   values independently.
5. Scan the package and logs for forbidden authentication material, password
   hashes, credential values, API keys, access tokens, and secret references;
   reject the package on a match. Avoid logging field values during this scan.
6. Reconcile exported and restored counts and hashes and retain the signed
   validation report with the package under the approved retention policy.
7. A successful isolated restore test is required before human approval of
   any destructive cleanup; it has not been run.

## Multi-tenant/RLS and versioned migration implications

No user table currently has authoritative TenantID or OrganizationID. Existing
CompanyID and DepartmentID are not tenant ownership proof. Agent
SecurityRoleID and ApprovalAuthorityID are null and cannot establish worker,
reviewer, or approver identity. No SQL Server RLS policy was found in the
verified catalog. Future tenant ownership, parent/child consistency,
worker/reviewer identity, least-privilege reaper scope, and evidence/cost
provenance require explicitly designed and reviewed versioned migrations.
Do not invent tenant assignments or implement RLS in the export/reset work.

Migration 23's canonical role and Agent nullability state is not safely
inferable from a missing migration ledger. Compare live schema, data, scripts,
and deployment records with the DBA before deciding migration order. Do not
modify role records or apply migrations as part of this plan.

## Risks, rollback, and outstanding approvals

- Data provenance is not established by the `AICompany` name or local host.
- The inspecting login is sysadmin; it is not acceptable for future export or
  cleanup execution.
- The current source has no verified backup or restore. A backup/export is not
  claimed to exist or be valid.
- The AI CEO Agent/profile responsibility and job-description fields diverge;
  preserve both until an owner rules.
- The AI CEO reports to AI Chief of Staff; 55 ManagerAgentID links and six
  DirectorAgentID links resolve, but director links lack FK enforcement.
- All 102 AgentSkill assignments spanning 55 agents are pending, not proof of
  approved proficiency. Provisioning blockers and unconfigured AI
  model/provider state require separate readiness decisions.
- AppUser, audit, approval, bootstrap, request, requirement, recommendation,
  notification, and governance records require privacy, legal, business, or
  security owner decisions.
- Role mappings between legacy database rows and canonical application roles
  are code aliases, not persisted role-permission evidence. Do not export
  credentials or infer missing grants.
- `AppUser.RoleID` has no SQL FK and RoleCode has no unique constraint.
  DirectorAgentID, ReportsToRoleCode, ApprovalAuthorityID, and SecurityRoleID
  also lack the enforcement needed to prove every conceptual relationship.
- No multi-tenant boundary is available in the schema. A data reset cannot
  establish tenant isolation.

Before any later destructive task: approve the allowlist and each REVIEW
disposition; resolve the two AI CEO field conflicts and hierarchy concern;
classify the source data; approve retention/legal/privacy handling; approve a
dedicated least-privilege identity and secured destination; create and restore-
test a full backup; verify the export in a disposable non-production database;
and authorize a separate cleanup implementation with pre/post guards and a
rollback/restore plan. If any gate fails, stop and preserve AICompany.

## Work performed for G3

Inspected the requested Markdown in order where present: README.md,
AI_WORKFORCE_OS_MASTER_PLAN.md (not present), IMPLEMENTATION_STATUS.md,
ARCHITECTURE_DECISIONS.md (not present), AGENT_HANDOFF.md,
RLS_Deployment_Guide.md, Single_Organization_RBAC_Migration_Plan.md, then
related architecture, deployment, runtime-evidence, and workforce docs.
README merge-conflict markers were observed and left unchanged. No equivalent
retention-export plan existed before this document.

Reverified server, machine, target database state, owner, current/original
login, and sysadmin membership with a SELECT-only `master` catalog query; used
SELECT-only schema/record reads against AICompany; then disconnected. No
application test or SQL Server integration test was run. No repository data,
database row, schema, credential, application configuration, backup, export,
migration, or cleanup was changed or created.

## Milestone 1.1-G4 — independent live verification (2026-11-04)

**Outcome: CONDITIONAL PASS.** The current workforce export allowlist and
table-level dependency graph match the live database. G4 corrected the G3
Agent-column nullability statement and project-cleanup narrative above. The
corrected design is technically consistent with the observed schema, but owner
disposition, separate export authorization, and cleanup authorization remain
outstanding. This outcome authorizes no export, backup, restore, or cleanup.

### Identity, method, and current inventory

At `2026-11-04 10:38:03.8854389Z` (`14:38:03.8854389 +04:00`), a
Windows-integrated connection directly to `AICompany` through `LocalHost`
reported server and machine
`YOSLTVBILLU02`, current database `AICompany` ONLINE, database owner
`POM\Vemanasai.Billu`, and matching `ORIGINAL_LOGIN()` /
`SUSER_SNAME()` `POM\Vemanasai.Billu`. `IS_SRVROLEMEMBER('sysadmin')` returned
`1`. This elevated identity was used only for SELECT-only verification; no
SQL-authentication fallback was used. During initial target verification, an
identity-only SELECT probe was also made while connected to `master`; this was
outside the requested AICompany-only connection scope. It read server/database
catalog metadata only. No other user database was accessed. The identity was
subsequently reverified directly in AICompany, and all workforce/schema
verification was performed there. This process deviation is disclosed; recheck
all identity fields before any separately authorized operation.

The full live table-name and row-count inventory was compared with the G3
72-table inventory: all table names and counts match, totaling 1,135 rows and
35 empty tables. Catalog totals are 120 FKs, 72 PKs, 16 unique constraints,
45 checks, 119 indexes, and one user-table identity (`AuditLog.AuditLogID`).
All FKs are enabled and trusted; there are no cross-schema FKs, table triggers,
user views, procedures, temporal tables, or RLS policies. The non-self FK graph
has no cycle; self-references are on Agent, AppUser, and Task. No migration
history table was found. The complete G3 graph and all 28
REMOVE-CANDIDATE dependency rows match the live FK metadata.

There are no user SQL modules. The catalog reports 55 SQL-expression
dependency rows (50 check-constraint entries and five schema-bound self-
references on dbo.Agent, dbo.AgentActivationBlocker, dbo.AgentCost (two), and
dbo.ProjectTaskAssignment); they do not reveal a view/procedure/trigger or
cross-table module dependency. The 45 check constraints remain included in the
catalog totals above.

### Retained allowlist schema comparison

Every documented allowlist column was compared with live `sys.columns`
metadata, including SQL type, nullability, identity status, and PK membership.
All eight table column lists match exactly (80 columns total); no documented
column is missing and no undocumented column is present. No allowlist column
is an identity. A `?` below means nullable; columns without `?` are NOT NULL.

| Table | Live columns in source order: SQL type and nullability |
|---|---|
| Company | `CompanyID uniqueidentifier PK; CompanyName nvarchar(200); Status varchar(20); CreatedAtUtc datetime2(7)` |
| Department | `DepartmentID uniqueidentifier PK; CompanyID uniqueidentifier; DepartmentName nvarchar(150); Status varchar(20); CreatedAtUtc datetime2(7)` |
| Position | `PositionID uniqueidentifier PK; DepartmentID uniqueidentifier; PositionName nvarchar(150); Grade varchar(20); Status varchar(20)` |
| Skill | `SkillID uniqueidentifier PK; Name nvarchar(150); Description nvarchar(1000)?; Version varchar(30); InputSchema nvarchar(MAX)?; OutputSchema nvarchar(MAX)?; RequiredTools nvarchar(MAX)?; RequiredPermissions nvarchar(MAX)?; RiskLevel varchar(20); Owner nvarchar(200); Status varchar(20)` |
| WorkforceRoleProfile | `RoleCode varchar(60) PK; PositionName nvarchar(150); DepartmentName nvarchar(150); Grade varchar(40); JobDescription nvarchar(MAX); ResponsibilitiesJson nvarchar(MAX); RequiredSkillsJson nvarchar(MAX); ProfileVersion varchar(20); Status varchar(20); CreatedAtUtc datetime2(7); ReportsToRoleCode varchar(60)?; OrgLayer varchar(40)?; ApprovalScope varchar(80)?; QualityGatesJson nvarchar(MAX)?; MaxRecommendedAutonomy tinyint?` |
| Agent | `AgentID uniqueidentifier PK; CompanyID uniqueidentifier; DepartmentID uniqueidentifier; PositionID uniqueidentifier?; AgentName nvarchar(200); AgentType varchar(30); Grade varchar(20); ManagerAgentID uniqueidentifier?; DirectorAgentID uniqueidentifier?; JobDescription nvarchar(MAX); ResponsibilitiesJson nvarchar(MAX)?; SecurityRoleID uniqueidentifier?; ApprovalAuthorityID uniqueidentifier?; Model nvarchar(100)?; ModelVersion nvarchar(50)?; PromptVersion nvarchar(50)?; AutonomyLevel tinyint; RiskLevel varchar(20); CostLimitMonthly decimal(18,2); TokenLimitDaily bigint; ConcurrentTaskLimit int; CurrentWorkload decimal(5,2); CreatedDate datetime2(7); LastEvaluationDate datetime2(7)?; ExpiryDate datetime2(7)?; Status varchar(30); CreatedBy nvarchar(200); ModifiedDate datetime2(7); ModifiedBy nvarchar(200); WorkforceRoleCode varchar(60)?; ModelProvider nvarchar(100)?` |
| AgentSkill | `AgentID uniqueidentifier PK; SkillID uniqueidentifier PK; Proficiency tinyint; Status varchar(20)` |
| Role | `RoleID uniqueidentifier PK; RoleName nvarchar(100)?; RoleLevel int?; RoleCode nvarchar(50)?; IsActive bit?` |

The eight PKs match the allowlist (AgentID; RoleCode; SkillID; composite
AgentID/SkillID; CompanyID; DepartmentID; PositionID; RoleID). The live
allowlist also has `UQ_Department(CompanyID, DepartmentName)` and
`UQ_Skill(Name)`; there is no unique constraint on `Role.RoleCode`. Agent's
CompanyID and DepartmentID are NOT NULL while PositionID is nullable, contrary
to G3's blanket statement that the three columns were all non-null. All 56
current Agent rows nevertheless have values for all three fields. Canonical
Role rows are absent; with no migration ledger this mixed schema/data evidence
does not establish whether migration 23 was applied, partially applied, or
otherwise reconciled.

The six empty mapping/reference tables in the G3 schema/count section were also
checked; their documented column lists match live schema. Their row counts
remain zero. Skill and WorkforceRoleProfile JSON/configuration columns were
checked for valid JSON; no malformed records were found.

### Workforce, RBAC, and special-case results

- Agent/profile/skill counts remain 56 / 56 / 38; all 56 Agent role codes
  resolve to profiles. There are 102 AgentSkill rows across 55 agents, all
  Pending, with no orphaned Agent or Skill references. All Agent names are
  distinct; descriptions and responsibilities are present for all 56.
- One Agent is Active and 55 Provisioning. All 56 Model and ModelVersion fields
  contain the literal `UNCONFIGURED`; ModelProvider is unset for all. No
  AgentPermission, AgentTool, or AgentKnowledgeAccess assignments exist.
  Exactly 24 open activation blockers remain across six agents: AI Business
  Analyst, AI Delivery Lead, AI QA Engineer, AI Security Engineer, HR Workforce
  Coordinator, and Software Developer (four each). Current blocker codes are
  `APPROVED_MODEL_IS_NOT_CONFIGURED`,
  `APPROVED_PROVIDER_IS_NOT_CONFIGURED`,
  `MODEL_VERSION_IS_NOT_CONFIGURED`, and `PASSED_EVALUATIONS_MISSING`.
- All 55 ManagerAgentID links and six DirectorAgentID links resolve. All 55
  populated ReportsToRoleCode values resolve as profile codes, but that field
  is text-only; DirectorAgentID is not FK-enforced. AI CEO remains Active and
  reports to AI Chief of Staff. Its Agent and profile JobDescription and
  ResponsibilitiesJson values still differ; both JSON values are valid. No
  source values were reconciled.
- The database still has only active `USER`, `MANAGER`, and `SUPER_ADMIN`
  roles, assigned to 31, 6, and 2 AppUsers respectively. All 39 AppUser RoleID
  values resolve, but AppUser.RoleID has no physical FK. No canonical role row
  exists. `app/security/roles.py` contains the documented code aliases and
  canonical role names; `app/security/permissions.py` implements role-gated
  access, not a persisted permission matrix. There is no RolePermission table,
  Permission has zero rows, and AgentPermission has zero rows. The
  `sys.database_permissions` catalog contains 220 SQL permission rows (217
  SELECT object/column grants and three database grants); these are SQL
  principal permissions, not mappings from application Role IDs. No custom
  database-role membership rows were found. No application role-permission
  mapping is verified.
- Special counts are unchanged: AuditLog 257; Approval 7;
  OrganizationBootstrapRun 1; WorkforceRequest 36; Requirement 14;
  RequirementAssessment 8; RequirementAssessmentDepartment 45; RequirementSkill
  38; AppUser 39; AppUserAvailability 18; AppUserCertification 6; AppUserSkill
  35; Notification 73; ResourceAssignmentRecommendation 5; and
  ProjectTaskAssignment 2. Approval has no physical FKs despite ORM
  declarations; OrganizationBootstrapRun's three FKs to Approval, Company, and
  Requirement are present. These records remain outside the default workforce
  export and require their documented owner/privacy/legal/security decisions.
- No credential values, password hashes, token hashes, or secret-reference
  values were queried or displayed. Schema inspection confirmed sensitive
  columns in AppUser, AgentRuntimeCredential, and ExecutionAdapterConfig;
  AgentRuntimeCredential and ExecutionAdapterConfig currently have zero rows.

### Dependency correction and export/import assessment

The G3 table graph was accurate, but its project sequence incorrectly said
ProjectDeliveryTask depends on ResourceAssignmentRecommendation and did not
state all child-first steps. Live edges are
ProjectTaskAssignment -> ProjectDeliveryTask and
ResourceAssignmentRecommendation; ResourceAssignmentRecommendation ->
ProjectDeliveryTask; ProjectDeliveryTask -> ProjectStory;
ProjectStory -> ProjectFeature and ProjectSprint; ProjectFeature ->
ProjectEpic; and ProjectEpic / ProjectSprint -> Project. The sequence above is
corrected; REVIEW children must still be dispositioned and counted at execution.
TaskDependency has two Task FKs, Task has its self-parent FK, and the graph has
no multi-table FK cycle. Relationship-by-code/text remains separate from FK
evidence.

The eight-table parent-first restore order remains technically feasible:
Company -> Department -> Position; Skill and WorkforceRoleProfile before Agent;
Agent before AgentSkill; Role is independent. Preserve source PKs, all values
and nulls, and JSON text exactly; validate ManagerAgentID, DirectorAgentID,
ReportsToRoleCode, and role-code relationships separately because not all are
FK-enforced. The allowlist does not include 24 activation blockers, 257 audit
rows, 7 approvals, 1 bootstrap run, 36 workforce requests, the requirement and
assessment chains, human-account/workforce rows, notifications, or allocation
recommendations. These rows remain in the source but have not been exported;
they are not safe to classify as disposable. No backup/restore or value-hash
round trip was performed, so actual package completeness and restoration remain
unproven.

### Security, blockers, and non-execution record

There are no authoritative TenantID/OrganizationID columns and no SQL Server
RLS policies. CompanyID/DepartmentID do not establish tenant ownership.
Migration history and data provenance remain unknown; the sysadmin inspection
identity is prohibited for future export/cleanup execution. The current RLS
guide and code state that `get_db` sets only `SESSION_CONTEXT(UserID)`, worker
requests do not establish SQL worker/Agent context, and session-context cleanup
suppresses clear failures. No distinct least-privilege SQL API/worker/reviewer/
reaper identities or their row scopes have been verified. Migrations 16-18
retain the old organization/department model and migration 16's coverage guard;
migration 27's optional policy path retains broad reaper owner-row visibility.
These paths are not a validated deployment and no migration-history table is
available to prove application state. This database cannot support a verified
multi-tenant or production-readiness claim.

Required follow-up is owner disposition for excluded operational, identity,
audit, approval, requirement, and security evidence; confirmation of AI CEO
authoring/hierarchy; approved least-privilege export identity and encrypted
destination; separate written export/backup authorization; and an isolated
restore/value-validation run before any cleanup is considered. Cleanup remains
NO-GO and the reset remains unapproved.

Documentation inspected for G4: README.md (conflict markers preserved),
AI_WORKFORCE_OS_MASTER_PLAN.md (absent), IMPLEMENTATION_STATUS.md,
ARCHITECTURE_DECISIONS.md (absent), AGENT_HANDOFF.md, this plan,
RLS_Deployment_Guide.md, Single_Organization_RBAC_Migration_Plan.md,
`app/security/roles.py`, `app/security/permissions.py`, and SQL migrations
04, phase3_roles, and 23. No application tests were run. All database
verification used SELECT-only statements. No database rows/objects, application
code, configuration, backups, exports, or migration state were changed.
