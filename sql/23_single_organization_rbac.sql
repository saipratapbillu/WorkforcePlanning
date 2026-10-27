USE AICompany;
GO

IF OBJECT_ID('dbo.Role','U') IS NULL OR OBJECT_ID('dbo.Agent','U') IS NULL
    THROW 51500,'Apply the existing identity and workforce schema before this migration.',1;
GO

SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    DECLARE @Roles TABLE(
        RoleCode varchar(50) NOT NULL PRIMARY KEY,
        RoleName nvarchar(100) NOT NULL,
        RoleLevel int NOT NULL
    );
    INSERT @Roles(RoleCode,RoleName,RoleLevel) VALUES
        ('BUSINESS_USER',N'Business User',10),
        ('APPROVER',N'Approver',20),
        ('EXECUTIVE',N'Executive',30),
        ('WORKFORCE_MANAGER',N'Workforce Manager',40),
        ('PLATFORM_OWNER',N'Platform Owner',50);

    INSERT dbo.Role(RoleID,RoleCode,RoleName,RoleLevel,IsActive)
    SELECT NEWID(),source.RoleCode,source.RoleName,source.RoleLevel,1
    FROM @Roles source
    WHERE NOT EXISTS (
        SELECT 1 FROM dbo.Role existing WITH (UPDLOCK,HOLDLOCK)
        WHERE existing.RoleCode=source.RoleCode
    );

    UPDATE target
       SET RoleName=source.RoleName,RoleLevel=source.RoleLevel,IsActive=1
    FROM dbo.Role target
    JOIN @Roles source ON source.RoleCode=target.RoleCode;

    IF EXISTS (
        SELECT 1 FROM sys.columns
        WHERE object_id=OBJECT_ID('dbo.Agent') AND name='CompanyID' AND is_nullable=0
    )
        ALTER TABLE dbo.Agent ALTER COLUMN CompanyID uniqueidentifier NULL;

    IF EXISTS (
        SELECT 1 FROM sys.columns
        WHERE object_id=OBJECT_ID('dbo.Agent') AND name='DepartmentID' AND is_nullable=0
    )
        ALTER TABLE dbo.Agent ALTER COLUMN DepartmentID uniqueidentifier NULL;

    IF EXISTS (
        SELECT 1 FROM sys.columns
        WHERE object_id=OBJECT_ID('dbo.Agent') AND name='PositionID' AND is_nullable=0
    )
        ALTER TABLE dbo.Agent ALTER COLUMN PositionID uniqueidentifier NULL;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

SELECT RoleCode,RoleName,IsActive FROM dbo.Role
WHERE RoleCode IN ('BUSINESS_USER','APPROVER','EXECUTIVE','WORKFORCE_MANAGER','PLATFORM_OWNER')
ORDER BY RoleLevel;

SELECT c.name AS AgentOrganizationColumn,c.is_nullable
FROM sys.columns c
WHERE c.object_id=OBJECT_ID('dbo.Agent')
  AND c.name IN ('CompanyID','DepartmentID','PositionID')
ORDER BY c.column_id;
GO
