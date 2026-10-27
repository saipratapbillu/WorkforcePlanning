USE AICompany;
GO

DECLARE @Departments TABLE(DepartmentName nvarchar(150));
INSERT @Departments VALUES
('Business Analysis'),('Architecture'),('Development'),('Security'),('DevOps'),('Support');
INSERT dbo.Department(CompanyID, DepartmentName)
SELECT c.CompanyID, names.DepartmentName
FROM dbo.Company c CROSS JOIN @Departments names
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.Department d
    WHERE d.CompanyID=c.CompanyID AND d.DepartmentName=names.DepartmentName
);
GO

DECLARE @Heads TABLE(
    RoleCode varchar(60), PositionName nvarchar(150), DepartmentName nvarchar(150), Grade varchar(40),
    ReportsToRoleCode varchar(60), OrgLayer varchar(40), JobDescription nvarchar(max),
    ResponsibilitiesJson nvarchar(max), RequiredSkillsJson nvarchar(max), ApprovalScope varchar(80),
    QualityGatesJson nvarchar(max), MaxRecommendedAutonomy tinyint
);
INSERT @Heads VALUES
('AI_BUSINESS_DIRECTOR','AI Business Director','Business Analysis','Director','AI_PMO_DIRECTOR','Department',N'Leads business analysis, business architecture, and process analysis. Ensures approved requirements have measurable outcomes, traceable acceptance criteria, and documented assumptions.',N'["Lead business analysis capacity and quality","Review capability and process analysis","Escalate unresolved requirement risks"]','[{"name":"RequirementAnalysis","minimum_proficiency":4},{"name":"BusinessArchitecture","minimum_proficiency":3}]','business_analysis','["REQUIREMENT_VALIDATION","ESCALATION"]',1),
('AI_ARCHITECTURE_DIRECTOR','AI Architecture Director','Architecture','Director','AI_CTO','Department',N'Leads enterprise, solution, data, and integration architecture. Ensures design decisions meet approved standards and risk gates.',N'["Govern architecture standards","Review solution and data design","Escalate material technical risks"]','[{"name":"ArchitectureReview","minimum_proficiency":4},{"name":"SecurityReview","minimum_proficiency":3}]','architecture','["ARCHITECTURE_REVIEW","ESCALATION"]',1),
('AI_ENGINEERING_DIRECTOR','AI Engineering Director','Development','Director','AI_CTO','Department',N'Leads software engineering and technical delivery. Ensures code changes are reviewed, tested, traceable, and limited to approved scope.',N'["Manage engineering capacity","Review technical quality and secure development","Escalate delivery and technical risks"]','[{"name":"SoftwareDevelopment","minimum_proficiency":4},{"name":"CodeReview","minimum_proficiency":4}]','engineering','["PEER_REVIEW","QUALITY_REVIEW"]',1),
('AI_SECURITY_DIRECTOR','AI Security Director','Security','Director','AI_CISO','Department',N'Leads security architecture, security engineering, and compliance analysis under CISO policy. Independent release decisions remain with authorized CISO/Owner governance.',N'["Coordinate security assessments","Track vulnerabilities and mitigations","Escalate critical security findings"]','[{"name":"SecurityReview","minimum_proficiency":4},{"name":"SecurityEngineering","minimum_proficiency":4}]','security','["SECURITY_REVIEW","PRODUCTION_RELEASE"]',1),
('AI_DEVOPS_DIRECTOR','AI DevOps Director','DevOps','Director','AI_CTO','Department',N'Leads DevOps, cloud, and platform operations. Production changes remain blocked until release, security, and rollback approvals are satisfied.',N'["Govern platform and delivery operations","Review release readiness and observability","Escalate reliability and security incidents"]','[{"name":"DevOpsEngineering","minimum_proficiency":4},{"name":"CloudEngineering","minimum_proficiency":3}]','devops','["PRODUCTION_RELEASE","SECURITY_REVIEW"]',1),
('AI_SUPPORT_DIRECTOR','AI Support Director','Support','Director','AI_COO','Department',N'Leads service desk, support tiers, and incident response. Ensures clear service ownership, safe escalation, and auditable incident handoffs.',N'["Manage support coverage and escalation","Review incident and service trends","Coordinate support readiness and handoff"]','[{"name":"SupportOperations","minimum_proficiency":4},{"name":"IncidentManagement","minimum_proficiency":3}]','support','["HANDOFF","ESCALATION"]',1);

