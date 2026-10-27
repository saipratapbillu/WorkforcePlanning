USE AICompany;
GO

/* Schema prerequisites: these are diagnostic queries; they perform no writes. */
SELECT t.name AS TableName,c.name AS RequiredColumn
FROM (VALUES
    ('AppUser','CompanyID'),('AppUser','DepartmentID'),('AppUser','PositionID'),
    ('Requirement','CreatedByUserID'),('Project','CreatedByUserID'),('Task','CreatedByUserID'),
    ('Issue','OwnerUserID'),('Approval','RequirementID'),('Approval','AssignedToUserID'),
    ('Notification','UserID')
) AS required_columns(TableName,RequiredColumn)
LEFT JOIN sys.tables t ON t.name=required_columns.TableName
LEFT JOIN sys.columns c ON c.object_id=t.object_id AND c.name=required_columns.RequiredColumn
WHERE c.column_id IS NULL
ORDER BY required_columns.TableName,required_columns.RequiredColumn;
GO

/* AppUser organization references must be complete and internally consistent. */
SELECT 'Active user missing CompanyID' AS CheckName,COUNT(*) AS IssueCount
FROM dbo.AppUser WHERE IsActive=1 AND CompanyID IS NULL
UNION ALL SELECT 'Active user missing DepartmentID',COUNT(*)
FROM dbo.AppUser WHERE IsActive=1 AND DepartmentID IS NULL
UNION ALL SELECT 'Active user missing PositionID',COUNT(*)
FROM dbo.AppUser WHERE IsActive=1 AND PositionID IS NULL
UNION ALL SELECT 'Department-company mismatch',COUNT(*)
FROM dbo.AppUser u JOIN dbo.Department d ON d.DepartmentID=u.DepartmentID
WHERE u.CompanyID<>d.CompanyID
UNION ALL SELECT 'Position-department mismatch',COUNT(*)
FROM dbo.AppUser u JOIN dbo.Position p ON p.PositionID=u.PositionID
WHERE u.DepartmentID<>p.DepartmentID
UNION ALL SELECT 'Active user missing/inactive role',COUNT(*)
FROM dbo.AppUser u LEFT JOIN dbo.Role r ON r.RoleID=u.RoleID
WHERE u.IsActive=1 AND (r.RoleID IS NULL OR r.IsActive<>1 OR r.RoleCode IS NULL);
GO

/* Dynamic ownership coverage; counts change as approved business records are added. */
SELECT 'Requirement' AS TableName,COUNT(*) AS TotalRows,
  SUM(CASE WHEN r.CreatedByUserID IS NOT NULL AND u.UserID IS NOT NULL THEN 1 ELSE 0 END) AS ValidOwnerRows,
  SUM(CASE WHEN r.CreatedByUserID IS NULL THEN 1 ELSE 0 END) AS NullOwnerRows,
  SUM(CASE WHEN r.CreatedByUserID IS NOT NULL AND u.UserID IS NULL THEN 1 ELSE 0 END) AS OrphanOwnerRows
FROM dbo.Requirement r LEFT JOIN dbo.AppUser u ON u.UserID=r.CreatedByUserID
UNION ALL SELECT 'Project',COUNT(*),
  SUM(CASE WHEN p.CreatedByUserID IS NOT NULL AND u.UserID IS NOT NULL THEN 1 ELSE 0 END),
  SUM(CASE WHEN p.CreatedByUserID IS NULL THEN 1 ELSE 0 END),
  SUM(CASE WHEN p.CreatedByUserID IS NOT NULL AND u.UserID IS NULL THEN 1 ELSE 0 END)
FROM dbo.Project p LEFT JOIN dbo.AppUser u ON u.UserID=p.CreatedByUserID
UNION ALL SELECT 'Task',COUNT(*),
  SUM(CASE WHEN t.CreatedByUserID IS NOT NULL AND u.UserID IS NOT NULL THEN 1 ELSE 0 END),
  SUM(CASE WHEN t.CreatedByUserID IS NULL THEN 1 ELSE 0 END),
  SUM(CASE WHEN t.CreatedByUserID IS NOT NULL AND u.UserID IS NULL THEN 1 ELSE 0 END)
FROM dbo.Task t LEFT JOIN dbo.AppUser u ON u.UserID=t.CreatedByUserID
UNION ALL SELECT 'Issue',COUNT(*),
  SUM(CASE WHEN i.OwnerUserID IS NOT NULL AND u.UserID IS NOT NULL THEN 1 ELSE 0 END),
  SUM(CASE WHEN i.OwnerUserID IS NULL THEN 1 ELSE 0 END),
  SUM(CASE WHEN i.OwnerUserID IS NOT NULL AND u.UserID IS NULL THEN 1 ELSE 0 END)
