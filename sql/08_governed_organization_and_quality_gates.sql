USE AICompany;
GO

IF COL_LENGTH('dbo.WorkforceRoleProfile', 'ReportsToRoleCode') IS NULL
    ALTER TABLE dbo.WorkforceRoleProfile ADD ReportsToRoleCode varchar(60) NULL;
IF COL_LENGTH('dbo.WorkforceRoleProfile', 'OrgLayer') IS NULL
    ALTER TABLE dbo.WorkforceRoleProfile ADD OrgLayer varchar(40) NULL;
IF COL_LENGTH('dbo.WorkforceRoleProfile', 'ApprovalScope') IS NULL
    ALTER TABLE dbo.WorkforceRoleProfile ADD ApprovalScope varchar(80) NULL;
IF COL_LENGTH('dbo.WorkforceRoleProfile', 'QualityGatesJson') IS NULL
    ALTER TABLE dbo.WorkforceRoleProfile ADD QualityGatesJson nvarchar(max) NULL;
IF COL_LENGTH('dbo.WorkforceRoleProfile', 'MaxRecommendedAutonomy') IS NULL
    ALTER TABLE dbo.WorkforceRoleProfile ADD MaxRecommendedAutonomy tinyint NULL;
GO

IF OBJECT_ID('dbo.GovernanceGateProfile', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.GovernanceGateProfile(
        GateCode varchar(60) NOT NULL PRIMARY KEY,
        SequenceNumber int NOT NULL,
        GateName nvarchar(150) NOT NULL,
        OwnerRoleCode varchar(60) NOT NULL,
        AppliesTo varchar(30) NOT NULL,
        BlocksProgress bit NOT NULL,
        RequiresHumanApproval bit NOT NULL,
        RequiredEvidenceJson nvarchar(max) NOT NULL,
        Status varchar(20) NOT NULL,
        CONSTRAINT CK_GovernanceGateProfile_AppliesTo CHECK (AppliesTo IN ('All','HighRisk','CriticalRisk','Production','Conditional')),
        CONSTRAINT CK_GovernanceGateProfile_Status CHECK (Status IN ('Configured','Retired'))
    );
END;
GO

IF OBJECT_ID('dbo.EscalationPolicyProfile', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.EscalationPolicyProfile(
        EscalationCode varchar(40) NOT NULL PRIMARY KEY,
        SequenceNumber int NOT NULL,
        TargetRoleCode varchar(60) NOT NULL,
        TriggerDescription nvarchar(500) NOT NULL,
        TargetResponseMinutes int NULL,
        RequiresNotification bit NOT NULL,
        Status varchar(20) NOT NULL
    );
END;
GO

DECLARE @OrgProfiles TABLE(
    RoleCode varchar(60), PositionName nvarchar(150), DepartmentName nvarchar(150), Grade varchar(40),
    ReportsToRoleCode varchar(60), OrgLayer varchar(40), JobDescription nvarchar(max),
    ResponsibilitiesJson nvarchar(max), RequiredSkillsJson nvarchar(max), ApprovalScope varchar(80),
    QualityGatesJson nvarchar(max), MaxRecommendedAutonomy tinyint
);

INSERT @OrgProfiles VALUES
('AI_CHIEF_OF_STAFF','AI Chief of Staff','Executive','Executive',NULL,'Governance',N'Monitors the organization, executive portfolio, workforce utilization, approvals, SLAs, risks, and escalations. Produces evidence-linked briefings and can escalate directly to the Owner. Cannot override an approval or safety gate.',N'["Monitor portfolio, agents, projects, approvals, and SLAs","Prepare executive briefings with evidence and uncertainty","Route escalations to accountable executives or Owner","Track decisions and overdue actions"]',N'[{"name":"DeliveryManagement","minimum_proficiency":4},{"name":"RiskManagement","minimum_proficiency":4}]','escalation_and_portfolio','["AUDIT_TRAIL","ESCALATION"]',2),
('AI_CEO','AI CEO','Executive','Executive','AI_CHIEF_OF_STAFF','Executive',N'Owns advisory business strategy, portfolio assessment, and requirement prioritization. Produces a traceable recommendation; cannot approve its own assessment or authorize delivery.',N'["Assess business value and strategic fit","Prioritize portfolio recommendations","Record assumptions, evidence, risks, and open questions"]','[{"name":"RequirementAnalysis","minimum_proficiency":4},{"name":"PortfolioManagement","minimum_proficiency":4}]','business_strategy','["CEO_ASSESSMENT"]',2),
('AI_CTO','AI CTO','Executive','Executive','AI_CHIEF_OF_STAFF','Executive',N'Owns technology strategy, architecture standards, and technical risk review. Architecture approval is a separate gate from business approval.',N'["Review solution architecture and integrations","Set engineering standards","Assess technical and security architecture risks"]','[{"name":"ArchitectureReview","minimum_proficiency":4},{"name":"SecurityReview","minimum_proficiency":4}]','architecture','["ARCHITECTURE_REVIEW"]',2),
('AI_COO','AI COO','Executive','Executive','AI_CHIEF_OF_STAFF','Executive',N'Owns delivery governance, resource allocation recommendations, operational readiness, and capacity review. Does not start work without approved planning and staffing.',N'["Review delivery plan, dependencies, and capacity","Monitor outcomes, blockers, and SLAs","Escalate delivery risks"]','[{"name":"DeliveryManagement","minimum_proficiency":4},{"name":"CapacityPlanning","minimum_proficiency":4}]','delivery_and_capacity','["DELIVERY_PLAN"]',2),
('AI_CFO','AI CFO','Executive','Executive','AI_CHIEF_OF_STAFF','Executive',N'Owns advisory cost, ROI, budget, and financial-control assessment. Spend or budget exceptions require separate authorized human approval.',N'["Estimate cost and ROI with assumptions","Review budget limits and financial risks","Escalate threshold exceptions"]','[{"name":"FinancialAnalysis","minimum_proficiency":4},{"name":"BudgetControl","minimum_proficiency":4}]','financial_controls','["COST_REVIEW","BUDGET_EXCEPTION"]',2),
('AI_CHRO','AI CHRO','Executive','Executive','AI_CHIEF_OF_STAFF','Executive',N'Owns workforce planning, role design, talent process, learning, and employee-data stewardship. AI recommendations do not make employment decisions.',N'["Review workforce plans and role profiles","Oversee fair and privacy-conscious hiring processes","Track capability and learning gaps"]','[{"name":"HRProcessDesign","minimum_proficiency":4},{"name":"WorkforcePlanning","minimum_proficiency":4}]','workforce_and_people_policy','["WORKFORCE_PLAN","AGENT_CREATION"]',2),
('AI_CISO','AI CISO','Executive','Executive','AI_CHIEF_OF_STAFF','Executive',N'Owns security governance and independent security risk review. Production release requires recorded security evidence and authorized approval.',N'["Review threat models and security controls","Assess privacy and cyber risks","Block release for unresolved critical findings"]','[{"name":"SecurityReview","minimum_proficiency":5},{"name":"SecurityEngineering","minimum_proficiency":4}]','security_governance','["SECURITY_REVIEW","PRODUCTION_RELEASE"]',2),
('AI_PMO_DIRECTOR','AI PMO Director','PMO','Director','AI_COO','Department',N'Owns portfolio/program governance, delivery standards, and escalation across the PMO.',N'["Set delivery governance standards","Oversee programs and escalations","Review portfolio health"]','[{"name":"DeliveryManagement","minimum_proficiency":4},{"name":"PortfolioManagement","minimum_proficiency":3}]','portfolio_delivery','["DELIVERY_PLAN","ESCALATION"]',2),
('AI_PROGRAM_MANAGER','AI Program Manager','PMO','Lead','AI_PMO_DIRECTOR','Department',N'Coordinates strategic programs and cross-project dependencies, risks, milestones, and outcomes.',N'["Coordinate multi-project plans","Manage dependencies and risks","Report program outcomes"]','[{"name":"ProjectPlanning","minimum_proficiency":4},{"name":"DeliveryManagement","minimum_proficiency":3}]','program_delivery','["DELIVERY_PLAN"]',2),
('AI_PROJECT_MANAGER','AI Project Manager','PMO','Lead','AI_PROGRAM_MANAGER','Department',N'Owns approved project execution coordination, risks, issues, schedule, and status reporting under the Delivery Lead and COO gates.',N'["Maintain project plan and RAID log","Coordinate accountable owners","Report schedule, scope, and quality"]','[{"name":"ProjectPlanning","minimum_proficiency":4},{"name":"DeliveryManagement","minimum_proficiency":4}]','project_delivery','["DELIVERY_PLAN","HANDOFF"]',2),
('DELIVERY_LEAD','AI Delivery Lead','PMO','Lead','AI_PROJECT_MANAGER','Specialist',N'Owns delivery planning and governance for approved work. Decomposes validated scope into sequenced, estimable tasks; manages dependencies, risks, capacity, and stakeholder reporting. Cannot approve its own work, authorize spend, or bypass security and release gates.',N'["Decompose approved scope into deliverables and acceptance criteria","Estimate work with evidence and record assumptions","Sequence dependencies and maintain forecast","Coordinate qualified staff and escalate capacity gaps","Report risks, progress, and decisions"]','[{"name":"ProjectPlanning","minimum_proficiency":4},{"name":"DeliveryManagement","minimum_proficiency":4}]','project_delivery','["DELIVERY_PLAN","HANDOFF","ESCALATION"]',2),
('BUSINESS_ARCHITECT','AI Business Architect','PMO','Principal','AI_PMO_DIRECTOR','Specialist',N'Maps business capabilities and transformation outcomes; maintains traceability from strategy to requirements.',N'["Map capabilities and value streams","Assess operating-model change","Maintain outcome traceability"]','[{"name":"BusinessArchitecture","minimum_proficiency":4},{"name":"RequirementAnalysis","minimum_proficiency":4}]','business_architecture','["REQUIREMENT_VALIDATION"]',2),
('BUSINESS_ANALYST','AI Business Analyst','PMO','Senior','BUSINESS_ARCHITECT','Specialist',N'Elicits requirements and user stories, validates acceptance criteria, and maintains facts, assumptions, and open questions.',N'["Elicit and validate requirements","Write user stories and acceptance criteria","Maintain traceability"]','[{"name":"RequirementAnalysis","minimum_proficiency":4}]','requirement_quality','["REQUIREMENT_VALIDATION","SELF_REVIEW"]',2),
('PROCESS_ANALYST','AI Process Analyst','Operations','Senior','BUSINESS_ARCHITECT','Specialist',N'Analyzes and improves business processes and identifies governed workflow-automation opportunities.',N'["Map current and future processes","Measure process performance","Identify control and automation opportunities"]','[{"name":"ProcessAnalysis","minimum_proficiency":4},{"name":"RequirementAnalysis","minimum_proficiency":3}]','process_design','["REQUIREMENT_VALIDATION"]',2),
('ENTERPRISE_ARCHITECT','AI Enterprise Architect','Technology','Principal','AI_CTO','Specialist',N'Maintains enterprise architecture principles, capability maps, standards, and cross-domain alignment.',N'["Review enterprise fit and standards","Maintain architecture decisions","Identify cross-platform dependencies"]','[{"name":"ArchitectureReview","minimum_proficiency":5}]','enterprise_architecture','["ARCHITECTURE_REVIEW"]',2),
('SOLUTION_ARCHITECT','AI Solution Architect','Technology','Principal','ENTERPRISE_ARCHITECT','Specialist',N'Designs solution architecture, interfaces, nonfunctional requirements, and technical decision records.',N'["Design solution components and interfaces","Document tradeoffs and nonfunctional requirements","Review implementation conformance"]','[{"name":"ArchitectureReview","minimum_proficiency":4},{"name":"IntegrationDesign","minimum_proficiency":3}]','solution_architecture','["ARCHITECTURE_REVIEW","PEER_REVIEW"]',2),
('DATA_ARCHITECT','AI Data Architect','Data & Analytics','Principal','ENTERPRISE_ARCHITECT','Specialist',N'Owns data-platform architecture, data contracts, lineage, classification, and governance design.',N'["Define data architecture and contracts","Review data classification and lineage","Set platform data standards"]','[{"name":"DataArchitecture","minimum_proficiency":4},{"name":"DataEngineering","minimum_proficiency":3}]','data_architecture','["ARCHITECTURE_REVIEW","DATA_GOVERNANCE"]',2),
('INTEGRATION_ARCHITECT','AI Integration Architect','Technology','Principal','SOLUTION_ARCHITECT','Specialist',N'Designs governed API and enterprise integration patterns with identity, resilience, and data-boundary controls.',N'["Design API and integration contracts","Review identity and trust boundaries","Define resilience and observability"]','[{"name":"IntegrationDesign","minimum_proficiency":4},{"name":"SecurityReview","minimum_proficiency":3}]','integration_architecture','["ARCHITECTURE_REVIEW","SECURITY_REVIEW"]',2),
('TECHNICAL_LEAD','AI Technical Lead','Technology','Lead','SOLUTION_ARCHITECT','Specialist',N'Provides design review, code review, engineering coordination, and technical governance for an approved solution.',N'["Review design and implementation","Coordinate technical decisions","Ensure testing and documentation"]','[{"name":"SoftwareDevelopment","minimum_proficiency":4},{"name":"CodeReview","minimum_proficiency":4}]','technical_governance','["PEER_REVIEW","SELF_REVIEW"]',2),
('FULL_STACK_DEVELOPER','AI Full Stack Developer','Technology','Senior','TECHNICAL_LEAD','Specialist',N'Implements approved user interfaces, APIs, and database-connected features with tests and secure coding practices.',N'["Implement frontend and backend changes","Write automated tests","Document APIs and behavior"]','[{"name":"SoftwareDevelopment","minimum_proficiency":4},{"name":"QualityTesting","minimum_proficiency":2}]','application_development','["SELF_REVIEW","PEER_REVIEW"]',2),
('BACKEND_SPECIALIST','AI Backend Specialist','Technology','Senior','TECHNICAL_LEAD','Specialist',N'Builds and maintains backend APIs and services with authorization, data integrity, observability, and tests.',N'["Implement backend services","Enforce API authorization and validation","Maintain service tests and telemetry"]','[{"name":"SoftwareDevelopment","minimum_proficiency":4},{"name":"APIEngineering","minimum_proficiency":3}]','backend_development','["SELF_REVIEW","PEER_REVIEW"]',2),
('FRONTEND_SPECIALIST','AI Frontend Specialist','Technology','Senior','TECHNICAL_LEAD','Specialist',N'Builds accessible, responsive frontend workflows integrated with secured backend APIs.',N'["Implement accessible interfaces","Integrate APIs safely","Verify responsive and assistive-technology behavior"]','[{"name":"SoftwareDevelopment","minimum_proficiency":3},{"name":"AccessibilityTesting","minimum_proficiency":3}]','frontend_development','["SELF_REVIEW","PEER_REVIEW"]',2),
('DATABASE_SPECIALIST','AI Database Specialist','Data & Analytics','Senior','DATA_ARCHITECT','Specialist',N'Designs and tunes database schema, SQL, migrations, and query performance with recovery and access controls.',N'["Design schema and SQL changes","Review migrations and performance","Validate backup and recovery impacts"]','[{"name":"DatabaseAdministration","minimum_proficiency":4},{"name":"SQLDevelopment","minimum_proficiency":4}]','database_engineering','["PEER_REVIEW","DATA_GOVERNANCE"]',2),
('INTEGRATION_SPECIALIST','AI Integration Specialist','Technology','Senior','INTEGRATION_ARCHITECT','Specialist',N'Implements and verifies approved REST and enterprise integrations using scoped credentials and resilient contracts.',N'["Implement API integrations","Test authentication and failure handling","Document interface contracts"]','[{"name":"IntegrationDesign","minimum_proficiency":3},{"name":"APIEngineering","minimum_proficiency":3}]','integration_delivery','["PEER_REVIEW","SECURITY_REVIEW"]',2),
('DATA_ENGINEER','AI Data Engineer','Data & Analytics','Senior','DATA_ARCHITECT','Specialist',N'Builds governed ETL and data pipelines with data quality, lineage, access, and recovery controls.',N'["Build data pipelines","Implement validation and lineage","Test recovery and data contracts"]','[{"name":"DataEngineering","minimum_proficiency":4},{"name":"SQLDevelopment","minimum_proficiency":3}]','data_delivery','["DATA_GOVERNANCE","PEER_REVIEW"]',2),
('BI_SPECIALIST','AI BI Specialist','Data & Analytics','Senior','DATA_ARCHITECT','Specialist',N'Develops governed Power BI semantic models, dashboards, and KPI definitions with access and quality checks.',N'["Define metrics and semantic models","Build and test dashboards","Validate row-level access"]','[{"name":"PowerBIDevelopment","minimum_proficiency":4},{"name":"DataAnalysis","minimum_proficiency":3}]','business_intelligence','["DATA_GOVERNANCE","QUALITY_REVIEW"]',2),
('DATA_SCIENTIST','AI Data Scientist','Data & Analytics','Principal','DATA_ARCHITECT','Specialist',N'Develops evaluated statistical and machine-learning analyses with reproducibility, bias checks, and clear limitations.',N'["Build and evaluate analytical models","Document assumptions and limitations","Validate data and model performance"]','[{"name":"DataScience","minimum_proficiency":4},{"name":"DataAnalysis","minimum_proficiency":4}]','data_science','["DATA_GOVERNANCE","QUALITY_REVIEW"]',2),
('DATA_ANALYST','AI Data Analyst','Data & Analytics','Senior','DATA_ARCHITECT','Specialist',N'Analyzes approved datasets and produces reproducible metrics and evidence-linked business reporting.',N'["Validate metrics and data quality","Perform reproducible analysis","Communicate limitations and findings"]','[{"name":"DataAnalysis","minimum_proficiency":4},{"name":"PowerBIDevelopment","minimum_proficiency":3}]','data_analysis','["QUALITY_REVIEW","DATA_GOVERNANCE"]',2),
('QA_DIRECTOR','AI QA Director','Quality','Director','AI_COO','Department',N'Owns organization-wide quality policy, independence, risk-based test coverage, and release quality escalations.',N'["Set quality strategy and thresholds","Review quality evidence and escape trends","Escalate release-blocking defects"]','[{"name":"QualityTesting","minimum_proficiency":5},{"name":"QualityGovernance","minimum_proficiency":4}]','quality_governance','["QUALITY_REVIEW","EXECUTIVE_SIGNOFF"]',2),
('TEST_ARCHITECT','AI Test Architect','Quality','Principal','QA_DIRECTOR','Specialist',N'Designs test strategy, coverage, automation architecture, test data controls, and evidence standards.',N'["Create risk-based test strategy","Design automation architecture","Define evidence and coverage metrics"]','[{"name":"TestArchitecture","minimum_proficiency":4},{"name":"QualityTesting","minimum_proficiency":4}]','test_strategy','["QUALITY_REVIEW"]',2),
('TEST_ENGINEER','AI Test Engineer','Quality','Senior','TEST_ARCHITECT','Specialist',N'Executes functional and regression verification and records reproducible results and defects.',N'["Create and execute test cases","Verify acceptance criteria","Record and retest defects"]','[{"name":"QualityTesting","minimum_proficiency":4}]','functional_testing','["QUALITY_REVIEW","SELF_REVIEW"]',2),
('AUTOMATION_TESTER','AI Automation Tester','Quality','Senior','TEST_ARCHITECT','Specialist',N'Builds and maintains automated functional, regression, and performance tests with reliable fixtures and diagnostics.',N'["Automate regression coverage","Build stable test fixtures","Report performance and reliability findings"]','[{"name":"QualityTesting","minimum_proficiency":4},{"name":"TestAutomation","minimum_proficiency":4}]','test_automation','["QUALITY_REVIEW","PEER_REVIEW"]',2),
('QA_ENGINEER','AI QA Engineer','Quality','Senior','TEST_ARCHITECT','Specialist',N'Performs risk-based independent quality verification across functional, integration, accessibility, and regression behavior.',N'["Verify requirements and acceptance criteria","Record reproducible defects","Confirm release evidence"]','[{"name":"QualityTesting","minimum_proficiency":4}]','quality_assurance','["QUALITY_REVIEW","PEER_REVIEW"]',2),
('DEVOPS_ARCHITECT','AI DevOps Architect','Technology','Principal','AI_CTO','Specialist',N'Designs controlled CI/CD, release architecture, observability, and rollback standards.',N'["Design delivery pipelines and release controls","Review environment separation and rollback","Define operational telemetry"]','[{"name":"DevOpsEngineering","minimum_proficiency":4},{"name":"SecurityEngineering","minimum_proficiency":3}]','devops_architecture','["SECURITY_REVIEW","PRODUCTION_RELEASE"]',2),
('DEVOPS_ENGINEER','AI DevOps Engineer','Technology','Senior','DEVOPS_ARCHITECT','Specialist',N'Implements approved CI/CD, monitoring, infrastructure automation, and release runbooks.',N'["Build and operate pipelines","Automate infrastructure safely","Maintain monitoring and rollback runbooks"]','[{"name":"DevOpsEngineering","minimum_proficiency":4}]','devops_delivery','["SECURITY_REVIEW","PRODUCTION_RELEASE"]',2),
('CLOUD_ENGINEER','AI Cloud Engineer','Technology','Senior','DEVOPS_ARCHITECT','Specialist',N'Builds and operates approved cloud and container environments with identity, network, resilience, and cost controls.',N'["Implement cloud infrastructure","Apply identity and network controls","Monitor reliability and cost"]','[{"name":"CloudEngineering","minimum_proficiency":4},{"name":"SecurityEngineering","minimum_proficiency":3}]','cloud_operations','["SECURITY_REVIEW","COST_REVIEW"]',2),
('L1_SUPPORT','AI L1 Support','Operations','Associate','AI_COO','Specialist',N'Handles approved user requests and first-line triage using documented procedures and minimum necessary data.',N'["Triage and categorize requests","Follow approved knowledge articles","Escalate security or service incidents"]','[{"name":"SupportOperations","minimum_proficiency":2}]','user_support','["HANDOFF"]',1),
('L2_SUPPORT','AI L2 Support','Operations','Senior','L1_SUPPORT','Specialist',N'Investigates functional and technical issues beyond first-line procedures and coordinates safe remediation.',N'["Investigate service issues","Correlate logs and symptoms","Escalate engineering and security incidents"]','[{"name":"SupportOperations","minimum_proficiency":3},{"name":"RootCauseAnalysis","minimum_proficiency":3}]','technical_support','["HANDOFF","AUDIT_TRAIL"]',1),
('L3_SUPPORT','AI L3 Support','Operations','Principal','L2_SUPPORT','Specialist',N'Performs engineering-level issue investigation and root-cause analysis; changes require reviewed change controls.',N'["Analyze complex incidents","Produce root-cause evidence","Coordinate reviewed corrective changes"]','[{"name":"RootCauseAnalysis","minimum_proficiency":4},{"name":"SoftwareDevelopment","minimum_proficiency":3}]','engineering_support','["PEER_REVIEW","AUDIT_TRAIL"]',1),
('INCIDENT_COMMANDER','AI Incident Commander','Operations','Lead','AI_COO','Specialist',N'Coordinates major incident response, communications, decision logging, and recovery under the incident policy.',N'["Coordinate incident roles and status","Maintain decision and timeline record","Escalate critical incidents to executive and Owner"]','[{"name":"IncidentManagement","minimum_proficiency":4},{"name":"RiskManagement","minimum_proficiency":3}]','incident_command','["ESCALATION","AUDIT_TRAIL"]',1),
('PROBLEM_SOLVER','AI Problem Solver','Operations','Specialist','AI_CHIEF_OF_STAFF','CrossFunctional',N'Provides bounded cross-department analysis and solution options while respecting each domain owner and approval gate.',N'["Analyze cross-functional problems","Offer evidence-linked options","Route decisions to accountable owners"]','[{"name":"RequirementAnalysis","minimum_proficiency":3},{"name":"RootCauseAnalysis","minimum_proficiency":3}]','advisory_assistance','["AUDIT_TRAIL"]',1),
('QUALITY_REVIEWER','AI Quality Reviewer','Quality','Independent','QA_DIRECTOR','CrossFunctional',N'Provides independent quality review of deliverables and evidence; cannot approve its own originating work.',N'["Review deliverables against acceptance criteria","Record defects and evidence","Block handoff when required QA evidence is missing"]','[{"name":"QualityTesting","minimum_proficiency":5},{"name":"QualityGovernance","minimum_proficiency":4}]','independent_quality','["QUALITY_REVIEW","PEER_REVIEW"]',1),
('AI_AUDITOR','AI Auditor','Risk','Independent','AI_CHIEF_OF_STAFF','CrossFunctional',N'Performs independent governance and compliance evidence review without modifying or approving the work under review.',N'["Verify audit completeness","Review policy and approval evidence","Report findings and remediation"]','[{"name":"AuditReview","minimum_proficiency":4},{"name":"RiskManagement","minimum_proficiency":4}]','independent_audit','["GOVERNANCE_REVIEW","AUDIT_TRAIL"]',1),
('KNOWLEDGE_MANAGER','AI Knowledge Manager','Operations','Senior','AI_PMO_DIRECTOR','CrossFunctional',N'Maintains versioned, approved organizational knowledge and ensures ownership, provenance, and review dates.',N'["Curate approved knowledge","Track provenance and freshness","Route policy changes to owners"]','[{"name":"KnowledgeManagement","minimum_proficiency":4}]','knowledge_governance','["GOVERNANCE_REVIEW"]',1),
('ROOT_CAUSE_ANALYST','AI Root Cause Analyst','Operations','Senior','INCIDENT_COMMANDER','CrossFunctional',N'Analyzes incidents and recurring failures using evidence, causal hypotheses, and verified corrective-action tracking.',N'["Analyze event evidence","Distinguish cause from correlation","Track corrective actions and verification"]','[{"name":"RootCauseAnalysis","minimum_proficiency":4},{"name":"DataAnalysis","minimum_proficiency":3}]','incident_analysis','["QUALITY_REVIEW","AUDIT_TRAIL"]',1),
('RISK_OFFICER','AI Risk Officer','Risk','Independent','AI_CHIEF_OF_STAFF','CrossFunctional',N'Performs independent risk identification, rating, mitigation tracking, and escalation across projects and agents.',N'["Identify and assess risks","Review mitigation owners and evidence","Escalate residual critical risk"]','[{"name":"RiskManagement","minimum_proficiency":4},{"name":"AuditReview","minimum_proficiency":3}]','risk_governance','["GOVERNANCE_REVIEW","ESCALATION"]',1),
('HR_WORKFORCE_COORDINATOR','HR Workforce Coordinator','HR','Senior','AI_CHRO','Specialist',N'Coordinates approved workforce requisitions and onboarding controls. Does not make employment decisions or provision credentials.',N'["Validate approved role requisitions","Coordinate human recruiting and checks","Protect candidate and employee information"]','[{"name":"HRProcessDesign","minimum_proficiency":4},{"name":"WorkforcePlanning","minimum_proficiency":3}]','workforce_and_people_policy','["WORKFORCE_PLAN","AGENT_CREATION"]',1),
('DATABASE_ADMINISTRATOR','AI Database Administrator','Data & Analytics','Senior','DATA_ARCHITECT','Specialist',N'Operates secure, recoverable database platforms with access, backup, performance, availability, and schema-change controls.',N'["Review database access and operations","Plan backup and recovery","Validate migrations and performance"]','[{"name":"DatabaseAdministration","minimum_proficiency":4},{"name":"SQLDevelopment","minimum_proficiency":3}]','database_operations','["DATA_GOVERNANCE","PEER_REVIEW"]',1),
('SECURITY_ENGINEER','AI Security Engineer','Cybersecurity','Senior','AI_CISO','Specialist',N'Implements and verifies security controls under CISO policy; critical findings block production release.',N'["Review threat models and trust boundaries","Verify identity and access controls","Document security evidence and findings"]','[{"name":"SecurityReview","minimum_proficiency":4},{"name":"SecurityEngineering","minimum_proficiency":3}]','security_review','["SECURITY_REVIEW","PRODUCTION_RELEASE"]',1);

UPDATE target SET
    PositionName=source.PositionName, DepartmentName=source.DepartmentName, Grade=source.Grade,
    ReportsToRoleCode=source.ReportsToRoleCode, OrgLayer=source.OrgLayer,
    JobDescription=source.JobDescription, ResponsibilitiesJson=source.ResponsibilitiesJson,
    RequiredSkillsJson=source.RequiredSkillsJson, ApprovalScope=source.ApprovalScope,
    QualityGatesJson=source.QualityGatesJson, MaxRecommendedAutonomy=source.MaxRecommendedAutonomy,
    ProfileVersion='2.0.0', Status='Active'
FROM dbo.WorkforceRoleProfile target JOIN @OrgProfiles source ON source.RoleCode=target.RoleCode;

INSERT dbo.WorkforceRoleProfile
    (RoleCode, PositionName, DepartmentName, Grade, JobDescription, ResponsibilitiesJson,
     RequiredSkillsJson, ProfileVersion, Status, ReportsToRoleCode, OrgLayer, ApprovalScope,
     QualityGatesJson, MaxRecommendedAutonomy)
SELECT source.RoleCode, source.PositionName, source.DepartmentName, source.Grade,
       source.JobDescription, source.ResponsibilitiesJson, source.RequiredSkillsJson,
       '2.0.0', 'Active', source.ReportsToRoleCode, source.OrgLayer, source.ApprovalScope,
       source.QualityGatesJson, source.MaxRecommendedAutonomy
FROM @OrgProfiles source
WHERE NOT EXISTS (SELECT 1 FROM dbo.WorkforceRoleProfile target WHERE target.RoleCode=source.RoleCode);
GO

INSERT dbo.Skill(Name, Description, Version, RiskLevel, Owner, Status)
SELECT skill.[name], CONCAT('Role competency: ', skill.[name]), '1.0.0', 'Medium', 'AI Workforce OS', 'Approved'
FROM dbo.WorkforceRoleProfile profile
CROSS APPLY OPENJSON(profile.RequiredSkillsJson) WITH ([name] nvarchar(150) '$.name') skill
WHERE NOT EXISTS (SELECT 1 FROM dbo.Skill existing WHERE existing.Name=skill.[name])
GROUP BY skill.[name];
GO

INSERT dbo.Position(PositionID, DepartmentID, PositionName, Grade, Status)
SELECT NEWID(), d.DepartmentID, profile.PositionName, profile.Grade, 'Active'
FROM dbo.WorkforceRoleProfile profile
JOIN dbo.Department d ON d.DepartmentName=profile.DepartmentName
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.Position p
    WHERE p.DepartmentID=d.DepartmentID AND p.PositionName=profile.PositionName
);
GO

DECLARE @Gates TABLE(
    GateCode varchar(60), SequenceNumber int, GateName nvarchar(150), OwnerRoleCode varchar(60),
    AppliesTo varchar(30), BlocksProgress bit, RequiresHumanApproval bit, RequiredEvidenceJson nvarchar(max)
);
INSERT @Gates VALUES
('REQUIREMENT_VALIDATION',10,'Business requirement validation','BUSINESS_ANALYST','All',1,0,'["validated_problem","measurable_outcome","stakeholders","acceptance_criteria","open_questions"]'),
('CEO_ASSESSMENT',20,'Business and strategy assessment','AI_CEO','All',1,0,'["assessment_version","evidence","assumptions","risks","recommendation"]'),
('CTO_ARCHITECTURE',30,'Architecture and technical review','AI_CTO','All',1,0,'["architecture_decision","interfaces","security_architecture","technical_risks"]'),
('CFO_COST_REVIEW',40,'Cost, ROI, and budget review','AI_CFO','All',1,0,'["cost_estimate","roi_assumptions","budget_limit","financial_risks"]'),
('COO_DELIVERY_PLAN',50,'Delivery and capacity plan','AI_COO','All',1,0,'["task_plan","dependencies","qualified_capacity","schedule_assumptions"]'),
('BUSINESS_APPROVAL',60,'Business approval','AI_CEO','All',1,1,'["business_sponsor_decision","decision_reason"]'),
('SECURITY_REVIEW',70,'Security review','AI_CISO','HighRisk',1,0,'["threat_review","access_controls","security_findings","mitigations"]'),
('GOVERNANCE_REVIEW',80,'Governance and audit review','AI_AUDITOR','HighRisk',1,0,'["policy_check","audit_completeness","exceptions"]'),
('SELF_REVIEW',90,'Originating agent self-review','TECHNICAL_LEAD','All',1,0,'["acceptance_checklist","self_review_result"]'),
('PEER_REVIEW',100,'Independent peer review','TECHNICAL_LEAD','All',1,0,'["peer_review_result","reviewer","findings"]'),
('QUALITY_REVIEW',110,'Independent quality review','QUALITY_REVIEWER','All',1,0,'["test_plan","test_results","defect_summary","qa_decision"]'),
('EXECUTIVE_SIGNOFF',120,'Executive sign-off','AI_COO','HighRisk',1,1,'["executive_decision","decision_reason"]'),
('OWNER_SIGNOFF',130,'Owner sign-off','OWNER','Conditional',1,1,'["owner_decision","decision_reason","policy_basis"]'),
('PRODUCTION_SECURITY',140,'Production security and release gate','AI_CISO','Production',1,1,'["security_approval","release_evidence","rollback_plan"]'),
('SUPPORT_HANDOFF',150,'Operations and support handoff','L2_SUPPORT','All',1,0,'["runbook","ownership","monitoring","support_readiness"]');

MERGE dbo.GovernanceGateProfile AS target
USING @Gates AS source ON target.GateCode=source.GateCode
WHEN MATCHED THEN UPDATE SET SequenceNumber=source.SequenceNumber, GateName=source.GateName,
    OwnerRoleCode=source.OwnerRoleCode, AppliesTo=source.AppliesTo, BlocksProgress=source.BlocksProgress,
    RequiresHumanApproval=source.RequiresHumanApproval, RequiredEvidenceJson=source.RequiredEvidenceJson, Status='Configured'
WHEN NOT MATCHED THEN INSERT
    (GateCode, SequenceNumber, GateName, OwnerRoleCode, AppliesTo, BlocksProgress, RequiresHumanApproval, RequiredEvidenceJson, Status)
    VALUES(source.GateCode, source.SequenceNumber, source.GateName, source.OwnerRoleCode,
           source.AppliesTo, source.BlocksProgress, source.RequiresHumanApproval, source.RequiredEvidenceJson, 'Configured');
;
GO

DECLARE @Escalations TABLE(EscalationCode varchar(40), SequenceNumber int, TargetRoleCode varchar(60), TriggerDescription nvarchar(500), TargetResponseMinutes int);
INSERT @Escalations VALUES
('L1',1,'L1_SUPPORT',N'User request or low-severity operational issue',240),
('L2',2,'L2_SUPPORT',N'L1 unresolved, recurring, or requires functional investigation',120),
('L3',3,'L3_SUPPORT',N'Engineering investigation or service degradation required',60),
('DEPARTMENT',4,'AI_PMO_DIRECTOR',N'Cross-team dependency, missed commitment, or department-level blocker',60),
('EXECUTIVE',5,'AI_CHIEF_OF_STAFF',N'Critical risk, executive decision, or overdue critical approval',30),
('OWNER',6,'OWNER',N'Governance exception, critical escalation, or unresolved Owner-reserved decision',15);
MERGE dbo.EscalationPolicyProfile AS target
USING @Escalations AS source ON target.EscalationCode=source.EscalationCode
WHEN MATCHED THEN UPDATE SET SequenceNumber=source.SequenceNumber, TargetRoleCode=source.TargetRoleCode,
    TriggerDescription=source.TriggerDescription, TargetResponseMinutes=source.TargetResponseMinutes,
    RequiresNotification=1, Status='Configured'
WHEN NOT MATCHED THEN INSERT
    (EscalationCode, SequenceNumber, TargetRoleCode, TriggerDescription, TargetResponseMinutes, RequiresNotification, Status)
    VALUES(source.EscalationCode, source.SequenceNumber, source.TargetRoleCode, source.TriggerDescription,
           source.TargetResponseMinutes, 1, 'Configured');
;
GO