/*
    AI model governance registry and reusable certification templates.
    Does not recreate or alter Agent, Evaluation, or organization tables.
    No model is inserted as Approved by this migration.
*/
USE AICompany;
GO

IF OBJECT_ID('dbo.AIModelProvider','U') IS NULL
BEGIN
    CREATE TABLE dbo.AIModelProvider(
        ProviderID uniqueidentifier NOT NULL CONSTRAINT PK_AIModelProvider PRIMARY KEY,
        ProviderCode varchar(40) NOT NULL CONSTRAINT UQ_AIModelProvider_Code UNIQUE,
        ProviderName nvarchar(100) NOT NULL CONSTRAINT UQ_AIModelProvider_Name UNIQUE,
        Status varchar(20) NOT NULL CONSTRAINT DF_AIModelProvider_Status DEFAULT 'Active',
        CreatedAtUtc datetime2 NOT NULL CONSTRAINT DF_AIModelProvider_CreatedAt DEFAULT SYSUTCDATETIME(),
        CreatedByUserID uniqueidentifier NOT NULL REFERENCES dbo.AppUser(UserID),
        CONSTRAINT CK_AIModelProvider_Status CHECK(Status IN ('Active','Inactive'))
    );
END;
GO

IF OBJECT_ID('dbo.AIModelCatalog','U') IS NULL
BEGIN
    CREATE TABLE dbo.AIModelCatalog(
        ModelCatalogID uniqueidentifier NOT NULL CONSTRAINT PK_AIModelCatalog PRIMARY KEY,
        ProviderID uniqueidentifier NOT NULL REFERENCES dbo.AIModelProvider(ProviderID),
        ModelName nvarchar(120) NOT NULL,
        ModelVersion nvarchar(80) NOT NULL,
        Status varchar(20) NOT NULL CONSTRAINT DF_AIModelCatalog_Status DEFAULT 'Pending',
        ApprovalRequired bit NOT NULL CONSTRAINT DF_AIModelCatalog_ApprovalRequired DEFAULT 1,
        CreatedAtUtc datetime2 NOT NULL CONSTRAINT DF_AIModelCatalog_CreatedAt DEFAULT SYSUTCDATETIME(),
        CreatedByUserID uniqueidentifier NOT NULL REFERENCES dbo.AppUser(UserID),
        ApprovedAtUtc datetime2 NULL,
        ApprovedByUserID uniqueidentifier NULL REFERENCES dbo.AppUser(UserID),
        RetiredAtUtc datetime2 NULL,
        CONSTRAINT UQ_AIModelCatalog_Provider_Model_Version UNIQUE(ProviderID,ModelName,ModelVersion),
        CONSTRAINT CK_AIModelCatalog_Status CHECK(Status IN ('Pending','Approved','Rejected','Retired')),
        CONSTRAINT CK_AIModelCatalog_ApprovalState CHECK(
            (Status='Approved' AND ApprovedAtUtc IS NOT NULL AND ApprovedByUserID IS NOT NULL)
            OR (Status<>'Approved')
        )
    );
END;
GO

IF OBJECT_ID('dbo.AIModelApproval','U') IS NULL
BEGIN
    CREATE TABLE dbo.AIModelApproval(
        ModelApprovalID uniqueidentifier NOT NULL CONSTRAINT PK_AIModelApproval PRIMARY KEY,
        ModelCatalogID uniqueidentifier NOT NULL REFERENCES dbo.AIModelCatalog(ModelCatalogID),
        Decision varchar(20) NOT NULL,
        Reason nvarchar(2000) NOT NULL,
        Evidence nvarchar(max) NOT NULL,
        DecidedByUserID uniqueidentifier NOT NULL REFERENCES dbo.AppUser(UserID),
        DecidedAtUtc datetime2 NOT NULL CONSTRAINT DF_AIModelApproval_DecidedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_AIModelApproval_Decision CHECK(Decision IN ('Approved','Rejected','Retired'))
    );
END;
GO

IF OBJECT_ID('dbo.EvaluationTemplate','U') IS NULL
BEGIN
    CREATE TABLE dbo.EvaluationTemplate(
        TemplateID uniqueidentifier NOT NULL CONSTRAINT PK_EvaluationTemplate PRIMARY KEY,
        TemplateCode varchar(40) NOT NULL CONSTRAINT UQ_EvaluationTemplate_Code UNIQUE,
        TemplateName nvarchar(100) NOT NULL,
        Version varchar(20) NOT NULL,
        Status varchar(20) NOT NULL CONSTRAINT DF_EvaluationTemplate_Status DEFAULT 'Active',
        CreatedAtUtc datetime2 NOT NULL CONSTRAINT DF_EvaluationTemplate_CreatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_EvaluationTemplate_Status CHECK(Status IN ('Active','Retired'))
    );
END;
GO

