USE AICompany;
GO

IF OBJECT_ID('dbo.WorkforceReuseAssessment','U') IS NULL
BEGIN
    CREATE TABLE dbo.WorkforceReuseAssessment(
        AssessmentID uniqueidentifier NOT NULL PRIMARY KEY,
        ProjectID uniqueidentifier NOT NULL REFERENCES dbo.Project(ProjectID),
        TaskID uniqueidentifier NULL REFERENCES dbo.Task(TaskID),
        RoleCode varchar(60) NOT NULL REFERENCES dbo.WorkforceRoleProfile(RoleCode),
        AgentID uniqueidentifier NOT NULL REFERENCES dbo.Agent(AgentID),
        MatchScore int NOT NULL,
        Classification varchar(30) NOT NULL,
        SkillPlanJson nvarchar(max) NOT NULL,
        MissingCertificationsJson nvarchar(max) NOT NULL,
        CapacityAvailable bit NOT NULL,
        EstimatedReadinessDays int NOT NULL,
        AssessmentStatus varchar(30) NOT NULL,
        AssessedAtUtc datetime2 NOT NULL,
        DecisionBy nvarchar(200) NULL,
        DecisionAtUtc datetime2 NULL,
        DecisionReason nvarchar(2000) NULL,
        CompletedAtUtc datetime2 NULL,
        CompletionEvidence nvarchar(4000) NULL,
        CONSTRAINT CK_WorkforceReuseAssessment_MatchScore CHECK (MatchScore BETWEEN 0 AND 100),
        CONSTRAINT CK_WorkforceReuseAssessment_Classification CHECK
            (Classification IN ('Ready Candidate','Strong Candidate','Upskill Candidate','Workforce Request')),
        CONSTRAINT CK_WorkforceReuseAssessment_Status CHECK
            (AssessmentStatus IN ('Considered','PendingApproval','Approved','Rejected','Completed','Assigned')),
        CONSTRAINT UQ_WorkforceReuseAssessment_Project_Role_Agent UNIQUE(ProjectID,RoleCode,AgentID)
    );
    CREATE INDEX IX_WorkforceReuseAssessment_Review
        ON dbo.WorkforceReuseAssessment(AssessmentStatus,AssessedAtUtc DESC)
        INCLUDE(ProjectID,RoleCode,AgentID,MatchScore,Classification);
END;
GO

IF EXISTS (SELECT 1 FROM sys.check_constraints
           WHERE parent_object_id=OBJECT_ID('dbo.WorkforceReuseAssessment')
             AND name='CK_WorkforceReuseAssessment_Classification')
    ALTER TABLE dbo.WorkforceReuseAssessment DROP CONSTRAINT CK_WorkforceReuseAssessment_Classification;
UPDATE dbo.WorkforceReuseAssessment
SET Classification=CASE Classification
    WHEN 'Exact Match' THEN 'Ready Candidate'
    WHEN 'Strong Match' THEN 'Strong Candidate'
    WHEN 'New Workforce Request' THEN 'Workforce Request'
    ELSE Classification
END;
ALTER TABLE dbo.WorkforceReuseAssessment WITH CHECK ADD CONSTRAINT CK_WorkforceReuseAssessment_Classification
    CHECK (Classification IN ('Ready Candidate','Strong Candidate','Upskill Candidate','Workforce Request'));

IF EXISTS (SELECT 1 FROM sys.check_constraints
           WHERE parent_object_id=OBJECT_ID('dbo.WorkforceReuseAssessment')
             AND name='CK_WorkforceReuseAssessment_Status')
    ALTER TABLE dbo.WorkforceReuseAssessment DROP CONSTRAINT CK_WorkforceReuseAssessment_Status;
ALTER TABLE dbo.WorkforceReuseAssessment WITH CHECK ADD CONSTRAINT CK_WorkforceReuseAssessment_Status
    CHECK (AssessmentStatus IN ('Considered','PendingApproval','Approved','Rejected','Completed','Assigned'));
GO