UPDATE target SET
    PositionName=source.PositionName, DepartmentName=source.DepartmentName, Grade=source.Grade,
    ReportsToRoleCode=source.ReportsToRoleCode, OrgLayer=source.OrgLayer,
    JobDescription=source.JobDescription, ResponsibilitiesJson=source.ResponsibilitiesJson,
    RequiredSkillsJson=source.RequiredSkillsJson, ApprovalScope=source.ApprovalScope,
    QualityGatesJson=source.QualityGatesJson, MaxRecommendedAutonomy=source.MaxRecommendedAutonomy,
    ProfileVersion='2.1.0', Status='Active'
FROM dbo.WorkforceRoleProfile target JOIN @Heads source ON source.RoleCode=target.RoleCode;

INSERT dbo.WorkforceRoleProfile
    (RoleCode, PositionName, DepartmentName, Grade, JobDescription, ResponsibilitiesJson,
     RequiredSkillsJson, ProfileVersion, Status, ReportsToRoleCode, OrgLayer, ApprovalScope,
     QualityGatesJson, MaxRecommendedAutonomy)
SELECT source.RoleCode, source.PositionName, source.DepartmentName, source.Grade,
       source.JobDescription, source.ResponsibilitiesJson, source.RequiredSkillsJson,
       '2.1.0', 'Active', source.ReportsToRoleCode, source.OrgLayer, source.ApprovalScope,
       source.QualityGatesJson, source.MaxRecommendedAutonomy
FROM @Heads source
WHERE NOT EXISTS (SELECT 1 FROM dbo.WorkforceRoleProfile target WHERE target.RoleCode=source.RoleCode);
GO

UPDATE dbo.WorkforceRoleProfile
SET DepartmentName='Development', Grade='Senior', ReportsToRoleCode='TECHNICAL_LEAD',
    OrgLayer='Specialist', ApprovalScope='application_development',
    QualityGatesJson='["SELF_REVIEW","PEER_REVIEW"]', MaxRecommendedAutonomy=2,
    ProfileVersion='2.1.0'
WHERE RoleCode='SOFTWARE_DEVELOPER' AND Status='Active';
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

IF COL_LENGTH('dbo.Agent', 'WorkforceRoleCode') IS NULL
    ALTER TABLE dbo.Agent ADD WorkforceRoleCode varchar(60) NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name='FK_Agent_WorkforceRoleProfile')
    ALTER TABLE dbo.Agent ADD CONSTRAINT FK_Agent_WorkforceRoleProfile
        FOREIGN KEY(WorkforceRoleCode) REFERENCES dbo.WorkforceRoleProfile(RoleCode);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.Agent') AND name='UX_Agent_Company_WorkforceRoleCode')
    CREATE UNIQUE INDEX UX_Agent_Company_WorkforceRoleCode
        ON dbo.Agent(CompanyID, WorkforceRoleCode) WHERE WorkforceRoleCode IS NOT NULL;
GO

IF OBJECT_ID('dbo.OrganizationBootstrapRun', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.OrganizationBootstrapRun(
        BootstrapRunID uniqueidentifier NOT NULL PRIMARY KEY,
        CompanyID uniqueidentifier NOT NULL REFERENCES dbo.Company(CompanyID),
        TriggerRequirementID uniqueidentifier NOT NULL REFERENCES dbo.Requirement(RequirementID),
        TriggerApprovalID uniqueidentifier NOT NULL REFERENCES dbo.Approval(ApprovalID),
        Status varchar(20) NOT NULL,
        RoleCount int NOT NULL,
        CreatedAgentCount int NOT NULL,
        ReusedAgentCount int NOT NULL,
        CreatedAtUtc datetime2 NOT NULL,
        CompletedAtUtc datetime2 NULL,
        CONSTRAINT UQ_OrganizationBootstrapRun_Company UNIQUE(CompanyID),
        CONSTRAINT CK_OrganizationBootstrapRun_Status CHECK (Status IN ('Running','Completed'))
    );
END;
GO