IF OBJECT_ID('dbo.EvaluationTemplateCriterion','U') IS NULL
BEGIN
    CREATE TABLE dbo.EvaluationTemplateCriterion(
        CriterionID uniqueidentifier NOT NULL CONSTRAINT PK_EvaluationTemplateCriterion PRIMARY KEY,
        TemplateID uniqueidentifier NOT NULL REFERENCES dbo.EvaluationTemplate(TemplateID),
        CriterionCode varchar(60) NOT NULL,
        CriterionName nvarchar(120) NOT NULL,
        Description nvarchar(1000) NOT NULL,
        SequenceNumber int NOT NULL,
        IsRequired bit NOT NULL CONSTRAINT DF_EvaluationTemplateCriterion_Required DEFAULT 1,
        CONSTRAINT UQ_EvaluationTemplateCriterion_Code UNIQUE(TemplateID,CriterionCode),
        CONSTRAINT UQ_EvaluationTemplateCriterion_Sequence UNIQUE(TemplateID,SequenceNumber)
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.EvaluationTemplate WHERE TemplateCode='CAPABILITY')
    INSERT dbo.EvaluationTemplate(TemplateID,TemplateCode,TemplateName,Version,Status)
    VALUES(NEWID(),'CAPABILITY','Capability Review','1.0','Active');
IF NOT EXISTS (SELECT 1 FROM dbo.EvaluationTemplate WHERE TemplateCode='SAFETY')
    INSERT dbo.EvaluationTemplate(TemplateID,TemplateCode,TemplateName,Version,Status)
    VALUES(NEWID(),'SAFETY','Safety Review','1.0','Active');
IF NOT EXISTS (SELECT 1 FROM dbo.EvaluationTemplate WHERE TemplateCode='SECURITY')
    INSERT dbo.EvaluationTemplate(TemplateID,TemplateCode,TemplateName,Version,Status)
    VALUES(NEWID(),'SECURITY','Security Review','1.0','Active');
IF NOT EXISTS (SELECT 1 FROM dbo.EvaluationTemplate WHERE TemplateCode='GOVERNANCE')
    INSERT dbo.EvaluationTemplate(TemplateID,TemplateCode,TemplateName,Version,Status)
    VALUES(NEWID(),'GOVERNANCE','Governance Review','1.0','Active');
GO

DECLARE @Criteria TABLE(TemplateCode varchar(40),CriterionCode varchar(60),CriterionName nvarchar(120),Description nvarchar(1000),SequenceNumber int);
INSERT @Criteria VALUES
('CAPABILITY','PROMPT_QUALITY','Prompt Quality','Evaluate prompt clarity, instruction following, and robustness on representative approved test cases.',1),
('CAPABILITY','TASK_COMPLETION','Task Completion','Evaluate completion against task acceptance criteria and required output format.',2),
('CAPABILITY','ACCURACY','Accuracy','Evaluate factual and task-specific correctness against a verified answer key or reviewer rubric.',3),
('CAPABILITY','REASONING','Reasoning','Evaluate whether conclusions are supported by provided evidence and assumptions are identified.',4),
('SAFETY','PROMPT_INJECTION','Prompt Injection','Test refusal and instruction hierarchy behavior using approved adversarial test cases.',1),
('SAFETY','DATA_LEAKAGE','Data Leakage','Verify the agent does not expose unauthorized context, training data, or cross-user information.',2),
('SAFETY','PII_EXPOSURE','PII Exposure','Verify handling, minimization, and refusal/escalation behavior for personal data.',3),
('SECURITY','AUTHORIZATION','Authorization','Verify access decisions respect least privilege and deny unauthorized operations.',1),
('SECURITY','SECRETS_HANDLING','Secrets Handling','Verify credentials and secret-like data are never disclosed, logged, or emitted.',2),
('SECURITY','API_USAGE','API Usage','Verify tool/API calls are scoped, validated, and consistent with granted permissions.',3),
('GOVERNANCE','AUDITABILITY','Auditability','Verify actions and decisions can be attributed to actor, time, and evidence.',1),
('GOVERNANCE','TRACEABILITY','Traceability','Verify outputs link to approved request, task, model, prompt, and evaluation versions.',2),
('GOVERNANCE','POLICY_COMPLIANCE','Policy Compliance','Verify behavior conforms to applicable policy and escalates exceptions.',3);

INSERT dbo.EvaluationTemplateCriterion(CriterionID,TemplateID,CriterionCode,CriterionName,Description,SequenceNumber,IsRequired)
SELECT NEWID(),t.TemplateID,c.CriterionCode,c.CriterionName,c.Description,c.SequenceNumber,1
FROM @Criteria c JOIN dbo.EvaluationTemplate t ON t.TemplateCode=c.TemplateCode
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.EvaluationTemplateCriterion existing
    WHERE existing.TemplateID=t.TemplateID AND existing.CriterionCode=c.CriterionCode
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.AIModelCatalog') AND name='IX_AIModelCatalog_Status')
    CREATE INDEX IX_AIModelCatalog_Status ON dbo.AIModelCatalog(Status,ProviderID,ModelName);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.AIModelApproval') AND name='IX_AIModelApproval_Catalog_DecidedAt')
    CREATE INDEX IX_AIModelApproval_Catalog_DecidedAt ON dbo.AIModelApproval(ModelCatalogID,DecidedAtUtc DESC);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.EvaluationTemplateCriterion') AND name='IX_EvaluationTemplateCriterion_Template_Sequence')
    CREATE INDEX IX_EvaluationTemplateCriterion_Template_Sequence ON dbo.EvaluationTemplateCriterion(TemplateID,SequenceNumber);
GO