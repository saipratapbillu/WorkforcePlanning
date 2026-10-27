/*
    Approved ownership normalization only.

    Approved DDL gaps:
      dbo.Requirement.CreatedByUserID
      dbo.Project.CreatedByUserID
      dbo.Task.CreatedByUserID
      dbo.Issue.OwnerUserID

    Existing Company, Department, Position, Agent, AppUser, Role, Approval,
    and Notification tables are not recreated or altered by this script.
    Risk, WorkforceRequest, KnowledgeSource, and Skill are validation-only
    in this package because no ownership-column alteration was approved for
    those tables here.

    This file is intentionally inert by default. Execute a section only on a
    dedicated, reviewed DEV connection by setting its session-context gate.
    No DDL or backfill was executed while generating this file.

    Migration order:
      1. Run preflight/validation queries.
      2. Expand nullable GUID columns.
      3. Review exact-GUID backfill candidates, then backfill.
      4. Validate mappings and add indexes/FKs.
      5. Deploy API dual-write/read changes and test.
      6. Design and deploy table-specific RLS only after separate review.

    Do not drop legacy text columns in this migration.
*/

USE AICompany;
GO

/* -------------------------------------------------------------------------
   0. PREFLIGHT / BASELINE (read-only; safe to run)
   ------------------------------------------------------------------------- */
SELECT t.name AS TableName,c.name AS ColumnName,ty.name AS DataType,
       c.is_nullable,c.max_length
FROM sys.tables t
JOIN sys.columns c ON c.object_id=t.object_id
JOIN sys.types ty ON ty.user_type_id=c.user_type_id
WHERE (t.name='Requirement' AND c.name IN ('RequirementID','CreatedBy','CreatedByUserID'))
   OR (t.name='Project' AND c.name IN ('ProjectID','RequirementID','CreatedBy','CreatedByUserID'))
   OR (t.name='Task' AND c.name IN ('TaskID','ProjectID','CreatedBy','CreatedByUserID'))
   OR (t.name='Issue' AND c.name IN ('IssueID','ProjectID','Owner','OwnerUserID'))
   OR (t.name='Risk' AND c.name IN ('RiskID','ProjectID','Owner'))
   OR (t.name='WorkforceRequest' AND c.name IN ('WorkforceRequestID','ProjectID','TaskID','RequestedBy'))
   OR (t.name='KnowledgeSource' AND c.name IN ('KnowledgeSourceID','Owner'))
   OR (t.name='Skill' AND c.name IN ('SkillID','Owner'))
ORDER BY t.name,c.column_id;
GO

SELECT 'Requirement' AS TableName,COUNT(*) AS [Rows] FROM dbo.Requirement
UNION ALL SELECT 'Project',COUNT(*) FROM dbo.Project
UNION ALL SELECT 'Task',COUNT(*) FROM dbo.Task
UNION ALL SELECT 'Issue',COUNT(*) FROM dbo.Issue
UNION ALL SELECT 'Risk',COUNT(*) FROM dbo.Risk
UNION ALL SELECT 'WorkforceRequest',COUNT(*) FROM dbo.WorkforceRequest
UNION ALL SELECT 'KnowledgeSource',COUNT(*) FROM dbo.KnowledgeSource
UNION ALL SELECT 'Skill',COUNT(*) FROM dbo.Skill;
GO

/* Exact GUID match candidates only. These SELECTs do not update rows. */
SELECT 'Requirement.CreatedBy' AS OwnershipField,COUNT(*) AS TotalRows,
       SUM(CASE WHEN u.UserID IS NOT NULL THEN 1 ELSE 0 END) AS ExactUserGuidMatches,
       SUM(CASE WHEN x.CreatedBy IS NOT NULL AND u.UserID IS NULL THEN 1 ELSE 0 END) AS UnmatchedRows
FROM dbo.Requirement x
LEFT JOIN dbo.AppUser u ON u.UserID=TRY_CONVERT(uniqueidentifier,x.CreatedBy)
UNION ALL
SELECT 'Project.CreatedBy',COUNT(*),
       SUM(CASE WHEN u.UserID IS NOT NULL THEN 1 ELSE 0 END),
       SUM(CASE WHEN x.CreatedBy IS NOT NULL AND u.UserID IS NULL THEN 1 ELSE 0 END)
