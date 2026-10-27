USE AICompany;
GO

IF OBJECT_ID('dbo.Notification', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Notification
    (
        NotificationID uniqueidentifier NOT NULL CONSTRAINT PK_Notification PRIMARY KEY DEFAULT NEWID(),
        UserID uniqueidentifier NOT NULL,
        NotificationType varchar(50) NOT NULL,
        Title nvarchar(200) NOT NULL,
        Body nvarchar(1000) NOT NULL,
        ResourceType varchar(50) NOT NULL,
        ResourceID nvarchar(100) NOT NULL,
        CorrelationID uniqueidentifier NOT NULL,
        IsRead bit NOT NULL CONSTRAINT DF_Notification_IsRead DEFAULT 0,
        CreatedAtUtc datetime2 NOT NULL CONSTRAINT DF_Notification_CreatedAtUtc DEFAULT SYSUTCDATETIME(),
        ReadAtUtc datetime2 NULL,
        CONSTRAINT FK_Notification_AppUser FOREIGN KEY (UserID) REFERENCES dbo.AppUser(UserID)
    );
END;
GO

IF COL_LENGTH('dbo.Approval', 'DecisionAtUtc') IS NULL
BEGIN
    ALTER TABLE dbo.Approval ADD DecisionAtUtc datetime2 NULL;
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Notification_User_Read_Created')
    CREATE INDEX IX_Notification_User_Read_Created
        ON dbo.Notification(UserID, IsRead, CreatedAtUtc DESC);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Approval_Requirement_Status')
    CREATE INDEX IX_Approval_Requirement_Status
        ON dbo.Approval(RequirementID, Status, CreatedAtUtc);
GO
