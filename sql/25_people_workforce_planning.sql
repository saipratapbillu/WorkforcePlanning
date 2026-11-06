USE AICompany;
GO

IF OBJECT_ID('dbo.AppUser', 'U') IS NULL OR OBJECT_ID('dbo.Role', 'U') IS NULL
   OR OBJECT_ID('dbo.Skill', 'U') IS NULL OR OBJECT_ID('dbo.Project', 'U') IS NULL
   OR OBJECT_ID('dbo.Task', 'U') IS NULL OR OBJECT_ID('dbo.Company', 'U') IS NULL
   OR OBJECT_ID('dbo.Department', 'U') IS NULL OR OBJECT_ID('dbo.Position', 'U') IS NULL
   OR OBJECT_ID('dbo.AuditLog', 'U') IS NULL
    THROW 52500, 'Apply the existing identity, organization, audit, skill, project, and task schemas before migration 25.', 1;
GO

SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID('dbo.AppUserSkill', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AppUserSkill(
            UserID uniqueidentifier NOT NULL REFERENCES dbo.AppUser(UserID),
            SkillID uniqueidentifier NOT NULL REFERENCES dbo.Skill(SkillID),
            Proficiency tinyint NOT NULL,
            Status varchar(20) NOT NULL,
            Evidence nvarchar(2000) NOT NULL,
            CreatedAtUtc datetime2 NOT NULL CONSTRAINT DF_AppUserSkill_CreatedAtUtc DEFAULT SYSUTCDATETIME(),
            CreatedBy nvarchar(200) NOT NULL,
            ApprovedAtUtc datetime2 NULL,
            ApprovedBy nvarchar(200) NULL,
            CONSTRAINT PK_AppUserSkill PRIMARY KEY(UserID, SkillID),
            CONSTRAINT CK_AppUserSkill_Proficiency CHECK(Proficiency BETWEEN 1 AND 5),
            CONSTRAINT CK_AppUserSkill_Status CHECK(Status IN ('Pending', 'Active', 'Revoked'))
        );
    END;

    IF OBJECT_ID('dbo.AppUserCertification', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AppUserCertification(
            UserCertificationID uniqueidentifier NOT NULL PRIMARY KEY,
            UserID uniqueidentifier NOT NULL REFERENCES dbo.AppUser(UserID),
            CertificationName nvarchar(200) NOT NULL,
            Issuer nvarchar(200) NULL,
            IssuedAtUtc datetime2 NULL,
            ExpiresAtUtc datetime2 NULL,
            Status varchar(20) NOT NULL,
            Evidence nvarchar(2000) NOT NULL,
            CreatedAtUtc datetime2 NOT NULL CONSTRAINT DF_AppUserCertification_CreatedAtUtc DEFAULT SYSUTCDATETIME(),
            CreatedBy nvarchar(200) NOT NULL,
            ReviewedAtUtc datetime2 NULL,
            ReviewedBy nvarchar(200) NULL,
            CONSTRAINT CK_AppUserCertification_Status CHECK(Status IN ('Pending', 'Active', 'Rejected', 'Expired'))
        );
    END;

    IF OBJECT_ID('dbo.AppUserAvailability', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AppUserAvailability(
            UserID uniqueidentifier NOT NULL REFERENCES dbo.AppUser(UserID),
            WeekStartDate date NOT NULL,
            AvailableHours decimal(7,2) NOT NULL,
            IsAvailable bit NOT NULL,
            Note nvarchar(500) NULL,
            UpdatedAtUtc datetime2 NOT NULL CONSTRAINT DF_AppUserAvailability_UpdatedAtUtc DEFAULT SYSUTCDATETIME(),
            UpdatedBy nvarchar(200) NOT NULL,
            CONSTRAINT PK_AppUserAvailability PRIMARY KEY(UserID, WeekStartDate),
            CONSTRAINT CK_AppUserAvailability_Hours CHECK(AvailableHours BETWEEN 0 AND 168)
        );
    END;

    IF OBJECT_ID('dbo.ProjectEpic', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.ProjectEpic(
            EpicID uniqueidentifier NOT NULL PRIMARY KEY,
            ProjectID uniqueidentifier NOT NULL REFERENCES dbo.Project(ProjectID),
            Title nvarchar(200) NOT NULL,
            Description nvarchar(2000) NOT NULL,
            SequenceNumber int NOT NULL,
            Status varchar(20) NOT NULL,
            CreatedAtUtc datetime2 NOT NULL CONSTRAINT DF_ProjectEpic_CreatedAtUtc DEFAULT SYSUTCDATETIME(),
            CreatedBy nvarchar(200) NOT NULL,
            CONSTRAINT CK_ProjectEpic_Status CHECK(Status IN ('Proposed', 'Planned', 'InProgress', 'Completed', 'Cancelled'))
        );
    END;

    IF OBJECT_ID('dbo.ProjectFeature', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.ProjectFeature(
            FeatureID uniqueidentifier NOT NULL PRIMARY KEY,
            EpicID uniqueidentifier NOT NULL REFERENCES dbo.ProjectEpic(EpicID),
            Title nvarchar(200) NOT NULL,
            Description nvarchar(2000) NOT NULL,
            SequenceNumber int NOT NULL,
            Status varchar(20) NOT NULL,
            CreatedAtUtc datetime2 NOT NULL CONSTRAINT DF_ProjectFeature_CreatedAtUtc DEFAULT SYSUTCDATETIME(),
            CreatedBy nvarchar(200) NOT NULL,
            CONSTRAINT CK_ProjectFeature_Status CHECK(Status IN ('Proposed', 'Planned', 'InProgress', 'Completed', 'Cancelled'))
        );
    END;

    IF OBJECT_ID('dbo.ProjectSprint', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.ProjectSprint(
            SprintID uniqueidentifier NOT NULL PRIMARY KEY,
            ProjectID uniqueidentifier NOT NULL REFERENCES dbo.Project(ProjectID),
            SprintName nvarchar(100) NOT NULL,
            StartDate date NOT NULL,
            EndDate date NOT NULL,
            CapacityHours decimal(9,2) NOT NULL,
            Status varchar(20) NOT NULL,
            CreatedAtUtc datetime2 NOT NULL CONSTRAINT DF_ProjectSprint_CreatedAtUtc DEFAULT SYSUTCDATETIME(),
            CreatedBy nvarchar(200) NOT NULL,
            CONSTRAINT CK_ProjectSprint_Dates CHECK(EndDate >= StartDate),
            CONSTRAINT CK_ProjectSprint_Capacity CHECK(CapacityHours >= 0),
            CONSTRAINT CK_ProjectSprint_Status CHECK(Status IN ('Planned', 'Active', 'Completed', 'Cancelled'))
        );
    END;

    IF OBJECT_ID('dbo.ProjectStory', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.ProjectStory(
            StoryID uniqueidentifier NOT NULL PRIMARY KEY,
            FeatureID uniqueidentifier NOT NULL REFERENCES dbo.ProjectFeature(FeatureID),
            SprintID uniqueidentifier NULL REFERENCES dbo.ProjectSprint(SprintID),
            Title nvarchar(200) NOT NULL,
            Description nvarchar(2000) NOT NULL,
            AcceptanceCriteriaJson nvarchar(max) NOT NULL,
            RequiredSkillsJson nvarchar(max) NOT NULL,
            RequiredCertificationsJson nvarchar(max) NOT NULL,
            StoryPoints int NOT NULL,
            Status varchar(20) NOT NULL,
            CreatedAtUtc datetime2 NOT NULL CONSTRAINT DF_ProjectStory_CreatedAtUtc DEFAULT SYSUTCDATETIME(),
            CreatedBy nvarchar(200) NOT NULL,
            CONSTRAINT CK_ProjectStory_Points CHECK(StoryPoints BETWEEN 1 AND 100),
            CONSTRAINT CK_ProjectStory_Status CHECK(Status IN ('Backlog', 'Planned', 'InProgress', 'Completed', 'Blocked', 'Cancelled'))
        );
    END;

    IF OBJECT_ID('dbo.ProjectDeliveryTask', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.ProjectDeliveryTask(
            ProjectTaskID uniqueidentifier NOT NULL PRIMARY KEY,
            StoryID uniqueidentifier NOT NULL REFERENCES dbo.ProjectStory(StoryID),
            Title nvarchar(200) NOT NULL,
            Description nvarchar(2000) NOT NULL,
            RequiredSkillsJson nvarchar(max) NOT NULL,
            RequiredCertificationsJson nvarchar(max) NOT NULL,
            EstimatedEffortHours decimal(9,2) NOT NULL,
            Status varchar(20) NOT NULL,
            CreatedAtUtc datetime2 NOT NULL CONSTRAINT DF_ProjectTask_CreatedAtUtc DEFAULT SYSUTCDATETIME(),
            CreatedBy nvarchar(200) NOT NULL,
            CONSTRAINT CK_ProjectTask_Estimate CHECK(EstimatedEffortHours > 0),
            CONSTRAINT CK_ProjectTask_Status CHECK(Status IN ('Planned', 'InProgress', 'Completed', 'Blocked', 'Cancelled'))
        );
    END;

    IF OBJECT_ID('dbo.ResourceAssignmentRecommendation', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.ResourceAssignmentRecommendation(
            RecommendationID uniqueidentifier NOT NULL PRIMARY KEY,
            ProjectTaskID uniqueidentifier NOT NULL REFERENCES dbo.ProjectDeliveryTask(ProjectTaskID),
            UserID uniqueidentifier NOT NULL REFERENCES dbo.AppUser(UserID),
            MatchScore decimal(5,2) NOT NULL,
            EvidenceJson nvarchar(max) NOT NULL,
            Status varchar(20) NOT NULL,
            RecommendedAtUtc datetime2 NOT NULL CONSTRAINT DF_ResourceAssignmentRecommendation_RecommendedAtUtc DEFAULT SYSUTCDATETIME(),
            RecommendedBy nvarchar(200) NOT NULL,
            DecisionAtUtc datetime2 NULL,
            DecisionByUserID uniqueidentifier NULL REFERENCES dbo.AppUser(UserID),
            DecisionReason nvarchar(2000) NULL,
            CONSTRAINT CK_ResourceAssignmentRecommendation_Score CHECK(MatchScore BETWEEN 0 AND 100),
            CONSTRAINT CK_ResourceAssignmentRecommendation_Status CHECK(Status IN ('PendingApproval', 'Approved', 'Rejected', 'Assigned'))
        );
    END;

    IF OBJECT_ID('dbo.ProjectTaskAssignment', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.ProjectTaskAssignment(
            AssignmentID uniqueidentifier NOT NULL PRIMARY KEY,
            ProjectTaskID uniqueidentifier NOT NULL REFERENCES dbo.ProjectDeliveryTask(ProjectTaskID),
            UserID uniqueidentifier NOT NULL REFERENCES dbo.AppUser(UserID),
            RecommendationID uniqueidentifier NOT NULL REFERENCES dbo.ResourceAssignmentRecommendation(RecommendationID),
            AssignedAtUtc datetime2 NOT NULL CONSTRAINT DF_ProjectTaskAssignment_AssignedAtUtc DEFAULT SYSUTCDATETIME(),
            AssignedByUserID uniqueidentifier NOT NULL REFERENCES dbo.AppUser(UserID),
            ReleasedAtUtc datetime2 NULL,
            Status varchar(20) NOT NULL,
            CONSTRAINT CK_ProjectTaskAssignment_Status CHECK(Status IN ('Active', 'Released'))
        );
    END;

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.AppUserSkill') AND name='IX_AppUserSkill_Status')
        CREATE INDEX IX_AppUserSkill_Status ON dbo.AppUserSkill(Status, SkillID, UserID);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.AppUserAvailability') AND name='IX_AppUserAvailability_Week')
        CREATE INDEX IX_AppUserAvailability_Week ON dbo.AppUserAvailability(WeekStartDate, IsAvailable) INCLUDE(UserID, AvailableHours);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.ProjectStory') AND name='IX_ProjectStory_Sprint')
        CREATE INDEX IX_ProjectStory_Sprint ON dbo.ProjectStory(SprintID, Status);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.ResourceAssignmentRecommendation') AND name='IX_ResourceAssignmentRecommendation_Review')
        CREATE INDEX IX_ResourceAssignmentRecommendation_Review ON dbo.ResourceAssignmentRecommendation(Status, RecommendedAtUtc DESC);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.ProjectTaskAssignment') AND name='UX_ProjectTaskAssignment_Active')
        CREATE UNIQUE INDEX UX_ProjectTaskAssignment_Active ON dbo.ProjectTaskAssignment(ProjectTaskID) WHERE Status='Active';

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