FROM dbo.Project x
LEFT JOIN dbo.AppUser u ON u.UserID=TRY_CONVERT(uniqueidentifier,x.CreatedBy)
UNION ALL
SELECT 'Task.CreatedBy',COUNT(*),
       SUM(CASE WHEN u.UserID IS NOT NULL THEN 1 ELSE 0 END),
       SUM(CASE WHEN x.CreatedBy IS NOT NULL AND u.UserID IS NULL THEN 1 ELSE 0 END)
FROM dbo.Task x
LEFT JOIN dbo.AppUser u ON u.UserID=TRY_CONVERT(uniqueidentifier,x.CreatedBy)
UNION ALL
SELECT 'Issue.Owner',COUNT(*),
       SUM(CASE WHEN u.UserID IS NOT NULL THEN 1 ELSE 0 END),
       SUM(CASE WHEN x.Owner IS NOT NULL AND u.UserID IS NULL THEN 1 ELSE 0 END)
FROM dbo.Issue x
LEFT JOIN dbo.AppUser u ON u.UserID=TRY_CONVERT(uniqueidentifier,x.Owner);
GO

/* Confirm existing parent FKs and existing RLS policies; this script adds none. */
SELECT pt.name AS ChildTable,pc.name AS ChildColumn,
       rt.name AS ParentTable,rc.name AS ParentColumn,fk.name AS ForeignKeyName,
       fk.is_disabled,fk.is_not_trusted
FROM sys.foreign_key_columns fkc
JOIN sys.foreign_keys fk ON fk.object_id=fkc.constraint_object_id
JOIN sys.tables pt ON pt.object_id=fkc.parent_object_id
JOIN sys.columns pc ON pc.object_id=pt.object_id AND pc.column_id=fkc.parent_column_id
JOIN sys.tables rt ON rt.object_id=fkc.referenced_object_id
JOIN sys.columns rc ON rc.object_id=rt.object_id AND rc.column_id=fkc.referenced_column_id
WHERE (pt.name='Project' AND pc.name='RequirementID')
   OR (pt.name='Task' AND pc.name='ProjectID')
   OR (pt.name='Issue' AND pc.name='ProjectID');
SELECT COUNT(*) AS ExistingSecurityPolicyCount FROM sys.security_policies;
GO

/* -------------------------------------------------------------------------
   1. EXPAND: nullable columns only; gated, idempotent, transactional.
   Run in DEV only after review. No legacy columns are dropped or renamed.
   ------------------------------------------------------------------------- */
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF ISNULL(TRY_CONVERT(bit,SESSION_CONTEXT(N'ApplyApprovedOwnershipDDL')),0)<>1
    BEGIN
        ;THROW 51000,'DDL section blocked. Set ApplyApprovedOwnershipDDL=1 on the reviewed DEV session to proceed.',1;
    END;

    IF COL_LENGTH('dbo.Requirement','CreatedByUserID') IS NULL
        EXEC(N'ALTER TABLE dbo.Requirement ADD CreatedByUserID uniqueidentifier NULL;');
    IF COL_LENGTH('dbo.Project','CreatedByUserID') IS NULL
        EXEC(N'ALTER TABLE dbo.Project ADD CreatedByUserID uniqueidentifier NULL;');
    IF COL_LENGTH('dbo.Task','CreatedByUserID') IS NULL
        EXEC(N'ALTER TABLE dbo.Task ADD CreatedByUserID uniqueidentifier NULL;');
    IF COL_LENGTH('dbo.Issue','OwnerUserID') IS NULL
        EXEC(N'ALTER TABLE dbo.Issue ADD OwnerUserID uniqueidentifier NULL;');

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

