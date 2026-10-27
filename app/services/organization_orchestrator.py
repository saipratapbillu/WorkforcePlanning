import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import text


class OrganizationOrchestrator:
    EXECUTIVE_ROLES = {"AI_CEO", "AI_CTO", "AI_COO", "AI_CFO", "AI_CHRO", "AI_CISO", "AI_CHIEF_OF_STAFF"}
    DEPARTMENT_HEAD_GRADES = {"Director"}

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def bootstrap_approved_company(self, db, requirement_id, approval_id):
        approval = db.execute(text("""
            SELECT a.ApprovalID, a.Status, a.ApprovalStage, a.RequirementID, a.AssignedToUserID,
                   r.RoleCode AS ApproverRole
            FROM Approval a WITH (UPDLOCK, HOLDLOCK)
            JOIN AppUser u ON u.UserID=a.AssignedToUserID AND u.IsActive=1
            JOIN Role r ON r.RoleID=u.RoleID AND r.IsActive=1
            WHERE a.ApprovalID=:approval_id
        """), {"approval_id": approval_id}).mappings().first()
        if not approval or approval["Status"] != "Approved" or approval["ApproverRole"] not in {"OWNER", "SUPER_ADMIN"}:
            raise HTTPException(status_code=409, detail="Organization bootstrap requires an approved Owner/Super Admin decision")
        if uuid.UUID(str(approval["RequirementID"])) != uuid.UUID(str(requirement_id)):
            raise HTTPException(status_code=409, detail="Approval does not belong to this requirement")

        company_id = db.execute(text("""
            SELECT TOP 1 CompanyID FROM Agent WHERE AgentName='AI CEO' AND AgentType='Executive' AND Status='Active'
        """)).scalar_one_or_none()
        if not company_id:
            raise HTTPException(status_code=503, detail="No active company AI CEO is configured for organization bootstrap")

        run = db.execute(text("""
            SELECT BootstrapRunID, Status, RoleCount, CreatedAgentCount, ReusedAgentCount
            FROM OrganizationBootstrapRun WITH (UPDLOCK, HOLDLOCK)
            WHERE CompanyID=:company_id
        """), {"company_id": company_id}).mappings().first()
        profiles = db.execute(text("""
            SELECT RoleCode, PositionName, DepartmentName, Grade, ReportsToRoleCode,
                   OrgLayer, JobDescription, ResponsibilitiesJson, RequiredSkillsJson,
                   MaxRecommendedAutonomy
            FROM WorkforceRoleProfile WHERE Status='Active'
            ORDER BY CASE WHEN OrgLayer IN ('Governance','Executive') THEN 0
                          WHEN Grade='Director' THEN 1 ELSE 2 END, RoleCode
        """)).mappings().all()
        if not profiles:
            raise HTTPException(status_code=503, detail="No active workforce role profiles are configured")
        previous_run_completed = bool(run and run["Status"] == "Completed")
        now = self._now()
        run_id = run["BootstrapRunID"] if run else uuid.uuid4()
        if not run:
            db.execute(text("""
                INSERT OrganizationBootstrapRun
                    (BootstrapRunID, CompanyID, TriggerRequirementID, TriggerApprovalID,
                     Status, RoleCount, CreatedAgentCount, ReusedAgentCount, CreatedAtUtc)
                VALUES (:run_id,:company_id,:requirement_id,:approval_id,'Running',0,0,0,:created_at)
            """), {
                "run_id": run_id, "company_id": company_id, "requirement_id": requirement_id,
                "approval_id": approval_id, "created_at": now,
            })
        else:
            db.execute(text("UPDATE OrganizationBootstrapRun SET Status='Running' WHERE BootstrapRunID=:run_id"), {
                "run_id": run_id,
            })

        now = self._now()
        for profile in profiles:
            department = db.execute(text("""
                SELECT TOP 1 DepartmentID FROM Department
                WHERE CompanyID=:company_id AND DepartmentName=:department AND Status='Active'
            """), {"company_id": company_id, "department": profile["DepartmentName"]}).scalar_one_or_none()
            if not department:
                department = uuid.uuid4()
                db.execute(text("""
                    INSERT Department(DepartmentID,CompanyID,DepartmentName,Status,CreatedAtUtc)
                    VALUES(:department_id,:company_id,:department,'Active',:created_at)
                """), {
                    "department_id": department, "company_id": company_id,
                    "department": profile["DepartmentName"], "created_at": now,
                })
            position_id = db.execute(text("""
                SELECT TOP 1 PositionID FROM Position
                WHERE DepartmentID=:department_id AND PositionName=:position_name AND Status='Active'
            """), {"department_id": department, "position_name": profile["PositionName"]}).scalar_one_or_none()
            if not position_id:
                db.execute(text("""
                    INSERT Position(PositionID,DepartmentID,PositionName,Grade,Status)
                    VALUES(:position_id,:department_id,:position_name,:grade,'Active')
                """), {
                    "position_id": uuid.uuid4(), "department_id": department,
                    "position_name": profile["PositionName"], "grade": profile["Grade"],
                })

        # Associate pre-existing, explicitly authorized role provisioning and the seeded CEO.
        db.execute(text("""
            UPDATE agent SET WorkforceRoleCode=wr.RoleCode
            FROM Agent agent
            JOIN WorkforceRequest wr ON wr.ProvisionedAgentID=agent.AgentID
            WHERE agent.CompanyID=:company_id AND agent.WorkforceRoleCode IS NULL
        """), {"company_id": company_id})
        db.execute(text("""
            UPDATE Agent SET WorkforceRoleCode='AI_CEO'
            WHERE CompanyID=:company_id AND AgentName='AI CEO' AND AgentType='Executive' AND WorkforceRoleCode IS NULL
        """), {"company_id": company_id})

        created_count = 0
        reused_count = 0
        agent_ids = {}
        for profile in profiles:
            role_code = profile["RoleCode"]
            agent = db.execute(text("""
                SELECT AgentID, Status, DepartmentID, PositionID FROM Agent
                WHERE CompanyID=:company_id AND WorkforceRoleCode=:role_code
            """), {"company_id": company_id, "role_code": role_code}).mappings().first()
            if agent:
                if agent["Status"] == "Provisioning":
                    self._ensure_pending_skills(db, agent["AgentID"], profile)
                    department_id, position_id = db.execute(text("""
                        SELECT d.DepartmentID,p.PositionID FROM Department d JOIN Position p ON p.DepartmentID=d.DepartmentID
                        WHERE d.CompanyID=:company_id AND d.DepartmentName=:department
                          AND p.PositionName=:position AND p.Status='Active'
                    """), {
                        "company_id": company_id, "department": profile["DepartmentName"],
                        "position": profile["PositionName"],
                    }).one()
                    agent_type = "Executive" if profile["OrgLayer"] in {"Executive", "Governance"} else ("DepartmentHead" if profile["Grade"] == "Director" else "Specialist")
                    db.execute(text("""
                        UPDATE Agent SET DepartmentID=:department_id,PositionID=:position_id,
                            AgentName=:agent_name,AgentType=:agent_type,Grade=:grade,
                            JobDescription=:job_description,ResponsibilitiesJson=:responsibilities,
                            AutonomyLevel=:autonomy,ModifiedBy=:actor
                        WHERE AgentID=:agent_id
                    """), {
                        "department_id": department_id, "position_id": position_id,
                        "agent_name": profile["PositionName"], "agent_type": agent_type,
                        "grade": profile["Grade"], "job_description": profile["JobDescription"],
                        "responsibilities": profile["ResponsibilitiesJson"],
                        "autonomy": min(int(profile["MaxRecommendedAutonomy"] or 1), 1),
                        "actor": f"organization-bootstrap:{approval_id}", "agent_id": agent["AgentID"],
                    })
                agent_ids[role_code] = agent["AgentID"]
                reused_count += 1
                continue

            department_id, position_id = db.execute(text("""
                SELECT d.DepartmentID, p.PositionID FROM Department d
                JOIN Position p ON p.DepartmentID=d.DepartmentID
                WHERE d.CompanyID=:company_id AND d.DepartmentName=:department
                  AND p.PositionName=:position AND p.Status='Active'
            """), {
                "company_id": company_id, "department": profile["DepartmentName"],
                "position": profile["PositionName"],
            }).one()
            agent_id = uuid.uuid4()
            agent_type = "Executive" if profile["OrgLayer"] in {"Executive", "Governance"} else ("DepartmentHead" if profile["Grade"] == "Director" else "Specialist")
            db.execute(text("""
                INSERT INTO Agent
                    (AgentID,CompanyID,DepartmentID,PositionID,AgentName,AgentType,Grade,
                     ManagerAgentID,DirectorAgentID,JobDescription,ResponsibilitiesJson,
                     Model,ModelVersion,PromptVersion,AutonomyLevel,RiskLevel,CostLimitMonthly,
                     TokenLimitDaily,ConcurrentTaskLimit,CurrentWorkload,Status,CreatedBy,ModifiedBy,WorkforceRoleCode)
                VALUES
                    (:agent_id,:company_id,:department_id,:position_id,:agent_name,:agent_type,:grade,
                     NULL,NULL,:job_description,:responsibilities,'UNCONFIGURED','UNCONFIGURED','1.0.0',
                     :autonomy,'High',0,0,1,0,'Provisioning',:actor,:actor,:role_code)
            """), {
                "agent_id": agent_id, "company_id": company_id, "department_id": department_id,
                "position_id": position_id, "agent_name": profile["PositionName"],
                "agent_type": agent_type, "grade": profile["Grade"],
                "job_description": profile["JobDescription"],
                "responsibilities": profile["ResponsibilitiesJson"],
                "autonomy": min(int(profile["MaxRecommendedAutonomy"] or 1), 1),
                "actor": f"organization-bootstrap:{approval_id}", "role_code": role_code,
            })
            agent_ids[role_code] = agent_id
            created_count += 1
            self._ensure_pending_skills(db, agent_id, profile)

        for profile in profiles:
            parent_role = profile["ReportsToRoleCode"]
            agent_id = agent_ids[profile["RoleCode"]]
            if not parent_role or parent_role not in agent_ids or parent_role == profile["RoleCode"]:
                continue
            parent_id = agent_ids[parent_role]
            db.execute(text("""
                UPDATE Agent SET ManagerAgentID=:manager_id,
                    DirectorAgentID=CASE WHEN :parent_is_director=1 THEN :manager_id ELSE DirectorAgentID END
                WHERE AgentID=:agent_id
            """), {
                "manager_id": parent_id,
                "parent_is_director": parent_role in {row["RoleCode"] for row in profiles if row["Grade"] == "Director"},
                "agent_id": agent_id,
            })

        db.execute(text("""
            UPDATE wr SET ProvisionedAgentID=agent.AgentID, Status='Provisioning'
            FROM WorkforceRequest wr
            JOIN Project p ON p.ProjectID=wr.ProjectID AND p.RequirementID=:requirement_id
            JOIN Agent agent ON agent.CompanyID=:company_id AND agent.WorkforceRoleCode=wr.RoleCode
            WHERE wr.Status IN ('PendingApproval','Recruiting')
              AND wr.ProvisionedAgentID IS NULL
        """), {"requirement_id": requirement_id, "company_id": company_id})

        db.execute(text("""
            UPDATE OrganizationBootstrapRun SET Status='Completed', RoleCount=:role_count,
                CreatedAgentCount=:created_count, ReusedAgentCount=:reused_count,
                CompletedAtUtc=:completed_at, TriggerRequirementID=:requirement_id,
                TriggerApprovalID=:approval_id
            WHERE BootstrapRunID=:run_id
        """), {
            "role_count": len(profiles),
            "created_count": (int(run["CreatedAgentCount"] or 0) + created_count) if previous_run_completed else created_count,
            "reused_count": len(profiles) - ((int(run["CreatedAgentCount"] or 0) + created_count) if previous_run_completed else created_count),
            "completed_at": now,
            "requirement_id": requirement_id, "approval_id": approval_id, "run_id": run_id,
        })
        db.execute(text("""
            INSERT AuditLog(CorrelationID,ActorType,ActorID,Action,ResourceType,ResourceID,Outcome,Details)
            VALUES(:correlation,'System','organization-orchestrator','OrganizationBootstrapCompleted',
                   'OrganizationBootstrapRun',:resource,'Success',:details)
        """), {
            "correlation": uuid.uuid4(), "resource": str(run_id),
            "details": json.dumps({"role_count": len(profiles), "created_agents": created_count, "reused_agents": reused_count, "agents_activated": 0}),
        })
        return {
            "bootstrap_run_id": str(run_id), "status": "Completed", "role_count": len(profiles),
            "created_agent_count": int(run["CreatedAgentCount"] or 0) + created_count if previous_run_completed else created_count,
            "reused_agent_count": len(profiles) - (int(run["CreatedAgentCount"] or 0) + created_count if previous_run_completed else created_count),
            "new_agents_active": 0,
            "existing_active_agents_preserved": db.execute(text("SELECT COUNT(*) FROM Agent WHERE CompanyID=:company_id AND Status='Active'"), {"company_id": company_id}).scalar_one(),
            "idempotent": previous_run_completed and created_count == 0,
            "message": "Organization structure provisioned in non-active states; provider configuration and safety evaluation are required before activation.",
        }

    @staticmethod
    def _ensure_pending_skills(db, agent_id, profile):
        for skill in json.loads(profile["RequiredSkillsJson"]):
            existing = db.execute(text("""
                SELECT 1 FROM AgentSkill ags JOIN Skill s ON s.SkillID=ags.SkillID
                WHERE ags.AgentID=:agent_id AND s.Name=:skill_name
            """), {"agent_id": agent_id, "skill_name": skill["name"]}).first()
            if existing:
                continue
            inserted = db.execute(text("""
                INSERT INTO AgentSkill(AgentID,SkillID,Proficiency,Status)
                SELECT :agent_id,SkillID,:proficiency,'Pending'
                FROM Skill WHERE Name=:skill_name AND Status='Approved'
            """), {
                "agent_id": agent_id, "proficiency": int(skill["minimum_proficiency"]),
                "skill_name": skill["name"],
            })
            if inserted.rowcount != 1:
                raise HTTPException(status_code=409, detail=f"Required skill {skill['name']} is missing or not approved")
