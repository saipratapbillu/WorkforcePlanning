/*
    SQL Server native row-level security policies.
    Prerequisites (must be reviewed and deployed first):
      - sql/15_rls_identity_normalization.sql
      - sql/14_approved_ownership_normalization.sql
      - reviewed AppUser membership backfill and approved Role rows
      - API AuthorizationMiddleware + SQL SESSION_CONTEXT integration

    This script creates only the Security schema/functions/policy. It does not
    create or recreate application tables and contains no ownership ALTERs.
    It is unexecuted. Enable only in DEV after validation and the performance
    plan has passed. SESSION_CONTEXT UserID is set by trusted server code.
*/
USE AICompany;
GO
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF ISNULL(TRY_CONVERT(bit,SESSION_CONTEXT(N'ApplyNativeRlsMigration')),0)<>1
    BEGIN
        ;THROW 51200,'Native RLS migration blocked. Set ApplyNativeRlsMigration=1 on an approved DEV session.',1;
    END;

    IF OBJECT_ID('dbo.AppUser','U') IS NULL OR OBJECT_ID('dbo.Role','U') IS NULL
       OR COL_LENGTH('dbo.AppUser','CompanyID') IS NULL
       OR COL_LENGTH('dbo.AppUser','DepartmentID') IS NULL
      OR COL_LENGTH('dbo.AppUser','PositionID') IS NULL
       OR COL_LENGTH('dbo.Requirement','CreatedByUserID') IS NULL
       OR COL_LENGTH('dbo.Project','CreatedByUserID') IS NULL
       OR COL_LENGTH('dbo.Task','CreatedByUserID') IS NULL
       OR COL_LENGTH('dbo.Issue','OwnerUserID') IS NULL
    BEGIN
        ;THROW 51201,'RLS prerequisites are incomplete. Apply and validate identity and ownership migrations first.',1;
    END;

    IF EXISTS (SELECT 1 FROM dbo.AppUser u LEFT JOIN dbo.Role r ON r.RoleID=u.RoleID
               WHERE u.IsActive=1 AND (r.RoleID IS NULL OR r.IsActive<>1 OR r.RoleCode IS NULL))
    BEGIN
        ;THROW 51202,'Active AppUser rows have missing/inactive role mappings. Resolve before RLS deployment.',1;
    END;

      IF EXISTS (SELECT 1 FROM dbo.AppUser u
             WHERE u.IsActive=1 AND (u.CompanyID IS NULL OR u.DepartmentID IS NULL OR u.PositionID IS NULL))
             OR EXISTS (SELECT 1 FROM dbo.AppUser u
            LEFT JOIN dbo.Company c ON c.CompanyID=u.CompanyID
            LEFT JOIN dbo.Department d ON d.DepartmentID=u.DepartmentID
            LEFT JOIN dbo.Position p ON p.PositionID=u.PositionID
            WHERE u.IsActive=1 AND (c.CompanyID IS NULL OR d.DepartmentID IS NULL OR p.PositionID IS NULL))
             OR EXISTS (SELECT 1 FROM dbo.AppUser u JOIN dbo.Department d ON d.DepartmentID=u.DepartmentID
            WHERE u.IsActive=1 AND u.CompanyID<>d.CompanyID)
             OR EXISTS (SELECT 1 FROM dbo.AppUser u JOIN dbo.Position p ON p.PositionID=u.PositionID
            WHERE u.IsActive=1 AND u.DepartmentID<>p.DepartmentID)
      BEGIN
        ;THROW 51203,'Active AppUser organization scope is incomplete or inconsistent. Resolve approved CompanyID, DepartmentID, and PositionID mappings before RLS deployment.',1;
      END;

      IF EXISTS (SELECT 1 FROM dbo.Requirement r LEFT JOIN dbo.AppUser u ON u.UserID=r.CreatedByUserID
             WHERE r.CreatedByUserID IS NULL OR u.UserID IS NULL)
         OR EXISTS (SELECT 1 FROM dbo.Project p LEFT JOIN dbo.AppUser u ON u.UserID=p.CreatedByUserID
              WHERE p.CreatedByUserID IS NULL OR u.UserID IS NULL)
         OR EXISTS (SELECT 1 FROM dbo.Task t LEFT JOIN dbo.AppUser u ON u.UserID=t.CreatedByUserID
              WHERE t.CreatedByUserID IS NULL OR u.UserID IS NULL)
         OR EXISTS (SELECT 1 FROM dbo.Issue i LEFT JOIN dbo.AppUser u ON u.UserID=i.OwnerUserID
              WHERE i.OwnerUserID IS NULL OR u.UserID IS NULL)
      BEGIN
        ;THROW 51204,'Requirement, Project, Task, or Issue ownership is null or orphaned. Resolve ownership using an approved mapping before RLS deployment.',1;
      END;

      IF EXISTS (SELECT 1 FROM dbo.Approval a
             LEFT JOIN dbo.Requirement r ON r.RequirementID=a.RequirementID
             LEFT JOIN dbo.AppUser u ON u.UserID=a.AssignedToUserID
             WHERE r.RequirementID IS NULL OR u.UserID IS NULL)
         OR EXISTS (SELECT 1 FROM dbo.Notification n LEFT JOIN dbo.AppUser u ON u.UserID=n.UserID
              WHERE u.UserID IS NULL)
      BEGIN
        ;THROW 51205,'Approval or notification ownership references are orphaned. Resolve them before RLS deployment.',1;
      END;

      IF OBJECT_ID('dbo.TaskAssignment','U') IS NOT NULL
         OR OBJECT_ID('dbo.TaskDependency','U') IS NOT NULL
         OR OBJECT_ID('dbo.Deliverable','U') IS NOT NULL
         OR OBJECT_ID('dbo.Evaluation','U') IS NOT NULL
         OR OBJECT_ID('dbo.AgentTaskQueue','U') IS NOT NULL
         OR OBJECT_ID('dbo.AgentExecution','U') IS NOT NULL
         OR OBJECT_ID('dbo.AgentExecutionOutput','U') IS NOT NULL
      BEGIN
        ;THROW 51206,'Native RLS migration is incomplete for existing assignment/runtime tables. Add and review predicates for every table reported by sql/17_sql_server_rls_validation.sql before enabling any policy.',1;
      END;

    IF SCHEMA_ID('Security') IS NULL
        EXEC(N'CREATE SCHEMA Security AUTHORIZATION dbo;');

    IF OBJECT_ID('Security.fn_CanAccessOwner','IF') IS NULL
        EXEC(N'CREATE FUNCTION Security.fn_CanAccessOwner(@OwnerUserID uniqueidentifier)
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

    IF OBJECT_ID('Security.fn_CanAccessApproval','IF') IS NULL
        EXEC(N'CREATE FUNCTION Security.fn_CanAccessApproval(@AssignedToUserID uniqueidentifier,@RequirementID uniqueidentifier)
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
              OR @AssignedToUserID=actor.UserID
              OR EXISTS (
                  SELECT 1 FROM dbo.Requirement AS req
                  CROSS APPLY Security.fn_CanAccessOwner(req.CreatedByUserID) AS req_scope
                  WHERE req.RequirementID=@RequirementID
              )
            )
        );');

    IF OBJECT_ID('Security.fn_CanAccessNotification','IF') IS NULL
        EXEC(N'CREATE FUNCTION Security.fn_CanAccessNotification(@NotificationUserID uniqueidentifier)
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
              OR @NotificationUserID=actor.UserID
            )
        );');

    IF NOT EXISTS (SELECT 1 FROM sys.security_policies WHERE schema_id=SCHEMA_ID('Security') AND name='WorkforceOwnershipPolicy')
    BEGIN
        EXEC(N'CREATE SECURITY POLICY Security.WorkforceOwnershipPolicy
          ADD FILTER PREDICATE Security.fn_CanAccessOwner(CreatedByUserID) ON dbo.Requirement,
          ADD BLOCK PREDICATE Security.fn_CanAccessOwner(CreatedByUserID) ON dbo.Requirement AFTER INSERT,
          ADD BLOCK PREDICATE Security.fn_CanAccessOwner(CreatedByUserID) ON dbo.Requirement BEFORE UPDATE,
          ADD FILTER PREDICATE Security.fn_CanAccessOwner(CreatedByUserID) ON dbo.Project,
          ADD BLOCK PREDICATE Security.fn_CanAccessOwner(CreatedByUserID) ON dbo.Project AFTER INSERT,
          ADD BLOCK PREDICATE Security.fn_CanAccessOwner(CreatedByUserID) ON dbo.Project BEFORE UPDATE,
          ADD FILTER PREDICATE Security.fn_CanAccessOwner(CreatedByUserID) ON dbo.Task,
          ADD BLOCK PREDICATE Security.fn_CanAccessOwner(CreatedByUserID) ON dbo.Task AFTER INSERT,
          ADD BLOCK PREDICATE Security.fn_CanAccessOwner(CreatedByUserID) ON dbo.Task BEFORE UPDATE,
          ADD FILTER PREDICATE Security.fn_CanAccessOwner(OwnerUserID) ON dbo.Issue,
          ADD BLOCK PREDICATE Security.fn_CanAccessOwner(OwnerUserID) ON dbo.Issue AFTER INSERT,
          ADD BLOCK PREDICATE Security.fn_CanAccessOwner(OwnerUserID) ON dbo.Issue BEFORE UPDATE,
          ADD FILTER PREDICATE Security.fn_CanAccessApproval(AssignedToUserID,RequirementID) ON dbo.Approval,
          ADD BLOCK PREDICATE Security.fn_CanAccessApproval(AssignedToUserID,RequirementID) ON dbo.Approval AFTER INSERT,
          ADD BLOCK PREDICATE Security.fn_CanAccessApproval(AssignedToUserID,RequirementID) ON dbo.Approval BEFORE UPDATE,
          ADD FILTER PREDICATE Security.fn_CanAccessNotification(UserID) ON dbo.Notification,
          ADD BLOCK PREDICATE Security.fn_CanAccessNotification(UserID) ON dbo.Notification BEFORE UPDATE
          WITH (STATE=ON,SCHEMABINDING=ON);');
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
