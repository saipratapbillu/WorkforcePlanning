USE AICompany;
GO

IF COL_LENGTH('dbo.WorkforceRequest', 'ProvisionedAgentID') IS NULL
    ALTER TABLE dbo.WorkforceRequest ADD ProvisionedAgentID uniqueidentifier NULL REFERENCES dbo.Agent(AgentID);
GO

IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID('dbo.WorkforceRequest') AND name='CK_WorkforceRequest_Status')
    ALTER TABLE dbo.WorkforceRequest DROP CONSTRAINT CK_WorkforceRequest_Status;
ALTER TABLE dbo.WorkforceRequest WITH CHECK ADD CONSTRAINT CK_WorkforceRequest_Status
    CHECK (Status IN ('PendingApproval','Recruiting','Provisioning','CandidateReady','AgentActive','Filled','Rejected','Cancelled'));
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.WorkforceRequest') AND name='IX_WorkforceRequest_ProvisionedAgentID')
    CREATE INDEX IX_WorkforceRequest_ProvisionedAgentID ON dbo.WorkforceRequest(ProvisionedAgentID, Status);
GO