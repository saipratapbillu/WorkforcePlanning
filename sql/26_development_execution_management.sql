USE AICompany;
GO

IF OBJECT_ID('dbo.ProjectEpic', 'U') IS NULL OR OBJECT_ID('dbo.ProjectFeature', 'U') IS NULL
   OR OBJECT_ID('dbo.ProjectStory', 'U') IS NULL OR OBJECT_ID('dbo.ProjectSprint', 'U') IS NULL
   OR OBJECT_ID('dbo.AppUser', 'U') IS NULL
    THROW 52600, 'Apply migration 25 before migration 26.', 1;
GO

SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF COL_LENGTH('dbo.ProjectEpic', 'OwnerUserID') IS NULL
        ALTER TABLE dbo.ProjectEpic ADD OwnerUserID uniqueidentifier NULL REFERENCES dbo.AppUser(UserID);
    IF COL_LENGTH('dbo.ProjectEpic', 'Priority') IS NULL
        ALTER TABLE dbo.ProjectEpic ADD Priority tinyint NOT NULL CONSTRAINT DF_ProjectEpic_Priority DEFAULT 3;
    IF COL_LENGTH('dbo.ProjectEpic', 'UpdatedAtUtc') IS NULL
        ALTER TABLE dbo.ProjectEpic ADD UpdatedAtUtc datetime2 NULL;
    IF COL_LENGTH('dbo.ProjectEpic', 'ClosedAtUtc') IS NULL
        ALTER TABLE dbo.ProjectEpic ADD ClosedAtUtc datetime2 NULL;

    IF COL_LENGTH('dbo.ProjectFeature', 'Priority') IS NULL
        ALTER TABLE dbo.ProjectFeature ADD Priority tinyint NOT NULL CONSTRAINT DF_ProjectFeature_Priority DEFAULT 3;
    IF COL_LENGTH('dbo.ProjectFeature', 'UpdatedAtUtc') IS NULL
        ALTER TABLE dbo.ProjectFeature ADD UpdatedAtUtc datetime2 NULL;

    IF COL_LENGTH('dbo.ProjectStory', 'Priority') IS NULL
        ALTER TABLE dbo.ProjectStory ADD Priority tinyint NOT NULL CONSTRAINT DF_ProjectStory_Priority DEFAULT 3;
    IF COL_LENGTH('dbo.ProjectStory', 'BacklogRank') IS NULL
        ALTER TABLE dbo.ProjectStory ADD BacklogRank int NOT NULL CONSTRAINT DF_ProjectStory_BacklogRank DEFAULT 0;
    IF COL_LENGTH('dbo.ProjectStory', 'UpdatedAtUtc') IS NULL
        ALTER TABLE dbo.ProjectStory ADD UpdatedAtUtc datetime2 NULL;
    IF COL_LENGTH('dbo.ProjectStory', 'CompletedAtUtc') IS NULL
        ALTER TABLE dbo.ProjectStory ADD CompletedAtUtc datetime2 NULL;

    IF COL_LENGTH('dbo.ProjectSprint', 'StartedAtUtc') IS NULL
        ALTER TABLE dbo.ProjectSprint ADD StartedAtUtc datetime2 NULL;
    IF COL_LENGTH('dbo.ProjectSprint', 'CompletedAtUtc') IS NULL
        ALTER TABLE dbo.ProjectSprint ADD CompletedAtUtc datetime2 NULL;

    IF OBJECT_ID('dbo.ProjectStoryDependency', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.ProjectStoryDependency(
            StoryID uniqueidentifier NOT NULL REFERENCES dbo.ProjectStory(StoryID),
            DependsOnStoryID uniqueidentifier NOT NULL REFERENCES dbo.ProjectStory(StoryID),
            CreatedAtUtc datetime2 NOT NULL CONSTRAINT DF_ProjectStoryDependency_CreatedAtUtc DEFAULT SYSUTCDATETIME(),
            CreatedBy nvarchar(200) NOT NULL,
            CONSTRAINT PK_ProjectStoryDependency PRIMARY KEY(StoryID, DependsOnStoryID),
            CONSTRAINT CK_ProjectStoryDependency_NotSelf CHECK(StoryID <> DependsOnStoryID)
        );
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

-- Priority constraints and backlog index are added after the columns exist (batch boundary).
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_ProjectStory_Priority')
    ALTER TABLE dbo.ProjectStory ADD CONSTRAINT CK_ProjectStory_Priority CHECK(Priority BETWEEN 1 AND 5);
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_ProjectEpic_Priority')
    ALTER TABLE dbo.ProjectEpic ADD CONSTRAINT CK_ProjectEpic_Priority CHECK(Priority BETWEEN 1 AND 5);
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_ProjectFeature_Priority')
    ALTER TABLE dbo.ProjectFeature ADD CONSTRAINT CK_ProjectFeature_Priority CHECK(Priority BETWEEN 1 AND 5);
GO
