USE AICompany;
GO

IF COL_LENGTH('dbo.Task', 'PlannedSequence') IS NULL
    ALTER TABLE dbo.Task ADD PlannedSequence int NULL;
IF COL_LENGTH('dbo.Task', 'RequiredRoleCode') IS NULL
    ALTER TABLE dbo.Task ADD RequiredRoleCode varchar(60) NULL;
IF COL_LENGTH('dbo.Task', 'EstimatedEffortHours') IS NULL
    ALTER TABLE dbo.Task ADD EstimatedEffortHours decimal(9,2) NULL;
IF COL_LENGTH('dbo.Task', 'CompletedAtUtc') IS NULL
    ALTER TABLE dbo.Task ADD CompletedAtUtc datetime2 NULL;
GO

IF OBJECT_ID('dbo.WorkforceRoleProfile', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WorkforceRoleProfile(
        RoleCode varchar(60) NOT NULL PRIMARY KEY,
        PositionName nvarchar(150) NOT NULL,
        DepartmentName nvarchar(150) NOT NULL,
        Grade varchar(40) NOT NULL,
        JobDescription nvarchar(max) NOT NULL,
        ResponsibilitiesJson nvarchar(max) NOT NULL,
        RequiredSkillsJson nvarchar(max) NOT NULL,
        ProfileVersion varchar(20) NOT NULL,
        Status varchar(20) NOT NULL,
        CreatedAtUtc datetime2 NOT NULL CONSTRAINT DF_WorkforceRoleProfile_CreatedAtUtc DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_WorkforceRoleProfile_Status CHECK (Status IN ('Active','Retired'))
    );
END;
GO

IF OBJECT_ID('dbo.WorkforceRequest', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WorkforceRequest(
        WorkforceRequestID uniqueidentifier NOT NULL PRIMARY KEY,
        ProjectID uniqueidentifier NOT NULL REFERENCES dbo.Project(ProjectID),
        TaskID uniqueidentifier NULL REFERENCES dbo.Task(TaskID),
        RoleCode varchar(60) NOT NULL REFERENCES dbo.WorkforceRoleProfile(RoleCode),
        RequestReason nvarchar(1000) NOT NULL,
        Status varchar(30) NOT NULL,
        RequestedBy nvarchar(200) NOT NULL,
        RequestedAtUtc datetime2 NOT NULL,
        DecisionBy nvarchar(200) NULL,
        DecisionReason nvarchar(2000) NULL,
        DecisionAtUtc datetime2 NULL,
        FilledAgentID uniqueidentifier NULL REFERENCES dbo.Agent(AgentID),
        CONSTRAINT UQ_WorkforceRequest_Project_Role UNIQUE(ProjectID, RoleCode),
        CONSTRAINT CK_WorkforceRequest_Status CHECK (Status IN ('PendingApproval','Recruiting','Rejected','CandidateReady','Filled','Cancelled'))
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.Skill WHERE Name = 'DeliveryManagement')
    INSERT dbo.Skill(Name, Description, Version, RiskLevel, Owner, Status) VALUES ('DeliveryManagement', 'Govern delivery scope, dependencies, capacity, and outcomes', '1.0.0', 'Medium', 'PMO', 'Approved');
IF NOT EXISTS (SELECT 1 FROM dbo.Skill WHERE Name = 'HRProcessDesign')
    INSERT dbo.Skill(Name, Description, Version, RiskLevel, Owner, Status) VALUES ('HRProcessDesign', 'Design privacy-conscious HR operations and onboarding processes', '1.0.0', 'High', 'HR', 'Approved');
IF NOT EXISTS (SELECT 1 FROM dbo.Skill WHERE Name = 'SoftwareDevelopment')
    INSERT dbo.Skill(Name, Description, Version, RiskLevel, Owner, Status) VALUES ('SoftwareDevelopment', 'Build reviewed and tested application software', '1.0.0', 'Medium', 'Technology', 'Approved');
IF NOT EXISTS (SELECT 1 FROM dbo.Skill WHERE Name = 'QualityTesting')
    INSERT dbo.Skill(Name, Description, Version, RiskLevel, Owner, Status) VALUES ('QualityTesting', 'Design and execute functional, integration, and regression tests', '1.0.0', 'Medium', 'Quality', 'Approved');
IF NOT EXISTS (SELECT 1 FROM dbo.Skill WHERE Name = 'DatabaseAdministration')
    INSERT dbo.Skill(Name, Description, Version, RiskLevel, Owner, Status) VALUES ('DatabaseAdministration', 'Operate secure, recoverable, performant database platforms', '1.0.0', 'High', 'Data & Analytics', 'Approved');
IF NOT EXISTS (SELECT 1 FROM dbo.Skill WHERE Name = 'DataEngineering')
    INSERT dbo.Skill(Name, Description, Version, RiskLevel, Owner, Status) VALUES ('DataEngineering', 'Build governed data pipelines and quality controls', '1.0.0', 'Medium', 'Data & Analytics', 'Approved');
IF NOT EXISTS (SELECT 1 FROM dbo.Skill WHERE Name = 'DataAnalysis')
    INSERT dbo.Skill(Name, Description, Version, RiskLevel, Owner, Status) VALUES ('DataAnalysis', 'Analyze data and communicate evidence-based findings', '1.0.0', 'Low', 'Data & Analytics', 'Approved');
IF NOT EXISTS (SELECT 1 FROM dbo.Skill WHERE Name = 'SecurityEngineering')
    INSERT dbo.Skill(Name, Description, Version, RiskLevel, Owner, Status) VALUES ('SecurityEngineering', 'Implement and verify application security controls', '1.0.0', 'High', 'Cybersecurity', 'Approved');
GO

DECLARE @Profiles TABLE(
    RoleCode varchar(60), PositionName nvarchar(150), DepartmentName nvarchar(150), Grade varchar(40),
    JobDescription nvarchar(max), ResponsibilitiesJson nvarchar(max), RequiredSkillsJson nvarchar(max)
);
INSERT @Profiles VALUES
('DELIVERY_LEAD','AI Delivery Lead','PMO','Lead',N'Owns delivery planning and governance for approved work. Decomposes validated scope into sequenced, estimable tasks; manages dependencies, risks, capacity, and stakeholder reporting. Cannot approve its own work, authorize spend, or bypass security and release gates.',N'["Decompose approved scope into deliverables and acceptance criteria","Estimate work with evidence and record assumptions","Sequence dependencies and maintain forecast","Coordinate qualified staff and escalate capacity gaps","Report risks, progress, and decisions"]',N'[{"name":"ProjectPlanning","minimum_proficiency":4},{"name":"DeliveryManagement","minimum_proficiency":4}]'),
('HR_WORKFORCE_COORDINATOR','HR Workforce Coordinator','HR','Senior',N'Coordinates approved workforce requisitions and onboarding controls. Maintains role requirements, routes recruiting decisions to accountable humans, and verifies that candidate evaluation, privacy, and onboarding approvals are recorded. Does not make employment decisions or provision AI credentials.',N'["Validate approved role requisitions and job criteria","Coordinate human recruiting and candidate review","Track onboarding and required checks","Protect candidate and employee information","Escalate unresolved policy and authorization questions"]',N'[{"name":"HRProcessDesign","minimum_proficiency":4},{"name":"RequirementAnalysis","minimum_proficiency":3}]'),
('BUSINESS_ANALYST','Business Analyst','PMO','Senior',N'Elicits and validates business needs, process maps, user journeys, acceptance criteria, and traceability for enterprise change. Distinguishes evidence from assumptions and maintains open questions.',N'["Facilitate stakeholder discovery","Map as-is and to-be workflows","Define measurable acceptance criteria","Maintain requirement traceability and change impact"]',N'[{"name":"RequirementAnalysis","minimum_proficiency":4}]'),
('SOFTWARE_DEVELOPER','Software Developer','Technology','Senior',N'Designs, implements, reviews, and maintains secure software within approved architecture and change controls. Produces tested code and technical documentation; does not deploy to production without authorization.',N'["Implement reviewed application changes","Write unit and integration tests","Perform peer review and remediate defects","Document interfaces and operational behavior"]',N'[{"name":"SoftwareDevelopment","minimum_proficiency":4}]'),
('QA_ENGINEER','Quality Assurance Engineer','Quality','Senior',N'Designs and executes risk-based functional, integration, accessibility, security-coordination, and regression testing. Maintains reproducible evidence and blocks release for unresolved critical defects.',N'["Build traceable test plans and cases","Execute automated and manual verification","Record defects with reproducible evidence","Verify fixes and release criteria"]',N'[{"name":"QualityTesting","minimum_proficiency":4}]'),
('DATABASE_ADMINISTRATOR','Database Administrator','Data & Analytics','Senior',N'Operates secure and recoverable database platforms, including access controls, backup and restore, performance, availability, and schema-change governance.',N'["Review database architecture and access","Plan backup, recovery, and availability","Validate schema migrations and performance","Monitor database health and audit evidence"]',N'[{"name":"DatabaseAdministration","minimum_proficiency":4},{"name":"SQLDevelopment","minimum_proficiency":3}]'),
('DATA_ENGINEER','Data Engineer','Data & Analytics','Senior',N'Designs and operates governed data ingestion, transformation, quality, lineage, and serving pipelines with privacy and reliability controls.',N'["Build maintainable data pipelines","Implement quality, lineage, and observability","Apply minimization and access controls","Test recovery and data contracts"]',N'[{"name":"DataEngineering","minimum_proficiency":4},{"name":"SQLDevelopment","minimum_proficiency":3}]'),
('DATA_ANALYST','Data Analyst','Data & Analytics','Senior',N'Uses approved data to answer business questions, validate metrics, and produce reproducible analysis and decision-ready reporting without overstating causality.',N'["Define metrics with stakeholders","Validate source data and assumptions","Produce reproducible analyses and dashboards","Communicate limitations and findings"]',N'[{"name":"DataAnalysis","minimum_proficiency":4},{"name":"PowerBIDevelopment","minimum_proficiency":3}]'),
('SECURITY_ENGINEER','Security Engineer','Cybersecurity','Senior',N'Performs threat-informed security design and verification for approved systems, focusing on least privilege, secure development, privacy boundaries, logging, and release controls.',N'["Review threat model and trust boundaries","Verify identity, authorization, and audit controls","Assess data protection and secrets handling","Document findings and required release mitigations"]',N'[{"name":"SecurityReview","minimum_proficiency":4},{"name":"SecurityEngineering","minimum_proficiency":3}]');

UPDATE target SET
    PositionName = source.PositionName,
    DepartmentName = source.DepartmentName,
    Grade = source.Grade,
    JobDescription = source.JobDescription,
    ResponsibilitiesJson = source.ResponsibilitiesJson,
    RequiredSkillsJson = source.RequiredSkillsJson,
    ProfileVersion = '1.0.0',
    Status = 'Active'
FROM dbo.WorkforceRoleProfile target JOIN @Profiles source ON source.RoleCode = target.RoleCode;

INSERT dbo.WorkforceRoleProfile(RoleCode, PositionName, DepartmentName, Grade, JobDescription, ResponsibilitiesJson, RequiredSkillsJson, ProfileVersion, Status)
SELECT source.RoleCode, source.PositionName, source.DepartmentName, source.Grade, source.JobDescription, source.ResponsibilitiesJson, source.RequiredSkillsJson, '1.0.0', 'Active'
FROM @Profiles source WHERE NOT EXISTS (SELECT 1 FROM dbo.WorkforceRoleProfile target WHERE target.RoleCode = source.RoleCode);
GO

INSERT dbo.Position(PositionID, DepartmentID, PositionName, Grade, Status)
SELECT NEWID(), d.DepartmentID, rp.PositionName, rp.Grade, 'Active'
FROM dbo.WorkforceRoleProfile rp
JOIN dbo.Department d ON d.DepartmentName = rp.DepartmentName
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.Position p
    WHERE p.DepartmentID = d.DepartmentID AND p.PositionName = rp.PositionName
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_WorkforceRequest_Project_Status' AND object_id = OBJECT_ID('dbo.WorkforceRequest'))
    CREATE INDEX IX_WorkforceRequest_Project_Status ON dbo.WorkforceRequest(ProjectID, Status);
GO