/* -------------------------------------------------------------------------
   2. BACKFILL: exact UserID GUID text matches only.
   No email/display-name/parent-owner inference. Unmatched values remain NULL.
   Run only after reviewing preflight candidate counts and backing up DEV.
   ------------------------------------------------------------------------- */
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF ISNULL(TRY_CONVERT(bit,SESSION_CONTEXT(N'ApplyApprovedOwnershipBackfill')),0)<>1
    BEGIN
        ;THROW 51001,'Backfill blocked. Set ApplyApprovedOwnershipBackfill=1 on the reviewed DEV session to proceed.',1;
    END;

    UPDATE r
       SET CreatedByUserID=u.UserID
    FROM dbo.Requirement r
    JOIN dbo.AppUser u ON u.UserID=TRY_CONVERT(uniqueidentifier,r.CreatedBy)
    WHERE r.CreatedByUserID IS NULL;

    UPDATE p
       SET CreatedByUserID=u.UserID
    FROM dbo.Project p
    JOIN dbo.AppUser u ON u.UserID=TRY_CONVERT(uniqueidentifier,p.CreatedBy)
    WHERE p.CreatedByUserID IS NULL;

    UPDATE t
       SET CreatedByUserID=u.UserID
    FROM dbo.Task t
    JOIN dbo.AppUser u ON u.UserID=TRY_CONVERT(uniqueidentifier,t.CreatedBy)
    WHERE t.CreatedByUserID IS NULL;

    UPDATE i
       SET OwnerUserID=u.UserID
    FROM dbo.Issue i
    JOIN dbo.AppUser u ON u.UserID=TRY_CONVERT(uniqueidentifier,i.Owner)
    WHERE i.OwnerUserID IS NULL;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

/* -------------------------------------------------------------------------
   3. INDEXES AND FOREIGN KEYS: after successful backfill review.
   Nullable FKs allow unresolved legacy rows to remain quarantined; do not
   enforce NOT NULL until all rows are mapped or explicitly retired.
   ------------------------------------------------------------------------- */
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF ISNULL(TRY_CONVERT(bit,SESSION_CONTEXT(N'ApplyApprovedOwnershipConstraints')),0)<>1
    BEGIN
        ;THROW 51002,'Constraint section blocked. Set ApplyApprovedOwnershipConstraints=1 on the reviewed DEV session to proceed.',1;
    END;

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.Requirement') AND name='IX_Requirement_CreatedByUserID')
        EXEC(N'CREATE INDEX IX_Requirement_CreatedByUserID ON dbo.Requirement(CreatedByUserID,CreatedAtUtc);');
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.Project') AND name='IX_Project_CreatedByUserID')
        EXEC(N'CREATE INDEX IX_Project_CreatedByUserID ON dbo.Project(CreatedByUserID,CreatedAtUtc);');
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.Task') AND name='IX_Task_CreatedByUserID')
        EXEC(N'CREATE INDEX IX_Task_CreatedByUserID ON dbo.Task(CreatedByUserID,ProjectID);');
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.Issue') AND name='IX_Issue_OwnerUserID')
        EXEC(N'CREATE INDEX IX_Issue_OwnerUserID ON dbo.Issue(OwnerUserID,ProjectID);');

    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID('dbo.Requirement') AND name='FK_Requirement_CreatedByUser')
        EXEC(N'ALTER TABLE dbo.Requirement WITH CHECK ADD CONSTRAINT FK_Requirement_CreatedByUser FOREIGN KEY(CreatedByUserID) REFERENCES dbo.AppUser(UserID);');
    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID('dbo.Project') AND name='FK_Project_CreatedByUser')
        EXEC(N'ALTER TABLE dbo.Project WITH CHECK ADD CONSTRAINT FK_Project_CreatedByUser FOREIGN KEY(CreatedByUserID) REFERENCES dbo.AppUser(UserID);');
    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID('dbo.Task') AND name='FK_Task_CreatedByUser')
        EXEC(N'ALTER TABLE dbo.Task WITH CHECK ADD CONSTRAINT FK_Task_CreatedByUser FOREIGN KEY(CreatedByUserID) REFERENCES dbo.AppUser(UserID);');
    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID('dbo.Issue') AND name='FK_Issue_OwnerUser')
        EXEC(N'ALTER TABLE dbo.Issue WITH CHECK ADD CONSTRAINT FK_Issue_OwnerUser FOREIGN KEY(OwnerUserID) REFERENCES dbo.AppUser(UserID);');

    ALTER TABLE dbo.Requirement CHECK CONSTRAINT FK_Requirement_CreatedByUser;
    ALTER TABLE dbo.Project CHECK CONSTRAINT FK_Project_CreatedByUser;
    ALTER TABLE dbo.Task CHECK CONSTRAINT FK_Task_CreatedByUser;
    ALTER TABLE dbo.Issue CHECK CONSTRAINT FK_Issue_OwnerUser;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

