/*
Migration 27 - runtime review lease, idempotent review decision, reviewer and reaper service roles.

NOT applied automatically. Apply migration 23 first, test both on a restored copy of
AICompany, then run on the live database during a maintenance window.
Idempotent: safe to re-run.
*/
USE AICompany;
GO

IF OBJECT_ID('dbo.AgentExecution','U') IS NULL
   OR OBJECT_ID('dbo.AgentRuntimeDefect','U') IS NULL
   OR OBJECT_ID('dbo.Role','U') IS NULL
   OR OBJECT_ID('dbo.AppUser','U') IS NULL
    THROW 51700,'Apply the runtime (12, 13) and identity (04) schemas before migration 27.',1;
GO

SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF COL_LENGTH('dbo.AgentExecution','ReviewOwnerUserID') IS NULL
        ALTER TABLE dbo.AgentExecution ADD ReviewOwnerUserID uniqueidentifier NULL;
    IF COL_LENGTH('dbo.AgentExecution','ReviewLeaseExpiresAtUtc') IS NULL
        ALTER TABLE dbo.AgentExecution ADD ReviewLeaseExpiresAtUtc datetime2 NULL;
    IF COL_LENGTH('dbo.AgentExecution','ReviewAttempt') IS NULL
        ALTER TABLE dbo.AgentExecution ADD ReviewAttempt int NOT NULL
            CONSTRAINT DF_AgentExecution_ReviewAttempt DEFAULT 0;
    IF COL_LENGTH('dbo.AgentExecution','ReviewKey') IS NULL
        ALTER TABLE dbo.AgentExecution ADD ReviewKey varchar(100) NULL;
    IF COL_LENGTH('dbo.AgentExecution','ReviewDecision') IS NULL
        ALTER TABLE dbo.AgentExecution ADD ReviewDecision varchar(10) NULL;
    IF COL_LENGTH('dbo.AppUser','CreatedByUserID') IS NULL
        ALTER TABLE dbo.AppUser ADD CreatedByUserID uniqueidentifier NULL;
    IF NOT EXISTS (
        SELECT 1 FROM sys.foreign_keys WHERE name='FK_AppUser_CreatedByUser'
    )
        ALTER TABLE dbo.AppUser ADD CONSTRAINT FK_AppUser_CreatedByUser
            FOREIGN KEY(CreatedByUserID) REFERENCES dbo.AppUser(UserID);

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF NOT EXISTS (
        SELECT 1 FROM sys.foreign_keys WHERE name='FK_AgentExecution_ReviewOwner'
    )
        ALTER TABLE dbo.AgentExecution ADD CONSTRAINT FK_AgentExecution_ReviewOwner
            FOREIGN KEY(ReviewOwnerUserID) REFERENCES dbo.AppUser(UserID);

    IF NOT EXISTS (
        SELECT 1 FROM sys.check_constraints WHERE name='CK_AgentExecution_ReviewDecision'
    )
        ALTER TABLE dbo.AgentExecution ADD CONSTRAINT CK_AgentExecution_ReviewDecision
            CHECK (ReviewDecision IS NULL OR ReviewDecision IN ('Approved','Rejected'));

    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name='IX_AgentExecution_ReviewLease' AND object_id=OBJECT_ID('dbo.AgentExecution')
    )
        CREATE INDEX IX_AgentExecution_ReviewLease
            ON dbo.AgentExecution(Status,ReviewLeaseExpiresAtUtc) INCLUDE(ReviewOwnerUserID,ReviewAttempt);

    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name='IX_AgentRuntimeDefect_Task_Status' AND object_id=OBJECT_ID('dbo.AgentRuntimeDefect')
    )
        CREATE INDEX IX_AgentRuntimeDefect_Task_Status
            ON dbo.AgentRuntimeDefect(TaskID,Status);

    -- Service roles are explicit principals, not administrative privilege tiers.
    IF NOT EXISTS (
        SELECT 1 FROM dbo.Role WITH (UPDLOCK,HOLDLOCK) WHERE RoleCode='RUNTIME_REVIEWER'
    )
        INSERT dbo.Role(RoleID,RoleCode,RoleName,RoleLevel,IsActive)
        VALUES(NEWID(),'RUNTIME_REVIEWER',N'Runtime Reviewer',5,1);

    IF NOT EXISTS (
        SELECT 1 FROM dbo.Role WITH (UPDLOCK,HOLDLOCK) WHERE RoleCode='RUNTIME_REAPER'
    )
        INSERT dbo.Role(RoleID,RoleCode,RoleName,RoleLevel,IsActive)
        VALUES(NEWID(),'RUNTIME_REAPER',N'Runtime Lease Reaper',5,1);

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

SELECT RoleCode,RoleName,RoleLevel,IsActive FROM dbo.Role WHERE RoleCode='RUNTIME_REVIEWER';
GO

/*
The standalone reaper sets SESSION_CONTEXT(UserID) to its dedicated AppUser.
When the optional native ownership RLS policy is installed, authorize that
service role for owner-scoped rows needed by the existing reaper. The app
middleware denies this role on all HTTP routes.
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID('Security.fn_CanAccessOwner','IF') IS NOT NULL
BEGIN
    DECLARE @ownership_policy_was_enabled bit = 0;
    IF EXISTS (
        SELECT 1 FROM sys.security_policies
        WHERE schema_id=SCHEMA_ID('Security') AND name='WorkforceOwnershipPolicy' AND is_enabled=1
    )
        SET @ownership_policy_was_enabled=1;

    BEGIN TRY
        BEGIN TRANSACTION;
        IF @ownership_policy_was_enabled=1
        BEGIN
            ALTER SECURITY POLICY Security.WorkforceOwnershipPolicy WITH (STATE=OFF);
        END;

        EXEC(N'CREATE OR ALTER FUNCTION Security.fn_CanAccessOwner(@OwnerUserID uniqueidentifier)
    RETURNS TABLE WITH SCHEMABINDING AS RETURN
    SELECT 1 AS access_result
    WHERE EXISTS (
      SELECT 1
      FROM dbo.AppUser AS actor
      JOIN dbo.Role AS actor_role ON actor_role.RoleID=actor.RoleID
      WHERE actor.UserID=TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N''UserID''))
        AND actor.IsActive=1 AND actor_role.IsActive=1
        AND (
          actor_role.RoleCode=''SUPER_ADMIN''
          OR actor_role.RoleCode=''RUNTIME_REAPER''
          OR (actor_role.RoleCode=''USER'' AND @OwnerUserID=actor.UserID)
          OR (actor_role.RoleCode IN (''MANAGER'',''DEPARTMENT_HEAD'')
              AND actor.CompanyID IS NOT NULL AND actor.DepartmentID IS NOT NULL
              AND EXISTS (SELECT 1 FROM dbo.AppUser AS owner_user
                          WHERE owner_user.UserID=@OwnerUserID AND owner_user.IsActive=1
                            AND owner_user.CompanyID=actor.CompanyID
                            AND owner_user.DepartmentID=actor.DepartmentID))
          OR (actor_role.RoleCode IN (''EXECUTIVE'',''OWNER'')
              AND actor.CompanyID IS NOT NULL
              AND EXISTS (SELECT 1 FROM dbo.AppUser AS owner_user
                          WHERE owner_user.UserID=@OwnerUserID AND owner_user.IsActive=1
                            AND owner_user.CompanyID=actor.CompanyID))
        )
    );');
        IF @ownership_policy_was_enabled=1
            ALTER SECURITY POLICY Security.WorkforceOwnershipPolicy WITH (STATE=ON);
        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;
GO
