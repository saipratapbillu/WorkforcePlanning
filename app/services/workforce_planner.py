import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import text


REQUIRED_AGENT_CERTIFICATIONS = {"Capability", "Safety", "Security", "Governance"}

TASK_PLAN = (
    ("Requirements confirmation", "BUSINESS_ANALYST", "RequirementAnalysis"),
    ("Solution design", "DELIVERY_LEAD", "ProjectPlanning"),
    ("Implementation", "SOFTWARE_DEVELOPER", "SoftwareDevelopment"),
    ("Verification and testing", "QA_ENGINEER", "QualityTesting"),
    ("Deployment readiness", "SECURITY_ENGINEER", "SecurityReview"),
    ("Training and handover", "HR_WORKFORCE_COORDINATOR", "HRProcessDesign"),
    ("Hypercare and support", "DELIVERY_LEAD", "ProjectPlanning"),
)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def agent_meets_profile(profile: dict, skills: dict[str, int]) -> bool:
    required = json.loads(profile["RequiredSkillsJson"])
    return all(skills.get(item["name"], 0) >= int(item["minimum_proficiency"]) for item in required)


def assess_workforce_match(profile: dict, agent: dict, skills: dict[str, int], certifications: set[str]) -> dict:
    required = json.loads(profile["RequiredSkillsJson"])
    skill_fit = sum(
        min(max(int(skills.get(item["name"], 0)), 0), int(item["minimum_proficiency"]))
        / int(item["minimum_proficiency"])
        for item in required
    ) / len(required) if required else 1.0
    workload = min(max(float(agent.get("CurrentWorkload") or 0), 0), 100)
    assignment_limit = max(int(agent.get("ConcurrentTaskLimit") or 1), 1)
    active_assignments = int(agent.get("ActiveAssignments") or 0)
    has_capacity = agent.get("Status") == "Active" and workload < 100 and active_assignments < assignment_limit
    score = int(100 * skill_fit)
    classification = "Ready Candidate" if score == 100 else (
        "Strong Candidate" if score >= 80 else "Upskill Candidate" if score >= 50 else "Workforce Request"
    )
    skill_plan = []
    for item in required:
        required_level = int(item["minimum_proficiency"])
        current_level = max(int(skills.get(item["name"], 0)), 0)
        gap = max(required_level - current_level, 0)
        skill_plan.append({
            "required_skill": item["name"],
            "required_proficiency": required_level,
            "current_skill": current_level,
            "gap": gap,
            "recommendation": (
                f"Targeted training and evidence-backed assessment for {item['name']}"
                if gap else "Already meets the required proficiency; reuse without a skill change"
            ),
        })

    readiness_days = max((item["gap"] * 5 for item in skill_plan), default=0)
    blockers = []
    if not has_capacity:
        blockers.append("Agent is not Active with available workload capacity")
    missing_certifications = sorted(REQUIRED_AGENT_CERTIFICATIONS - certifications)
    if missing_certifications:
        blockers.append("Missing current certifications: " + ", ".join(missing_certifications))
    return {
        "match_score": score,
        "classification": classification,
        "skill_plan": skill_plan,
        "estimated_readiness_days": readiness_days,
        "missing_certifications": missing_certifications,
        "capacity_available": has_capacity,
        "blockers": blockers,
    }