/* -------------------------------------------------------------------------
   4. VALIDATION: read-only. Run after expand/backfill/constraints.
   ------------------------------------------------------------------------- */
SELECT 'Requirement.CreatedByUserID null' AS CheckName,COUNT(*) AS IssueCount
FROM dbo.Requirement WHERE CreatedByUserID IS NULL
UNION ALL SELECT 'Requirement.CreatedByUserID orphan',COUNT(*)
FROM dbo.Requirement r LEFT JOIN dbo.AppUser u ON u.UserID=r.CreatedByUserID
WHERE r.CreatedByUserID IS NOT NULL AND u.UserID IS NULL
UNION ALL SELECT 'Project.CreatedByUserID null',COUNT(*) FROM dbo.Project WHERE CreatedByUserID IS NULL
UNION ALL SELECT 'Project.CreatedByUserID orphan',COUNT(*)
FROM dbo.Project p LEFT JOIN dbo.AppUser u ON u.UserID=p.CreatedByUserID
WHERE p.CreatedByUserID IS NOT NULL AND u.UserID IS NULL
UNION ALL SELECT 'Task.CreatedByUserID null',COUNT(*) FROM dbo.Task WHERE CreatedByUserID IS NULL
UNION ALL SELECT 'Task.CreatedByUserID orphan',COUNT(*)
FROM dbo.Task t LEFT JOIN dbo.AppUser u ON u.UserID=t.CreatedByUserID
WHERE t.CreatedByUserID IS NOT NULL AND u.UserID IS NULL
UNION ALL SELECT 'Issue.OwnerUserID orphan',COUNT(*)
FROM dbo.Issue i LEFT JOIN dbo.AppUser u ON u.UserID=i.OwnerUserID
WHERE i.OwnerUserID IS NOT NULL AND u.UserID IS NULL
UNION ALL SELECT 'Issue.Owner populated but GUID owner null',COUNT(*)
FROM dbo.Issue WHERE NULLIF(LTRIM(RTRIM(Owner)),'') IS NOT NULL AND OwnerUserID IS NULL;
GO

SELECT 'Requirement legacy GUID differs from normalized owner' AS CheckName,COUNT(*) AS IssueCount
FROM dbo.Requirement
WHERE CreatedByUserID IS NOT NULL
    AND TRY_CONVERT(uniqueidentifier,CreatedBy) IS NOT NULL
    AND CreatedByUserID<>TRY_CONVERT(uniqueidentifier,CreatedBy)
UNION ALL SELECT 'Project legacy GUID differs from normalized owner',COUNT(*)
FROM dbo.Project
WHERE CreatedByUserID IS NOT NULL
    AND TRY_CONVERT(uniqueidentifier,CreatedBy) IS NOT NULL
    AND CreatedByUserID<>TRY_CONVERT(uniqueidentifier,CreatedBy)
UNION ALL SELECT 'Task legacy GUID differs from normalized owner',COUNT(*)
FROM dbo.Task
WHERE CreatedByUserID IS NOT NULL
    AND TRY_CONVERT(uniqueidentifier,CreatedBy) IS NOT NULL
    AND CreatedByUserID<>TRY_CONVERT(uniqueidentifier,CreatedBy)
UNION ALL SELECT 'Issue legacy GUID differs from normalized owner',COUNT(*)
FROM dbo.Issue
WHERE OwnerUserID IS NOT NULL
    AND TRY_CONVERT(uniqueidentifier,Owner) IS NOT NULL
    AND OwnerUserID<>TRY_CONVERT(uniqueidentifier,Owner);
GO

SELECT fk.name AS ForeignKeyName,fk.is_disabled,fk.is_not_trusted
FROM sys.foreign_keys fk
WHERE fk.name IN ('FK_Requirement_CreatedByUser','FK_Project_CreatedByUser',
                  'FK_Task_CreatedByUser','FK_Issue_OwnerUser');
