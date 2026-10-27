/*
    Native RLS rollback only. Does not drop ownership columns, existing tables,
    or the Security schema. Do not run until API code has been returned to a
    compatible release and affected traffic is in maintenance/deny mode.
*/
USE AICompany;
GO
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF ISNULL(TRY_CONVERT(bit,SESSION_CONTEXT(N'RollbackNativeRls')),0)<>1
    BEGIN
        ;THROW 51300,'RLS rollback blocked. Set RollbackNativeRls=1 on an approved maintenance connection.',1;
    END;

    IF EXISTS (SELECT 1 FROM sys.security_policies WHERE schema_id=SCHEMA_ID('Security') AND name='WorkforceOwnershipPolicy')
        DROP SECURITY POLICY Security.WorkforceOwnershipPolicy;

    IF OBJECT_ID('Security.fn_CanAccessApproval','IF') IS NOT NULL
        DROP FUNCTION Security.fn_CanAccessApproval;
    IF OBJECT_ID('Security.fn_CanAccessNotification','IF') IS NOT NULL
        DROP FUNCTION Security.fn_CanAccessNotification;
    IF OBJECT_ID('Security.fn_CanAccessOwner','IF') IS NOT NULL
        DROP FUNCTION Security.fn_CanAccessOwner;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
EXEC sys.sp_set_session_context @key=N'RollbackNativeRls',@value=NULL;
GO