class WorkforcePlanner:
    @staticmethod
    def reuse_assessments_available(db) -> bool:
        return bool(db.execute(text("""
            SELECT CASE WHEN OBJECT_ID('dbo.WorkforceReuseAssessment', 'U') IS NULL THEN 0 ELSE 1 END
        """)).scalar_one())

    @staticmethod
    def certified_agent_ids(db) -> set:
        rows = db.execute(text("""
            WITH RankedEvaluations AS (
                SELECT AgentID,EvaluationType,Passed,
                       ROW_NUMBER() OVER(PARTITION BY AgentID,EvaluationType ORDER BY CreatedAtUtc DESC,EvaluationID DESC) AS RowNumber
                FROM dbo.Evaluation
            )
            SELECT AgentID,EvaluationType FROM RankedEvaluations
            WHERE RowNumber=1 AND Passed=1
        """)).mappings().all()
        certifications = {}
        for row in rows:
            certifications.setdefault(row["AgentID"], set()).add(row["EvaluationType"])
        return {
            agent_id for agent_id, evaluations in certifications.items()
            if REQUIRED_AGENT_CERTIFICATIONS.issubset(evaluations)
        }

    @staticmethod
    def latest_passed_evaluation_types(db, agent_id) -> set[str]:
        rows = db.execute(text("""
            WITH RankedEvaluations AS (
                SELECT EvaluationType,Passed,
                       ROW_NUMBER() OVER(PARTITION BY EvaluationType ORDER BY CreatedAtUtc DESC,EvaluationID DESC) AS RowNumber
                FROM dbo.Evaluation WHERE AgentID=:agent_id
            )
            SELECT EvaluationType FROM RankedEvaluations WHERE RowNumber=1 AND Passed=1
        """), {"agent_id": agent_id}).all()
        return {row[0] for row in rows}

    @staticmethod
    def agent_activation_blockers(agent: dict, passed_evaluation_types: set[str]) -> list[str]:
        blockers = []
        if agent.get("Status") != "Provisioning":
            blockers.append("agent is not in Provisioning state")
        if not agent.get("Model") or agent["Model"] == "UNCONFIGURED":
            blockers.append("approved model is not configured")
        if not agent.get("ModelVersion") or agent["ModelVersion"] == "UNCONFIGURED":
            blockers.append("model version is not configured")
        if not agent.get("ModelProvider") or agent["ModelProvider"] == "UNCONFIGURED":
            blockers.append("approved provider is not configured")
        missing = {"Capability", "Safety", "Security", "Governance"} - passed_evaluation_types
        if missing:
            blockers.append("passed evaluations missing: " + ", ".join(sorted(missing)))
        return blockers

    @staticmethod
    def agent_readiness_blockers(db, agent: dict) -> list[str]:
        passed = WorkforcePlanner.latest_passed_evaluation_types(db, agent["AgentID"])
        blockers = WorkforcePlanner.agent_activation_blockers(dict(agent), passed)
        role_code = agent.get("WorkforceRoleCode")
        profile = db.execute(text("""
            SELECT RequiredSkillsJson FROM dbo.WorkforceRoleProfile
            WHERE RoleCode=:role_code AND Status='Active'
        """), {"role_code": role_code}).mappings().first()
        if not profile:
            blockers.append("active workforce role profile is missing")
            return blockers
        active_skills = {
            row["Name"]: int(row["Proficiency"])
            for row in db.execute(text("""
                SELECT s.Name,MAX(ags.Proficiency) AS Proficiency
                FROM dbo.AgentSkill ags JOIN dbo.Skill s ON s.SkillID=ags.SkillID
                WHERE ags.AgentID=:agent_id AND ags.Status='Active'
                GROUP BY s.Name
            """), {"agent_id": agent["AgentID"]}).mappings().all()
        }
        if not agent_meets_profile(dict(profile), active_skills):
            blockers.append("required skills are not Active at the role minimum proficiency")
        return blockers

    @staticmethod
    def provision_agent(db, workforce_request, actor_id):
        existing_id = workforce_request.get("ProvisionedAgentID")
        if existing_id:
            return existing_id
        if workforce_request["Status"] != "Recruiting":
            raise HTTPException(status_code=409, detail="A workforce request must have recruiting authorization before agent provisioning")

        role = db.execute(text("""
            SELECT RoleCode, PositionName, DepartmentName, Grade,
                   JobDescription, ResponsibilitiesJson, RequiredSkillsJson,
                   MaxRecommendedAutonomy
            FROM WorkforceRoleProfile
            WHERE RoleCode=:role_code AND Status='Active'
        """), {"role_code": workforce_request["RoleCode"]}).mappings().first()
        if not role:
            raise HTTPException(status_code=409, detail="An active workforce role profile is required for provisioning")

        existing_role_agent = db.execute(text("""
            SELECT AgentID, Status FROM Agent
            WHERE WorkforceRoleCode=:role_code
        """), {"role_code": workforce_request["RoleCode"]}).mappings().first()
        if existing_role_agent:
            if existing_role_agent["Status"] not in {"Provisioning", "Active"}:
                raise HTTPException(status_code=409, detail="Existing company role agent is not eligible for this workforce request")
            WorkforcePlanner._ensure_pending_skills(db, existing_role_agent["AgentID"], dict(role))
            db.execute(text("""
                UPDATE WorkforceRequest SET Status='Provisioning', ProvisionedAgentID=:agent_id
                WHERE WorkforceRequestID=:request_id
            """), {"agent_id": existing_role_agent["AgentID"], "request_id": workforce_request["WorkforceRequestID"]})
            return existing_role_agent["AgentID"]

        now = _now()
        agent_id = uuid.uuid4()
        agent_name = role["PositionName"]
        existing_name = db.execute(text("SELECT 1 FROM Agent WHERE AgentName=:agent_name AND Status NOT IN ('Retired','Inactive')"), {
            "agent_name": agent_name,
        }).first()
        if existing_name:
            agent_name = f"{role['PositionName']} ({str(workforce_request['WorkforceRequestID'])[:8]})"

        db.execute(text("""
            INSERT INTO Agent
                (AgentID, CompanyID, DepartmentID, PositionID, AgentName, AgentType, Grade,
                 JobDescription, ResponsibilitiesJson, Model, ModelVersion, PromptVersion,
                 AutonomyLevel, RiskLevel, CostLimitMonthly, TokenLimitDaily, ConcurrentTaskLimit,
                 CurrentWorkload, Status, CreatedBy, ModifiedBy, WorkforceRoleCode)
            VALUES
                (:agent_id, :company_id, :department_id, :position_id, :agent_name, 'Specialist', :grade,
                 :job_description, :responsibilities, 'UNCONFIGURED', 'UNCONFIGURED', '1.0.0',
                 :autonomy, 'High', 0, 0, 1, 0, 'Provisioning', :actor, :actor, :role_code)
        """), {
            "agent_id": agent_id,
            "company_id": None,
            "department_id": None,
            "position_id": None,
            "agent_name": agent_name,
            "grade": role["Grade"],
            "job_description": role["JobDescription"],
            "responsibilities": role["ResponsibilitiesJson"],
            "autonomy": min(int(role["MaxRecommendedAutonomy"] or 1), 1),
            "actor": str(actor_id), "role_code": workforce_request["RoleCode"],
        })
        WorkforcePlanner._ensure_pending_skills(db, agent_id, dict(role))

        db.execute(text("""
            UPDATE WorkforceRequest
            SET Status='Provisioning', ProvisionedAgentID=:agent_id, FilledAgentID=NULL
            WHERE WorkforceRequestID=:request_id
        """), {"agent_id": agent_id, "request_id": workforce_request["WorkforceRequestID"]})
        return agent_id

    @staticmethod
    def _ensure_pending_skills(db, agent_id, profile):
        for skill in json.loads(profile["RequiredSkillsJson"]):
            if db.execute(text("""
                SELECT 1 FROM AgentSkill ags JOIN Skill s ON s.SkillID=ags.SkillID
                WHERE ags.AgentID=:agent_id AND s.Name=:skill_name
            """), {"agent_id": agent_id, "skill_name": skill["name"]}).first():
                continue
            inserted = db.execute(text("""
                INSERT INTO AgentSkill(AgentID, SkillID, Proficiency, Status)
                SELECT :agent_id, SkillID, :proficiency, 'Pending'
                FROM Skill WHERE Name=:skill_name AND Status='Approved'
            """), {
                "agent_id": agent_id,
                "proficiency": int(skill["minimum_proficiency"]),
                "skill_name": skill["name"],
            })
            if inserted.rowcount != 1:
                raise HTTPException(status_code=409, detail=f"Required skill {skill['name']} is missing or not approved")

    @staticmethod
    def activate_provisioned_agent(db, workforce_request, actor_id, reason):
        agent_id = workforce_request["ProvisionedAgentID"]
        if not agent_id or workforce_request["Status"] != "Provisioning":
            raise HTTPException(status_code=409, detail="No agent is awaiting provisioning validation")
        agent = db.execute(text("""
            SELECT AgentID, ModelProvider, Model, ModelVersion, Status, WorkforceRoleCode FROM Agent WHERE AgentID=:agent_id
        """), {"agent_id": agent_id}).mappings().first()
        if not agent:
            raise HTTPException(status_code=409, detail="Provisioned agent is not in the expected lifecycle state")

        blockers = WorkforcePlanner.agent_readiness_blockers(db, dict(agent))
        if blockers:
            raise HTTPException(status_code=409, detail="Agent activation is blocked: " + "; ".join(blockers))

        db.execute(text("""
            UPDATE Agent SET Status='Active', LastEvaluationDate=:now, ModifiedDate=:now, ModifiedBy=:actor
            WHERE AgentID=:agent_id
        """), {"now": _now(), "actor": str(actor_id), "agent_id": agent_id})
        db.execute(text("""
            UPDATE WorkforceRequest SET Status='AgentActive', DecisionBy=:actor,
                DecisionReason=:reason, DecisionAtUtc=:now
            WHERE WorkforceRequestID=:request_id
        """), {
            "actor": str(actor_id), "reason": reason.strip(), "now": _now(),
            "request_id": workforce_request["WorkforceRequestID"],
        })
        db.execute(text("""
            UPDATE AgentActivationBlocker SET Status='Resolved', ResolvedAtUtc=:resolved_at
            WHERE AgentID=:agent_id AND Status='Open'
        """), {"resolved_at": _now(), "agent_id": agent_id})

        project = db.execute(text("""
            SELECT p.ProjectID, p.Status, r.RequirementID, r.CreatedBy, r.Priority, r.RiskLevel,
                   r.Title, r.Description, r.RequestedBy
            FROM Project p JOIN Requirement r ON r.RequirementID=p.RequirementID
            WHERE p.ProjectID=:project_id
        """), {"project_id": workforce_request["ProjectID"]}).mappings().first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found for workforce request")
        summary = WorkforcePlanner().plan_project(db, project["ProjectID"], project)
        return agent_id, summary

    def auto_assign_agents(self, db, project_id, requirement):
        return self.plan_project(db, project_id, requirement)

    def plan_project(self, db, project_id, requirement):
        reuse_assessments_available = self.reuse_assessments_available(db)
        project_status = db.execute(text("SELECT Status FROM Project WHERE ProjectID=:project_id"), {
            "project_id": project_id,
        }).scalar_one_or_none()
        if not project_status:
            raise HTTPException(status_code=404, detail="Project not found")
        requirement_id = getattr(requirement, "RequirementID", None) or requirement["RequirementID"]
        profiles = {
            row["RoleCode"]: dict(row)
            for row in db.execute(text("""
                SELECT RoleCode, PositionName, DepartmentName, JobDescription,
                       ResponsibilitiesJson, RequiredSkillsJson
                FROM WorkforceRoleProfile WHERE Status = 'Active'
            """)).mappings().all()
        }
        tasks = db.execute(text("""
            SELECT TaskID, Description, Status, AssignedAgentID
            FROM Task WHERE ProjectID = :project_id
            ORDER BY CASE Description
                WHEN 'Requirements confirmation' THEN 1
                WHEN 'Solution design' THEN 2
                WHEN 'Implementation' THEN 3
                WHEN 'Verification and testing' THEN 4
                WHEN 'Deployment readiness' THEN 5
                WHEN 'Training and handover' THEN 6
                WHEN 'Hypercare and support' THEN 7
                ELSE 99 END, CreatedAtUtc, TaskID
        """), {"project_id": project_id}).mappings().all()
        if not tasks:
            raise HTTPException(status_code=409, detail="Project has no tasks to plan")
        if len(tasks) > len(TASK_PLAN):
            raise HTTPException(status_code=409, detail="Task plan has more tasks than the approved role map; review decomposition before staffing")

        effort_by_skill = {
            row["SkillName"]: float(row["EffortHours"] or 0)
            for row in db.execute(text("""
                SELECT s.Name AS SkillName, SUM(rs.EstimatedEffortHours) AS EffortHours
                FROM RequirementSkill rs JOIN Skill s ON s.SkillID = rs.SkillID
                WHERE rs.RequirementID = :requirement_id
                GROUP BY s.Name
            """), {"requirement_id": requirement.RequirementID}).mappings().all()
        }
        agents = db.execute(text("""
            SELECT a.AgentID, a.AgentName, a.AgentType, a.WorkforceRoleCode,
                   a.CurrentWorkload, a.ConcurrentTaskLimit, a.Status,
                   COUNT(CASE WHEN ta.ReleasedAtUtc IS NULL AND ta.Status = 'Active' THEN 1 END) AS ActiveAssignments
            FROM Agent a
            LEFT JOIN TaskAssignment ta ON ta.AgentID = a.AgentID
            WHERE a.Status IN ('Active','Provisioning')
            GROUP BY a.AgentID, a.AgentName, a.AgentType, a.WorkforceRoleCode, a.CurrentWorkload, a.ConcurrentTaskLimit, a.Status
            ORDER BY a.CurrentWorkload, a.AgentName
        """)).mappings().all()
        agent_skills = {}
        skill_status_by_agent = {}
        for row in db.execute(text("""
            SELECT ags.AgentID, s.Name AS SkillName,
                   MAX(CASE WHEN ags.Status='Active' THEN ags.Proficiency ELSE 0 END) AS Proficiency
            FROM AgentSkill ags JOIN Skill s ON s.SkillID = ags.SkillID
            WHERE ags.Status IN ('Active','Pending')
            GROUP BY ags.AgentID, s.Name
        """)).mappings().all():
            agent_skills.setdefault(row["AgentID"], {})[row["SkillName"]] = int(row["Proficiency"])

        certified_agents = self.certified_agent_ids(db)
        latest_evaluations = db.execute(text("""
            WITH RankedEvaluations AS (
                SELECT AgentID,EvaluationType,Passed,
                       ROW_NUMBER() OVER(PARTITION BY AgentID,EvaluationType ORDER BY CreatedAtUtc DESC,EvaluationID DESC) AS RowNumber
                FROM dbo.Evaluation
            )
            SELECT AgentID,EvaluationType FROM RankedEvaluations WHERE RowNumber=1 AND Passed=1
        """)).mappings().all()
        certifications_by_agent = {}
        for row in latest_evaluations:
            certifications_by_agent.setdefault(row["AgentID"], set()).add(row["EvaluationType"])
        role_agents = {}
        for role_code, profile in profiles.items():
            eligible = [
                agent for agent in agents
                if agent["AgentType"] != "Executive"
                and agent["Status"] == "Active"
                and agent["AgentID"] in certified_agents
                and int(agent["ActiveAssignments"] or 0) < int(agent["ConcurrentTaskLimit"] or 1)
                and float(agent["CurrentWorkload"] or 0) < 100
                and agent_meets_profile(profile, agent_skills.get(agent["AgentID"], {}))
            ]
            role_agents[role_code] = eligible

        def reserve_agent(agent_id):
            for candidates in role_agents.values():
                candidates[:] = [candidate for candidate in candidates if candidate["AgentID"] != agent_id]

        now = _now()
        requested_roles = set()
        assigned_count = 0
        upskill_candidate_count = 0
        planned_effort = {}
        lead_candidates = role_agents.get("DELIVERY_LEAD", [])
        if lead_candidates:
            lead = lead_candidates[0]
            db.execute(text("""
                IF NOT EXISTS (SELECT 1 FROM ProjectAgent WHERE ProjectID = :project_id AND AgentID = :agent_id)
                INSERT ProjectAgent(ProjectID, AgentID, ProjectRole, AssignedAtUtc)
                VALUES (:project_id, :agent_id, 'Delivery Lead', :assigned_at)
            """), {"project_id": project_id, "agent_id": lead["AgentID"], "assigned_at": now})
        else:
            requested_roles.add(("DELIVERY_LEAD", None))

        for sequence, task in enumerate(tasks, start=1):
            template = TASK_PLAN[min(sequence - 1, len(TASK_PLAN) - 1)]
            description, role_code, skill_name = template
            if role_code not in profiles:
                raise HTTPException(status_code=503, detail=f"Workforce profile {role_code} is not installed")
            effort = effort_by_skill.get(skill_name)
            if skill_name in planned_effort:
                effort = None
            else:
                planned_effort[skill_name] = True
            db.execute(text("""
                UPDATE Task
                SET PlannedSequence = :sequence, RequiredRoleCode = :role_code,
                    EstimatedEffortHours = :effort,
                    Description = CASE WHEN Description IN (
                        'Requirements confirmation','Solution design','Implementation',
                        'Verification and testing','Deployment readiness','Training and handover',
                        'Hypercare and support'
                    ) THEN :description ELSE Description END
                WHERE TaskID = :task_id
            """), {
                "sequence": sequence,
                "role_code": role_code,
                "effort": effort,
                "description": description,
                "task_id": task["TaskID"],
            })
            if sequence > 1:
                dependency_task_id = tasks[sequence - 2]["TaskID"]
                db.execute(text("""
                    IF NOT EXISTS (SELECT 1 FROM TaskDependency WHERE TaskID=:task_id AND DependsOnTaskID=:dependency_id)
                    INSERT TaskDependency(TaskID, DependsOnTaskID, DependencyType)
                    VALUES (:task_id, :dependency_id, 'FinishStart')
                """), {"task_id": task["TaskID"], "dependency_id": dependency_task_id})
            if task["AssignedAgentID"]:
                assigned_count += 1
            elif role_agents.get(role_code):
                agent = role_agents[role_code].pop(0)
                reserve_agent(agent["AgentID"])
                db.execute(text("UPDATE Task SET AssignedAgentID = :agent_id WHERE TaskID = :task_id"), {
                    "agent_id": agent["AgentID"], "task_id": task["TaskID"],
                })
                db.execute(text("""
                    IF NOT EXISTS (
                        SELECT 1 FROM TaskAssignment
                        WHERE TaskID = :task_id AND AgentID = :agent_id AND ReleasedAtUtc IS NULL
                    )
                    INSERT TaskAssignment(TaskAssignmentID, TaskID, AgentID, AssignedAtUtc, Status)
                    VALUES (:assignment_id, :task_id, :agent_id, :assigned_at, 'Active')
                """), {
                    "assignment_id": uuid.uuid4(), "task_id": task["TaskID"],
                    "agent_id": agent["AgentID"], "assigned_at": now,
                })
                assigned_count += 1
            else:
                requested_roles.add((role_code, task["TaskID"]))

        created_requests = 0
        for role_code, task_id in list(requested_roles):
            existing = db.execute(text("""
                SELECT WorkforceRequestID FROM WorkforceRequest
                                WHERE ProjectID = :project_id AND RoleCode = :role_code
            """), {"project_id": project_id, "role_code": role_code}).scalar_one_or_none()
            if existing:
                continue
            profile = profiles[role_code]
            assessments = []
            if reuse_assessments_available:
                for candidate in agents:
                    if candidate["AgentType"] == "Executive":
                        continue
                    assessment = assess_workforce_match(
                        profile, dict(candidate), agent_skills.get(candidate["AgentID"], {}),
                        certifications_by_agent.get(candidate["AgentID"], set()),
                    )
                    assessments.append((candidate, assessment))
                rejected_agents = set(db.execute(text("""
                    SELECT AgentID FROM dbo.WorkforceReuseAssessment
                    WHERE ProjectID=:project_id AND RoleCode=:role_code AND AssessmentStatus='Rejected'
                """), {"project_id": project_id, "role_code": role_code}).scalars().all())
            else:
                rejected_agents = set()
            reusable = [
                item for item in assessments
                if item[1]["match_score"] >= 50 and item[0]["AgentID"] not in rejected_agents
            ]
            selected_agent_id = None
            if reusable:
                upskill_candidate_count += sum(
                    assessment["classification"] == "Upskill Candidate"
                    for _candidate, assessment in reusable
                )
                reusable.sort(key=lambda item: (
                    -item[1]["match_score"],
                    item[0]["Status"] != "Active",
                    float(item[0]["CurrentWorkload"] or 0),
                    item[0]["AgentName"],
                ))
                selected_agent, _selected_assessment = reusable[0]
                selected_agent_id = selected_agent["AgentID"]
                requested_roles.discard((role_code, task_id))
            for candidate, assessment in assessments if reuse_assessments_available else ():
                assessment_id = uuid.uuid4()
                selected = candidate["AgentID"] == selected_agent_id
                assessment_status = "PendingApproval" if selected else "Considered"
                db.execute(text("""
                    IF EXISTS (SELECT 1 FROM dbo.WorkforceReuseAssessment
                               WHERE ProjectID=:project_id AND RoleCode=:role_code AND AgentID=:agent_id)
                        UPDATE dbo.WorkforceReuseAssessment
                        SET TaskID=:task_id,MatchScore=:match_score,Classification=:classification,
                            SkillPlanJson=:skill_plan,MissingCertificationsJson=:missing_certifications,
                            CapacityAvailable=:capacity_available,EstimatedReadinessDays=:readiness_days,
                            AssessmentStatus=CASE WHEN AssessmentStatus IN ('Approved','Rejected','Completed')
                                                  THEN AssessmentStatus ELSE :assessment_status END,
                            AssessedAtUtc=:assessed_at
                        WHERE ProjectID=:project_id AND RoleCode=:role_code AND AgentID=:agent_id
                    ELSE
                        INSERT dbo.WorkforceReuseAssessment
                            (AssessmentID,ProjectID,TaskID,RoleCode,AgentID,MatchScore,Classification,
                             SkillPlanJson,MissingCertificationsJson,CapacityAvailable,EstimatedReadinessDays,
                             AssessmentStatus,AssessedAtUtc)
                        VALUES
                            (:assessment_id,:project_id,:task_id,:role_code,:agent_id,:match_score,:classification,
                             :skill_plan,:missing_certifications,:capacity_available,:readiness_days,
                             :assessment_status,:assessed_at)
                """), {
                    "assessment_id": assessment_id, "project_id": project_id, "task_id": task_id,
                    "role_code": role_code, "agent_id": candidate["AgentID"],
                    "match_score": assessment["match_score"], "classification": assessment["classification"],
                    "skill_plan": json.dumps(assessment["skill_plan"], ensure_ascii=True),
                    "missing_certifications": json.dumps(assessment["missing_certifications"], ensure_ascii=True),
                    "capacity_available": assessment["capacity_available"],
                    "readiness_days": assessment["estimated_readiness_days"],
                    "assessment_status": assessment_status, "assessed_at": now,
                })
                persisted_assessment = db.execute(text("""
                    SELECT AssessmentID,AssessmentStatus FROM dbo.WorkforceReuseAssessment
                    WHERE ProjectID=:project_id AND RoleCode=:role_code AND AgentID=:agent_id
                """), {
                    "project_id": project_id, "role_code": role_code, "agent_id": candidate["AgentID"],
                }).mappings().one()
                if selected and persisted_assessment["AssessmentStatus"] == "PendingApproval":
                    for recipient_id in db.execute(text("""
                        SELECT user_account.UserID FROM dbo.AppUser user_account
                        JOIN dbo.Role role ON role.RoleID=user_account.RoleID
                        WHERE user_account.IsActive=1 AND role.IsActive=1
                          AND role.RoleCode IN ('WORKFORCE_MANAGER','PLATFORM_OWNER')
                    """)).scalars().all():
                        db.execute(text("""
                            IF NOT EXISTS (
                                SELECT 1 FROM dbo.Notification
                                WHERE UserID=:user_id AND ResourceType='WorkforceReuseAssessment'
                                  AND ResourceID=:resource_id AND IsRead=0
                            )
                            INSERT dbo.Notification
                                (NotificationID,UserID,NotificationType,Title,Body,ResourceType,
                                 ResourceID,CorrelationID,IsRead,CreatedAtUtc)
                            VALUES
                                (:notification_id,:user_id,'WORKFORCE_REUSE_REVIEW',
                                 'Workforce reuse review required',
                                 'A workforce reuse or upskill plan is awaiting Workforce Manager review.',
                                 'WorkforceReuseAssessment',:resource_id,:correlation_id,0,:created_at)
                        """), {
                            "notification_id": uuid.uuid4(), "user_id": recipient_id,
                            "resource_id": str(persisted_assessment["AssessmentID"]), "correlation_id": uuid.uuid4(),
                            "created_at": now,
                        })

            if reusable:
                continue
            request_id = uuid.uuid4()
            db.execute(text("""
                INSERT WorkforceRequest
                    (WorkforceRequestID, ProjectID, TaskID, RoleCode, RequestReason,
                     Status, RequestedBy, RequestedAtUtc)
                VALUES
                    (:request_id, :project_id, :task_id, :role_code, :reason,
                     'PendingApproval', :requested_by, :requested_at)
            """), {
                "request_id": request_id,
                "project_id": project_id,
                "task_id": task_id,
                "role_code": role_code,
                "reason": f"No active or provisioning agent reached the 50% reuse threshold for {profile['PositionName']}.",
                "requested_by": requirement.CreatedBy,
                "requested_at": now,
            })
            for recipient_id in db.execute(text("""
                SELECT u.UserID FROM AppUser u JOIN Role r ON r.RoleID = u.RoleID
                WHERE u.IsActive = 1 AND r.IsActive = 1 AND r.RoleCode IN ('APPROVER','WORKFORCE_MANAGER','PLATFORM_OWNER','OWNER','SUPER_ADMIN')
            """)).scalars().all():
                db.execute(text("""
                    INSERT Notification
                        (NotificationID, UserID, NotificationType, Title, Body, ResourceType,
                         ResourceID, CorrelationID, IsRead, CreatedAtUtc)
                    VALUES
                        (:notification_id, :user_id, 'WORKFORCE_REVIEW', 'Workforce review required',
                         'A project has an unfilled role that requires a governed recruiting decision.',
                         'WorkforceRequest', :resource_id, :correlation_id, 0, :created_at)
                """), {
                    "notification_id": uuid.uuid4(), "user_id": recipient_id,
                    "resource_id": str(request_id), "correlation_id": uuid.uuid4(), "created_at": now,
                })
            db.execute(text("""
                INSERT AuditLog
                    (CorrelationID, ActorType, ActorID, Action, ResourceType, ResourceID, Outcome, Details)
                VALUES
                    (:correlation_id, 'System', 'workforce-planner', 'WorkforceRequestCreated',
                     'WorkforceRequest', :resource_id, 'Success', :details)
            """), {
                "correlation_id": uuid.uuid4(), "resource_id": str(request_id),
                "details": '{"status":"PendingApproval","reason_recorded":false}',
            })
            created_requests += 1

        return {
            "project_id": str(project_id),
            "project_status": project_status,
            "task_count": len(tasks),
            "assigned_task_count": assigned_count,
            "unfilled_role_count": len({role_code for role_code, _task_id in requested_roles}),
            "new_workforce_requests": created_requests,
            "upskill_candidates": upskill_candidate_count,
            "calendar_dates": None,
            "message": "Planning only. Calendar dates require a confirmed start date and qualified capacity.",
        }

    @staticmethod
    def assign_request_to_agent(db, workforce_request, agent_id, decision_by, reason):
        profile = db.execute(text("""
            SELECT RoleCode, RequiredSkillsJson, PositionName
            FROM WorkforceRoleProfile WHERE RoleCode = :role_code AND Status = 'Active'
        """), {"role_code": workforce_request["RoleCode"]}).mappings().first()
        agent = db.execute(text("""
            SELECT AgentID, AgentType, WorkforceRoleCode, Status, CurrentWorkload, ConcurrentTaskLimit
            FROM Agent WHERE AgentID = :agent_id
        """), {"agent_id": agent_id}).mappings().first()
        if (not profile or not agent or agent["Status"] != "Active"
                or agent["AgentType"] == "Executive"
                or agent["WorkforceRoleCode"] != workforce_request["RoleCode"]):
            raise HTTPException(status_code=409, detail="Selected agent is not an active candidate for this workforce role")
        active_assignments = db.execute(text("""
            SELECT COUNT(*) FROM TaskAssignment
            WHERE AgentID=:agent_id AND ReleasedAtUtc IS NULL AND Status='Active'
        """), {"agent_id": agent_id}).scalar_one()
        if int(active_assignments) >= int(agent["ConcurrentTaskLimit"] or 1) or float(agent["CurrentWorkload"] or 0) >= 100:
            raise HTTPException(status_code=409, detail="Selected agent has no available task capacity")
        skills = {
            row["SkillName"]: int(row["Proficiency"])
            for row in db.execute(text("""
                SELECT s.Name AS SkillName, MAX(ags.Proficiency) AS Proficiency
                FROM AgentSkill ags JOIN Skill s ON s.SkillID = ags.SkillID
                WHERE ags.AgentID = :agent_id AND ags.Status = 'Active'
                GROUP BY s.Name
            """), {"agent_id": agent_id}).mappings().all()
        }
        if not agent_meets_profile(dict(profile), skills):
            raise HTTPException(status_code=409, detail="Selected agent does not meet the role's verified skill requirements")
        if not REQUIRED_AGENT_CERTIFICATIONS.issubset(self.latest_passed_evaluation_types(db, agent_id)):
            raise HTTPException(status_code=409, detail="Selected agent is missing current required certifications")

        now = _now()
        tasks = db.execute(text("""
            SELECT TaskID FROM Task WHERE ProjectID = :project_id AND RequiredRoleCode = :role_code
              AND Status = 'Planned' AND AssignedAgentID IS NULL
            ORDER BY PlannedSequence, CreatedAtUtc
        """), {"project_id": workforce_request["ProjectID"], "role_code": workforce_request["RoleCode"]}).scalars().all()
        for task_id in tasks[:1]:
            db.execute(text("UPDATE Task SET AssignedAgentID = :agent_id WHERE TaskID = :task_id"), {
                "agent_id": agent_id, "task_id": task_id,
            })
            db.execute(text("""
                INSERT TaskAssignment(TaskAssignmentID, TaskID, AgentID, AssignedAtUtc, Status)
                VALUES (:assignment_id, :task_id, :agent_id, :assigned_at, 'Active')
            """), {"assignment_id": uuid.uuid4(), "task_id": task_id, "agent_id": agent_id, "assigned_at": now})
        if workforce_request["RoleCode"] == "DELIVERY_LEAD":
            db.execute(text("""
                IF NOT EXISTS (SELECT 1 FROM ProjectAgent WHERE ProjectID=:project_id AND AgentID=:agent_id)
                INSERT ProjectAgent(ProjectID, AgentID, ProjectRole, AssignedAtUtc)
                VALUES (:project_id, :agent_id, 'Delivery Lead', :assigned_at)
            """), {"project_id": workforce_request["ProjectID"], "agent_id": agent_id, "assigned_at": now})
        db.execute(text("""
            UPDATE WorkforceRequest SET Status='Filled', FilledAgentID=:agent_id,
                DecisionBy=:decision_by, DecisionReason=:reason, DecisionAtUtc=:decided_at
            WHERE WorkforceRequestID=:request_id
        """), {
            "agent_id": agent_id, "decision_by": decision_by, "reason": reason,
            "decided_at": now, "request_id": workforce_request["WorkforceRequestID"],
        })
        return len(tasks)
