USE AICompany;
GO

IF COL_LENGTH('dbo.AppUser', 'ManagerUserID') IS NULL
BEGIN
    ALTER TABLE dbo.AppUser
    ADD ManagerUserID uniqueidentifier NULL;
END;
GO

IF NOT EXISTS
(
    SELECT 1 FROM sys.foreign_keys
    WHERE name = 'FK_AppUser_ManagerUser'
      AND parent_object_id = OBJECT_ID('dbo.AppUser')
)
BEGIN
    ALTER TABLE dbo.AppUser
    ADD CONSTRAINT FK_AppUser_ManagerUser
        FOREIGN KEY (ManagerUserID) REFERENCES dbo.AppUser(UserID);
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.Role WHERE RoleCode = 'MANAGER')
BEGIN
    INSERT INTO dbo.Role (RoleID, RoleCode, RoleName, RoleLevel, IsActive)
    VALUES (NEWID(), 'MANAGER', 'People Manager', 20, 1);
END;
ELSE
BEGIN
    UPDATE dbo.Role SET IsActive = 1 WHERE RoleCode = 'MANAGER';
END;
GO

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_AppUser_ManagerUserID'
      AND object_id = OBJECT_ID('dbo.AppUser')
)
BEGIN
    CREATE INDEX IX_AppUser_ManagerUserID ON dbo.AppUser(ManagerUserID, IsActive);
END;
GO
