USE AICompany;
GO

IF COL_LENGTH('dbo.Agent', 'ModelProvider') IS NULL
    ALTER TABLE dbo.Agent ADD ModelProvider nvarchar(100) NULL;
GO

IF OBJECT_ID('dbo.AgentActivationBlocker', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.AgentActivationBlocker(
        BlockerID uniqueidentifier NOT NULL PRIMARY KEY,
        AgentID uniqueidentifier NOT NULL REFERENCES dbo.Agent(AgentID),
        BlockerCode varchar(60) NOT NULL,
        Description nvarchar(500) NOT NULL,
        Status varchar(20) NOT NULL,
        FirstDetectedAtUtc datetime2 NOT NULL,
        LastDetectedAtUtc datetime2 NOT NULL,
        ResolvedAtUtc datetime2 NULL,
        CONSTRAINT CK_AgentActivationBlocker_Status CHECK(Status IN ('Open','Resolved'))
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.AgentActivationBlocker') AND name='UX_AgentActivationBlocker_Open')
    CREATE UNIQUE INDEX UX_AgentActivationBlocker_Open
        ON dbo.AgentActivationBlocker(AgentID,BlockerCode) WHERE Status='Open';
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.AgentActivationBlocker') AND name='IX_AgentActivationBlocker_Status')
    CREATE INDEX IX_AgentActivationBlocker_Status ON dbo.AgentActivationBlocker(Status,LastDetectedAtUtc);
GO

UPDATE dbo.AgentActivationBlocker
SET BlockerCode=REPLACE(BlockerCode,'/','_')
WHERE BlockerCode LIKE '%/%';
UPDATE dbo.AgentActivationBlocker
SET BlockerCode='APPROVED_MODEL_IS_NOT_CONFIGURED',
    Description='approved model is not configured'
WHERE BlockerCode='APPROVED_MODEL_PROVIDER_IS_NOT_CONFIGURED';
GO