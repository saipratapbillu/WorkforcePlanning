/*
    RLS identity prerequisites.
    Reuses Company, Department, Position, AppUser, and Role; creates no tables.
    No membership backfill is attempted. Department text did not uniquely map
    to the Department catalog in the audited data. Populate only from an
    approved HR/user-to-organization mapping source.

    This is an unexecuted DEV migration draft. Set the gate only in a reviewed
    DEV session after backup and mapping approval.
*/
USE AICompany;
GO
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF ISNULL(TRY_CONVERT(bit,SESSION_CONTEXT(N'ApplyRlsIdentityMigration')),0)<>1
    BEGIN
        ;THROW 51100,'Identity migration blocked. Set ApplyRlsIdentityMigration=1 on an approved DEV session.',1;
    END;

    IF OBJECT_ID('dbo.Company','U') IS NULL OR OBJECT_ID('dbo.Department','U') IS NULL
       OR OBJECT_ID('dbo.Position','U') IS NULL OR OBJECT_ID('dbo.AppUser','U') IS NULL
       OR OBJECT_ID('dbo.Role','U') IS NULL
    BEGIN
        ;THROW 51101,'Required existing organization tables are missing; this script will not create them.',1;
    END;

    IF COL_LENGTH('dbo.AppUser','CompanyID') IS NULL
        EXEC(N'ALTER TABLE dbo.AppUser ADD CompanyID uniqueidentifier NULL;');
    IF COL_LENGTH('dbo.AppUser','DepartmentID') IS NULL
        EXEC(N'ALTER TABLE dbo.AppUser ADD DepartmentID uniqueidentifier NULL;');
    IF COL_LENGTH('dbo.AppUser','PositionID') IS NULL
        EXEC(N'ALTER TABLE dbo.AppUser ADD PositionID uniqueidentifier NULL;');

    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID('dbo.AppUser') AND name='FK_AppUser_Company')
        EXEC(N'ALTER TABLE dbo.AppUser WITH CHECK ADD CONSTRAINT FK_AppUser_Company FOREIGN KEY(CompanyID) REFERENCES dbo.Company(CompanyID);');
    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID('dbo.AppUser') AND name='FK_AppUser_Department')
        EXEC(N'ALTER TABLE dbo.AppUser WITH CHECK ADD CONSTRAINT FK_AppUser_Department FOREIGN KEY(DepartmentID) REFERENCES dbo.Department(DepartmentID);');
    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID('dbo.AppUser') AND name='FK_AppUser_Position')
        EXEC(N'ALTER TABLE dbo.AppUser WITH CHECK ADD CONSTRAINT FK_AppUser_Position FOREIGN KEY(PositionID) REFERENCES dbo.Position(PositionID);');

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.Department') AND name='UX_Department_DepartmentID_CompanyID')
        EXEC(N'CREATE UNIQUE INDEX UX_Department_DepartmentID_CompanyID ON dbo.Department(DepartmentID,CompanyID);');
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.Position') AND name='UX_Position_PositionID_DepartmentID')
        EXEC(N'CREATE UNIQUE INDEX UX_Position_PositionID_DepartmentID ON dbo.Position(PositionID,DepartmentID);');

    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID('dbo.AppUser') AND name='FK_AppUser_DepartmentCompany')
        EXEC(N'ALTER TABLE dbo.AppUser WITH CHECK ADD CONSTRAINT FK_AppUser_DepartmentCompany FOREIGN KEY(DepartmentID,CompanyID) REFERENCES dbo.Department(DepartmentID,CompanyID);');
    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID('dbo.AppUser') AND name='FK_AppUser_PositionDepartment')
        EXEC(N'ALTER TABLE dbo.AppUser WITH CHECK ADD CONSTRAINT FK_AppUser_PositionDepartment FOREIGN KEY(PositionID,DepartmentID) REFERENCES dbo.Position(PositionID,DepartmentID);');

    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID('dbo.AppUser') AND name='FK_AppUser_Role')
        EXEC(N'ALTER TABLE dbo.AppUser WITH CHECK ADD CONSTRAINT FK_AppUser_Role FOREIGN KEY(RoleID) REFERENCES dbo.Role(RoleID);');

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
