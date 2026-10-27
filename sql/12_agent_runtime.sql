USE AICompany;
GO

IF OBJECT_ID('dbo.AgentTaskQueue', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.AgentTaskQueue(
        QueueID uniqueidentifier NOT NULL PRIMARY KEY,
        TaskID uniqueidentifier NOT NULL UNIQUE REFERENCES dbo.Task(TaskID),
        AgentID uniqueidentifier NOT NULL REFERENCES dbo.Agent(AgentID),
        Status varchar(30) NOT NULL,
        AttemptCount int NOT NULL DEFAULT 0,
        MaxAttempts int NOT NULL DEFAULT 3,
        AvailableAtUtc datetime2 NOT NULL,
        LeaseOwner nvarchar(200) NULL,
        LeaseExpiresAtUtc datetime2 NULL,
        LastFailure nvarchar(2000) NULL,
        EscalatedAtUtc datetime2 NULL,
        CreatedAtUtc datetime2 NOT NULL,
        ModifiedAtUtc datetime2 NOT NULL,
        CONSTRAINT CK_AgentTaskQueue_Status CHECK(Status IN ('Queued','Claimed','Executing','Review','Retry','Completed','Failed','Escalated','Cancelled')),
        CONSTRAINT CK_AgentTaskQueue_Attempts CHECK(AttemptCount >= 0 AND MaxAttempts > 0)
    );
END;
GO

IF OBJECT_ID('dbo.AgentExecution', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.AgentExecution(
        ExecutionID uniqueidentifier NOT NULL PRIMARY KEY,
        QueueID uniqueidentifier NOT NULL REFERENCES dbo.AgentTaskQueue(QueueID),
        TaskID uniqueidentifier NOT NULL REFERENCES dbo.Task(TaskID),
        AgentID uniqueidentifier NOT NULL REFERENCES dbo.Agent(AgentID),
        AttemptNumber int NOT NULL,
        Status varchar(30) NOT NULL,
        CorrelationID uniqueidentifier NOT NULL,
        InputSnapshot nvarchar(max) NOT NULL,
        StartedAtUtc datetime2 NOT NULL,
        HeartbeatAtUtc datetime2 NOT NULL,
        CompletedAtUtc datetime2 NULL,
        FailureReason nvarchar(2000) NULL,
        CONSTRAINT UQ_AgentExecution_Queue_Attempt UNIQUE(QueueID,AttemptNumber),
        CONSTRAINT CK_AgentExecution_Status CHECK(Status IN ('Executing','OutputSubmitted','Review','QARejected','Completed','Failed','Escalated'))
    );
END;
GO

IF OBJECT_ID('dbo.AgentExecutionOutput', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.AgentExecutionOutput(
        OutputID uniqueidentifier NOT NULL PRIMARY KEY,
        ExecutionID uniqueidentifier NOT NULL REFERENCES dbo.AgentExecution(ExecutionID),
        OutputName nvarchar(250) NOT NULL,
        ContentType varchar(100) NOT NULL,
        Content nvarchar(max) NOT NULL,
        Sha256 char(64) NOT NULL,
        CreatedAtUtc datetime2 NOT NULL,
        CONSTRAINT UQ_AgentExecutionOutput_Execution_Name UNIQUE(ExecutionID,OutputName)
    );
END;
GO

IF OBJECT_ID('dbo.AgentRuntimeEvent', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.AgentRuntimeEvent(
        RuntimeEventID uniqueidentifier NOT NULL PRIMARY KEY,
        ExecutionID uniqueidentifier NULL REFERENCES dbo.AgentExecution(ExecutionID),
        QueueID uniqueidentifier NULL REFERENCES dbo.AgentTaskQueue(QueueID),
        TaskID uniqueidentifier NULL REFERENCES dbo.Task(TaskID),
        AgentID uniqueidentifier NULL REFERENCES dbo.Agent(AgentID),
        EventType varchar(50) NOT NULL,
        Severity varchar(20) NOT NULL,
        ActorType varchar(30) NOT NULL,
        ActorID nvarchar(200) NOT NULL,
        Details nvarchar(max) NOT NULL,
        CreatedAtUtc datetime2 NOT NULL
    );
END;
GO

IF OBJECT_ID('dbo.AgentRuntimeEscalation', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.AgentRuntimeEscalation(
        EscalationID uniqueidentifier NOT NULL PRIMARY KEY,
        QueueID uniqueidentifier NOT NULL REFERENCES dbo.AgentTaskQueue(QueueID),
        TaskID uniqueidentifier NOT NULL REFERENCES dbo.Task(TaskID),
        AgentID uniqueidentifier NOT NULL REFERENCES dbo.Agent(AgentID),
        EscalationCode varchar(60) NOT NULL,
        Severity varchar(20) NOT NULL,
        Reason nvarchar(2000) NOT NULL,
        Status varchar(20) NOT NULL,
        CreatedAtUtc datetime2 NOT NULL,
        ResolvedAtUtc datetime2 NULL,
        ResolvedBy nvarchar(200) NULL,
        Resolution nvarchar(2000) NULL,
        CONSTRAINT CK_AgentRuntimeEscalation_Status CHECK(Status IN ('Open','Resolved'))
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

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.AgentTaskQueue') AND name='IX_AgentTaskQueue_Claim')
    CREATE INDEX IX_AgentTaskQueue_Claim ON dbo.AgentTaskQueue(Status,AvailableAtUtc,LeaseExpiresAtUtc,AgentID);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.AgentExecution') AND name='IX_AgentExecution_Agent_Status')
    CREATE INDEX IX_AgentExecution_Agent_Status ON dbo.AgentExecution(AgentID,Status,StartedAtUtc);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.AgentRuntimeEscalation') AND name='IX_AgentRuntimeEscalation_Status')
    CREATE INDEX IX_AgentRuntimeEscalation_Status ON dbo.AgentRuntimeEscalation(Status,Severity,CreatedAtUtc);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.AgentRuntimeDefect') AND name='IX_AgentRuntimeDefect_Status')
    CREATE INDEX IX_AgentRuntimeDefect_Status ON dbo.AgentRuntimeDefect(Status,Priority,CreatedAtUtc);
GO
