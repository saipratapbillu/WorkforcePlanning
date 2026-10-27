/* Add the explicit Retired decision value used by the model lifecycle workflow. */
USE AICompany;
GO
IF OBJECT_ID('dbo.AIModelApproval','U') IS NOT NULL
BEGIN
    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID('dbo.AIModelApproval') AND name='CK_AIModelApproval_Decision')
        ALTER TABLE dbo.AIModelApproval DROP CONSTRAINT CK_AIModelApproval_Decision;
    IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID('dbo.AIModelApproval') AND name='CK_AIModelApproval_Decision')
        ALTER TABLE dbo.AIModelApproval ADD CONSTRAINT CK_AIModelApproval_Decision CHECK(Decision IN ('Approved','Rejected','Retired'));
END;
GO