FROM dbo.Issue i LEFT JOIN dbo.AppUser u ON u.UserID=i.OwnerUserID;
GO

/* Owner GUID integrity; unresolved legacy text is reported, never guessed. */
SELECT 'Requirement owner null' AS CheckName,COUNT(*) AS IssueCount
FROM dbo.Requirement WHERE CreatedByUserID IS NULL
UNION ALL SELECT 'Requirement owner orphan',COUNT(*)
FROM dbo.Requirement x LEFT JOIN dbo.AppUser u ON u.UserID=x.CreatedByUserID
WHERE x.CreatedByUserID IS NOT NULL AND u.UserID IS NULL
UNION ALL SELECT 'Project owner null',COUNT(*) FROM dbo.Project WHERE CreatedByUserID IS NULL
UNION ALL SELECT 'Project owner orphan',COUNT(*)
FROM dbo.Project x LEFT JOIN dbo.AppUser u ON u.UserID=x.CreatedByUserID
WHERE x.CreatedByUserID IS NOT NULL AND u.UserID IS NULL
UNION ALL SELECT 'Task owner null',COUNT(*) FROM dbo.Task WHERE CreatedByUserID IS NULL
UNION ALL SELECT 'Task owner orphan',COUNT(*)
FROM dbo.Task x LEFT JOIN dbo.AppUser u ON u.UserID=x.CreatedByUserID
WHERE x.CreatedByUserID IS NOT NULL AND u.UserID IS NULL
UNION ALL SELECT 'Issue owner null',COUNT(*) FROM dbo.Issue WHERE OwnerUserID IS NULL
UNION ALL SELECT 'Issue owner orphan',COUNT(*)
FROM dbo.Issue x LEFT JOIN dbo.AppUser u ON u.UserID=x.OwnerUserID
WHERE x.OwnerUserID IS NOT NULL AND u.UserID IS NULL
UNION ALL SELECT 'Approval requirement orphan',COUNT(*)
FROM dbo.Approval a LEFT JOIN dbo.Requirement r ON r.RequirementID=a.RequirementID
WHERE r.RequirementID IS NULL
UNION ALL SELECT 'Approval assignee orphan',COUNT(*)
FROM dbo.Approval a LEFT JOIN dbo.AppUser u ON u.UserID=a.AssignedToUserID
WHERE a.AssignedToUserID IS NOT NULL AND u.UserID IS NULL
UNION ALL SELECT 'Notification recipient orphan',COUNT(*)
FROM dbo.Notification n LEFT JOIN dbo.AppUser u ON u.UserID=n.UserID
WHERE u.UserID IS NULL;
GO

/* Verify policies are enabled and cover every required table. */
SELECT sp.name AS SecurityPolicyName,sp.is_enabled,
       OBJECT_SCHEMA_NAME(pred.target_object_id) AS TargetSchema,
       OBJECT_NAME(pred.target_object_id) AS TargetTable,
       pred.predicate_type_desc,pred.operation_desc,pred.predicate_definition
FROM sys.security_policies sp
JOIN sys.security_predicates pred ON pred.object_id=sp.object_id
WHERE sp.schema_id=SCHEMA_ID('Security')
ORDER BY sp.name,TargetTable,pred.operation_desc;
GO

SELECT required.TableName,
       CASE WHEN EXISTS (
           SELECT 1 FROM sys.security_policies sp
           JOIN sys.security_predicates p ON p.object_id=sp.object_id
           WHERE sp.schema_id=SCHEMA_ID('Security') AND sp.is_enabled=1
             AND p.target_object_id=OBJECT_ID('dbo.'+required.TableName)
       ) THEN 1 ELSE 0 END AS HasEnabledRlsPredicate
FROM (VALUES
  ('Requirement'),('Project'),('Task'),('Issue'),('Approval'),('Notification'),
  ('TaskAssignment'),('TaskDependency'),('Deliverable'),('Evaluation'),
  ('AgentTaskQueue'),('AgentExecution'),('AgentExecutionOutput')
) required(TableName)
ORDER BY required.TableName;
GO

/* Verify request session context. Run from the same connection after authenticated request. */
SELECT TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N'UserID')) AS CurrentRlsUserID;
GO
