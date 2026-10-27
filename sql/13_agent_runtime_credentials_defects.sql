USE AICompany;
GO

IF OBJECT_ID('dbo.AgentRuntimeCredential', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.AgentRuntimeCredential(
        AgentID uniqueidentifier NOT NULL PRIMARY KEY REFERENCES dbo.Agent(AgentID),
        TokenHash char(64) NOT NULL,
        Status varchar(20) NOT NULL,
        CreatedAtUtc datetime2 NOT NULL,
        RotatedAtUtc datetime2 NOT NULL,
        LastUsedAtUtc datetime2 NULL,
        RevokedAtUtc datetime2 NULL,
        CreatedBy nvarchar(200) NOT NULL,
        CONSTRAINT CK_AgentRuntimeCredential_Status CHECK(Status IN ('Active','Revoked'))
    );
END;
GO

IF OBJECT_ID('dbo.AgentRuntimeDefect', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.AgentRuntimeDefect(
        DefectID uniqueidentifier NOT NULL PRIMARY KEY,
        ExecutionID uniqueidentifier NOT NULL REFERENCES dbo.AgentExecution(ExecutionID),
        TaskID uniqueidentifier NOT NULL REFERENCES dbo.Task(TaskID),
        AgentID uniqueidentifier NOT NULL REFERENCES dbo.Agent(AgentID),
        Severity varchar(20) NOT NULL,
        Priority varchar(20) NOT NULL,
        RootCause nvarchar(1000) NOT NULL,
        BusinessImpact nvarchar(1000) NOT NULL,
        TechnicalImpact nvarchar(1000) NOT NULL,
        FixRecommendation nvarchar(1000) NOT NULL,
        AssignedRoleCode varchar(60) NULL REFERENCES dbo.WorkforceRoleProfile(RoleCode),
        Status varchar(20) NOT NULL,
        CreatedAtUtc datetime2 NOT NULL,
        ClosedAtUtc datetime2 NULL,
        CONSTRAINT CK_AgentRuntimeDefect_Status CHECK(Status IN ('Open','InProgress','Retest','Closed','Escalated'))
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.AgentRuntimeCredential') AND name='IX_AgentRuntimeCredential_Status')
    CREATE INDEX IX_AgentRuntimeCredential_Status ON dbo.AgentRuntimeCredential(Status,RotatedAtUtc);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.AgentRuntimeCredential') AND name='UX_AgentRuntimeCredential_TokenHash')
    CREATE UNIQUE INDEX UX_AgentRuntimeCredential_TokenHash ON dbo.AgentRuntimeCredential(TokenHash);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.AgentRuntimeDefect') AND name='IX_AgentRuntimeDefect_Status')
    CREATE INDEX IX_AgentRuntimeDefect_Status ON dbo.AgentRuntimeDefect(Status,Priority,CreatedAtUtc);
GO
