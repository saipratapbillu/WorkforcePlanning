USE AICompany;
GO

IF OBJECT_ID('dbo.Role', 'U') IS NULL
    THROW 51000, 'dbo.Role is missing. Apply the user and role base schema before this migration.', 1;

IF OBJECT_ID('dbo.AppUser', 'U') IS NULL
    THROW 51001, 'dbo.AppUser is missing. Apply the user base schema before this migration.', 1;
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

DECLARE @UserRoleID uniqueidentifier;

SELECT TOP (1) @UserRoleID = RoleID
FROM dbo.Role WITH (UPDLOCK, HOLDLOCK)
WHERE RoleCode = 'USER'
ORDER BY IsActive DESC, RoleLevel ASC, RoleID ASC;

IF @UserRoleID IS NULL
BEGIN
    SET @UserRoleID = NEWID();
    INSERT INTO dbo.Role (RoleID, RoleCode, RoleName, RoleLevel, IsActive)
    VALUES (@UserRoleID, 'USER', 'Business User', 10, 1);
END
ELSE
BEGIN
    UPDATE dbo.Role
    SET IsActive = 1
    WHERE RoleID = @UserRoleID AND IsActive = 0;
END;

-- Repair only accounts whose role is missing or inactive. Existing active roles,
-- including privileged roles, are left unchanged.
UPDATE appUser
SET RoleID = @UserRoleID
FROM dbo.AppUser AS appUser
WHERE NOT EXISTS
(
    SELECT 1
    FROM dbo.Role AS assignedRole
    WHERE assignedRole.RoleID = appUser.RoleID
      AND assignedRole.IsActive = 1
);

COMMIT TRANSACTION;
GO

SELECT RoleCode, RoleName, IsActive
FROM dbo.Role
WHERE RoleCode = 'USER' AND IsActive = 1;

SELECT COUNT(*) AS AccountsWithMissingOrInactiveRole
FROM dbo.AppUser AS appUser
WHERE NOT EXISTS
(
    SELECT 1
    FROM dbo.Role AS assignedRole
    WHERE assignedRole.RoleID = appUser.RoleID
      AND assignedRole.IsActive = 1
);
GO
