/*
    Explicit AppUser organization mapping for existing Company/Department/Position.
    No organization tables are created. No mapping is inferred from display names,
    email addresses, role codes, or free-text Department fields.

    Populate @ApprovedMappings from an approved HR/company source. The UPDATE is
    blocked unless every active user has exactly one valid mapping and the session
    context gate is explicitly enabled on a reviewed DEV connection.
*/
USE AICompany;
GO

/* Read-only catalog and user diagnostics. */
SELECT u.UserID,u.Email,u.DisplayName,u.Department AS LegacyDepartment,
       u.CompanyID,u.DepartmentID,u.PositionID
FROM dbo.AppUser u
WHERE u.IsActive=1
ORDER BY u.Email;

SELECT c.CompanyID,c.CompanyName,d.DepartmentID,d.DepartmentName,
       p.PositionID,p.PositionName,p.Grade
FROM dbo.Company c
JOIN dbo.Department d ON d.CompanyID=c.CompanyID
JOIN dbo.Position p ON p.DepartmentID=d.DepartmentID
ORDER BY c.CompanyName,d.DepartmentName,p.PositionName;
GO

/*
    Deployment operator: add one explicit row for every active user, using
    approved HR/company mappings. This variable intentionally starts empty.
*/
DECLARE @ApprovedMappings TABLE(
    UserID uniqueidentifier NOT NULL PRIMARY KEY,
    CompanyID uniqueidentifier NOT NULL,
    DepartmentID uniqueidentifier NOT NULL,
    PositionID uniqueidentifier NOT NULL
);

/* Example shape only; replace with approved values before executing:
INSERT @ApprovedMappings(UserID,CompanyID,DepartmentID,PositionID)
VALUES ('<user-guid>','<company-guid>','<department-guid>','<position-guid>');
*/

IF EXISTS (
    SELECT 1 FROM dbo.AppUser u
    LEFT JOIN @ApprovedMappings m ON m.UserID=u.UserID
    WHERE u.IsActive=1 AND m.UserID IS NULL
)
    ;THROW 51400,'Every active AppUser requires an approved CompanyID, DepartmentID, and PositionID mapping.',1;

IF EXISTS (
    SELECT 1 FROM @ApprovedMappings m
    JOIN dbo.AppUser u ON u.UserID=m.UserID
    LEFT JOIN dbo.Department d ON d.DepartmentID=m.DepartmentID AND d.CompanyID=m.CompanyID
    LEFT JOIN dbo.Position p ON p.PositionID=m.PositionID AND p.DepartmentID=m.DepartmentID
    WHERE u.IsActive<>1 OR d.DepartmentID IS NULL OR p.PositionID IS NULL
)
    ;THROW 51401,'Mapping contains an inactive user or invalid Company/Department/Position relationship.',1;

IF ISNULL(TRY_CONVERT(bit,SESSION_CONTEXT(N'ApplyApprovedAppUserOrgMapping')),0)<>1
    ;THROW 51402,'Mapping update blocked. Set ApplyApprovedAppUserOrgMapping=1 on an approved DEV session after reviewing every row.',1;

SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    UPDATE u
       SET CompanyID=m.CompanyID,
           DepartmentID=m.DepartmentID,
           PositionID=m.PositionID
    FROM dbo.AppUser u
    JOIN @ApprovedMappings m ON m.UserID=u.UserID
    WHERE u.IsActive=1;

    IF EXISTS (
        SELECT 1 FROM dbo.AppUser u
        LEFT JOIN dbo.Department d ON d.DepartmentID=u.DepartmentID AND d.CompanyID=u.CompanyID
        LEFT JOIN dbo.Position p ON p.PositionID=u.PositionID AND p.DepartmentID=u.DepartmentID
        WHERE u.IsActive=1 AND (d.DepartmentID IS NULL OR p.PositionID IS NULL)
    )
        ;THROW 51403,'Post-update organization integrity check failed.',1;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

EXEC sys.sp_set_session_context @key=N'ApplyApprovedAppUserOrgMapping',@value=NULL;
GO
