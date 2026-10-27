/*
    Execution adapter configuration and health-check history.
    This migration does not activate agents, create worker credentials, or execute tasks.
    Secret material must remain in an external secret manager; only a secret reference is stored.
*/
USE AICompany;
GO

IF OBJECT_ID('dbo.ExecutionAdapterConfig','U') IS NULL
BEGIN
    CREATE TABLE dbo.ExecutionAdapterConfig(
        AdapterConfigID uniqueidentifier NOT NULL CONSTRAINT PK_ExecutionAdapterConfig PRIMARY KEY,
        ProviderCode varchar(40) NOT NULL CONSTRAINT UQ_ExecutionAdapterConfig_Provider UNIQUE,
        DisplayName nvarchar(120) NOT NULL,
        EndpointUrl nvarchar(1000) NULL,
        DeploymentName nvarchar(200) NULL,
        ModelCatalogID uniqueidentifier NULL REFERENCES dbo.AIModelCatalog(ModelCatalogID),
        SecretReference nvarchar(500) NULL,
        Status varchar(20) NOT NULL CONSTRAINT DF_ExecutionAdapterConfig_Status DEFAULT 'Disabled',
        CreatedAtUtc datetime2 NOT NULL CONSTRAINT DF_ExecutionAdapterConfig_CreatedAt DEFAULT SYSUTCDATETIME(),
        CreatedByUserID uniqueidentifier NOT NULL REFERENCES dbo.AppUser(UserID),
        ModifiedAtUtc datetime2 NOT NULL CONSTRAINT DF_ExecutionAdapterConfig_ModifiedAt DEFAULT SYSUTCDATETIME(),
        ModifiedByUserID uniqueidentifier NOT NULL REFERENCES dbo.AppUser(UserID),
        CONSTRAINT CK_ExecutionAdapterConfig_Provider CHECK(ProviderCode IN ('AZURE_OPENAI','OPENAI','GOOGLE_VERTEX','ANTHROPIC')),
        CONSTRAINT CK_ExecutionAdapterConfig_Status CHECK(Status IN ('Disabled','Configured','Retired'))
    );
END;
GO

IF OBJECT_ID('dbo.ExecutionAdapterHealthCheck','U') IS NULL
BEGIN
    CREATE TABLE dbo.ExecutionAdapterHealthCheck(
        HealthCheckID uniqueidentifier NOT NULL CONSTRAINT PK_ExecutionAdapterHealthCheck PRIMARY KEY,
        AdapterConfigID uniqueidentifier NOT NULL REFERENCES dbo.ExecutionAdapterConfig(AdapterConfigID),
        Status varchar(30) NOT NULL,
        Details nvarchar(2000) NOT NULL,
        CheckedAtUtc datetime2 NOT NULL CONSTRAINT DF_ExecutionAdapterHealthCheck_CheckedAt DEFAULT SYSUTCDATETIME(),
        CheckedByUserID uniqueidentifier NOT NULL REFERENCES dbo.AppUser(UserID),
        CONSTRAINT CK_ExecutionAdapterHealthCheck_Status CHECK(Status IN ('ConfigurationIncomplete','NotChecked','Healthy','Unhealthy','Error'))
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.ExecutionAdapterHealthCheck') AND name='IX_ExecutionAdapterHealthCheck_Config_CheckedAt')
    CREATE INDEX IX_ExecutionAdapterHealthCheck_Config_CheckedAt ON dbo.ExecutionAdapterHealthCheck(AdapterConfigID,CheckedAtUtc DESC);
GO