SELECT t.name AS TableName,i.name AS IndexName,i.is_disabled
FROM sys.indexes i
JOIN sys.tables t ON t.object_id=i.object_id
WHERE i.name IN ('IX_Requirement_CreatedByUserID','IX_Project_CreatedByUserID',
                 'IX_Task_CreatedByUserID','IX_Issue_OwnerUserID');
GO

/* Out-of-scope tables: validation only; no ownership DDL is approved here. */
SELECT 'Risk' AS TableName,COUNT(*) AS [Rows] FROM dbo.Risk
UNION ALL SELECT 'WorkforceRequest',COUNT(*) FROM dbo.WorkforceRequest
UNION ALL SELECT 'KnowledgeSource',COUNT(*) FROM dbo.KnowledgeSource
UNION ALL SELECT 'Skill',COUNT(*) FROM dbo.Skill;
GO

/* -------------------------------------------------------------------------
   5. ROLLBACK: run only after application code is rolled back and traffic is
   drained. Legacy text columns are retained, so GUID backfill can be removed.
   The independent gate prevents accidental execution during validation.
   ------------------------------------------------------------------------- */
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF ISNULL(TRY_CONVERT(bit,SESSION_CONTEXT(N'RollbackApprovedOwnershipDDL')),0)<>1
    BEGIN
        ;THROW 51003,'Rollback blocked. Set RollbackApprovedOwnershipDDL=1 on the reviewed DEV session to proceed.',1;
    END;

    IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID('dbo.Requirement') AND name='FK_Requirement_CreatedByUser')
        ALTER TABLE dbo.Requirement DROP CONSTRAINT FK_Requirement_CreatedByUser;
    IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID('dbo.Project') AND name='FK_Project_CreatedByUser')
        ALTER TABLE dbo.Project DROP CONSTRAINT FK_Project_CreatedByUser;
    IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID('dbo.Task') AND name='FK_Task_CreatedByUser')
        ALTER TABLE dbo.Task DROP CONSTRAINT FK_Task_CreatedByUser;
    IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID('dbo.Issue') AND name='FK_Issue_OwnerUser')
        ALTER TABLE dbo.Issue DROP CONSTRAINT FK_Issue_OwnerUser;

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.Requirement') AND name='IX_Requirement_CreatedByUserID')
        DROP INDEX IX_Requirement_CreatedByUserID ON dbo.Requirement;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.Project') AND name='IX_Project_CreatedByUserID')
        DROP INDEX IX_Project_CreatedByUserID ON dbo.Project;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.Task') AND name='IX_Task_CreatedByUserID')
        DROP INDEX IX_Task_CreatedByUserID ON dbo.Task;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.Issue') AND name='IX_Issue_OwnerUserID')
        DROP INDEX IX_Issue_OwnerUserID ON dbo.Issue;

    IF COL_LENGTH('dbo.Requirement','CreatedByUserID') IS NOT NULL
        ALTER TABLE dbo.Requirement DROP COLUMN CreatedByUserID;
    IF COL_LENGTH('dbo.Project','CreatedByUserID') IS NOT NULL
        ALTER TABLE dbo.Project DROP COLUMN CreatedByUserID;
    IF COL_LENGTH('dbo.Task','CreatedByUserID') IS NOT NULL
        ALTER TABLE dbo.Task DROP COLUMN CreatedByUserID;
    IF COL_LENGTH('dbo.Issue','OwnerUserID') IS NOT NULL
        ALTER TABLE dbo.Issue DROP COLUMN OwnerUserID;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

/* Clear explicit session gates after any approved execution on this connection.
   This statement only clears caller-set session flags; it changes no schema/data.
*/
EXEC sys.sp_set_session_context @key=N'ApplyApprovedOwnershipDDL', @value=NULL;
EXEC sys.sp_set_session_context @key=N'ApplyApprovedOwnershipBackfill', @value=NULL;
EXEC sys.sp_set_session_context @key=N'ApplyApprovedOwnershipConstraints', @value=NULL;
EXEC sys.sp_set_session_context @key=N'RollbackApprovedOwnershipDDL', @value=NULL;
GO