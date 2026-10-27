import unittest
import uuid
from unittest.mock import Mock

from app.api.workforce import (
    WorkforceReuseAssignment,
    WorkforceReuseDecision,
    assign_approved_reuse_candidate,
    decide_workforce_reuse_assessment,
)
from app.services.workforce_planner import WorkforcePlanner, assess_workforce_match


class SingleOrganizationWorkforceTests(unittest.TestCase):
    def test_reuse_priority_bands_and_upskill_plan_details(self):
        profile = {"RequiredSkillsJson": '[{"name":"PowerBIDevelopment","minimum_proficiency":4}]'}
        active_agent = {
            "Status": "Active", "CurrentWorkload": 20,
            "ConcurrentTaskLimit": 3, "ActiveAssignments": 1,
        }
        certifications = {"Capability", "Safety", "Security", "Governance"}

        exact = assess_workforce_match(profile, active_agent, {"PowerBIDevelopment": 4}, certifications)
        upskill = assess_workforce_match(profile, active_agent, {"PowerBIDevelopment": 2}, certifications)
        request = assess_workforce_match(profile, active_agent, {"PowerBIDevelopment": 1}, certifications)
        strong = assess_workforce_match(
            {"RequiredSkillsJson": '[{"name":"SkillA","minimum_proficiency":5},{"name":"SkillB","minimum_proficiency":5}]'},
            active_agent, {"SkillA": 5, "SkillB": 3}, certifications,
        )

        self.assertEqual((exact["match_score"], exact["classification"]), (100, "Ready Candidate"))
        self.assertEqual((strong["match_score"], strong["classification"]), (80, "Strong Candidate"))
        self.assertEqual((upskill["match_score"], upskill["classification"]), (50, "Upskill Candidate"))
        self.assertEqual((request["match_score"], request["classification"]), (25, "Workforce Request"))
        self.assertEqual(upskill["skill_plan"][0]["required_skill"], "PowerBIDevelopment")
        self.assertEqual(upskill["skill_plan"][0]["current_skill"], 2)
        self.assertEqual(upskill["skill_plan"][0]["gap"], 2)
        self.assertEqual(upskill["estimated_readiness_days"], 10)

    def test_certification_and_capacity_are_readiness_gates_not_skill_match_score(self):
        profile = {"RequiredSkillsJson": '[{"name":"PowerBIDevelopment","minimum_proficiency":4}]'}
        result = assess_workforce_match(
            profile,
            {"Status": "Provisioning", "CurrentWorkload": 100, "ConcurrentTaskLimit": 1, "ActiveAssignments": 1},
            {"PowerBIDevelopment": 4},
            set(),
        )

        self.assertEqual(result["match_score"], 100)
        self.assertFalse(result["capacity_available"])
        self.assertIn("Capability", result["missing_certifications"])
        self.assertEqual(result["skill_plan"][0]["gap"], 0)

    def test_manager_approval_records_decision_without_changing_agent(self):
        assessment_id = uuid.uuid4()
        selected = {"AssessmentID": assessment_id, "MatchScore": 75, "AssessmentStatus": "PendingApproval"}
        first_result = Mock()
        first_result.mappings.return_value.first.return_value = selected
        database = Mock()
        database.execute.side_effect = [first_result, Mock(), Mock()]

        result = decide_workforce_reuse_assessment(
            assessment_id,
            WorkforceReuseDecision(action="approve", reason="Approved after capacity review."),
            database,
            {"sub": "manager-user"},
        )

        self.assertEqual(result["status"], "Approved")
        self.assertFalse(result["agent_changed"])
        executed_sql = [str(call.args[0]) for call in database.execute.call_args_list]
        self.assertTrue(any("UPDATE dbo.WorkforceReuseAssessment" in query for query in executed_sql))
        self.assertFalse(any("UPDATE dbo.Agent" in query or "UPDATE dbo.AgentSkill" in query for query in executed_sql))

    def test_approved_reuse_assignment_requires_readiness_and_does_not_activate(self):
        assessment_id, agent_id, project_id, task_id = (uuid.uuid4() for _ in range(4))

        def mapping_result(row):
            result = Mock()
            result.mappings.return_value.first.return_value = row
            return result

        assessment = {
            "AssessmentID": assessment_id, "ProjectID": project_id, "TaskID": task_id,
            "RoleCode": "BUSINESS_ANALYST", "AgentID": agent_id,
            "AssessmentStatus": "Approved", "Classification": "Strong Candidate",
        }
        agent = {
            "AgentID": agent_id, "AgentType": "Specialist", "Status": "Active",
            "CurrentWorkload": 25, "ConcurrentTaskLimit": 3,
        }
        capacity_result = Mock()
        capacity_result.scalar_one.return_value = 1
        profile_result = mapping_result({"RequiredSkillsJson": '[{"name":"RequirementAnalysis","minimum_proficiency":4}]'})
        skills_result = Mock()
        skills_result.mappings.return_value.all.return_value = [{"Name": "RequirementAnalysis", "Proficiency": 4}]
        certification_result = Mock()
        certification_result.all.return_value = [(name,) for name in ("Capability", "Safety", "Security", "Governance")]
        task_result = mapping_result({"TaskID": task_id, "ProjectID": project_id, "AssignedAgentID": None})
        database = Mock()
        database.execute.side_effect = [
            mapping_result(assessment), mapping_result(agent), capacity_result,
            profile_result, skills_result, certification_result, task_result,
            Mock(), Mock(), Mock(), Mock(),
        ]

        result = assign_approved_reuse_candidate(
            assessment_id,
            WorkforceReuseAssignment(reason="Assign after confirming capacity and certification."),
            database,
            {"sub": "manager-user"},
        )

        self.assertEqual(result["status"], "Assigned")
        self.assertFalse(result["activated"])
        executed_sql = [str(call.args[0]) for call in database.execute.call_args_list]
        self.assertTrue(any("UPDATE dbo.Task SET AssignedAgentID" in query for query in executed_sql))
        self.assertTrue(any("INSERT dbo.TaskAssignment" in query for query in executed_sql))
        self.assertFalse(any("UPDATE dbo.Agent" in query or "UPDATE dbo.AgentSkill" in query for query in executed_sql))

    def test_provisioning_uses_active_role_profile_without_org_catalog_rows(self):
        request_id = uuid.uuid4()
        role = {
            "RoleCode": "SOFTWARE_DEVELOPER",
            "PositionName": "Software Developer",
            "DepartmentName": "Technology",
            "Grade": "Senior",
            "JobDescription": "Build approved software changes.",
            "ResponsibilitiesJson": "[]",
            "RequiredSkillsJson": "[]",
            "MaxRecommendedAutonomy": 1,
        }
        profile_result = Mock()
        profile_result.mappings.return_value.first.return_value = role
        existing_role_result = Mock()
        existing_role_result.mappings.return_value.first.return_value = None
        existing_name_result = Mock()
        existing_name_result.first.return_value = None
        database = Mock()
        database.execute.side_effect = [
            profile_result,
            existing_role_result,
            existing_name_result,
            Mock(),
            Mock(),
        ]

        agent_id = WorkforcePlanner.provision_agent(
            database,
            {
                "ProvisionedAgentID": None,
                "Status": "Recruiting",
                "RoleCode": role["RoleCode"],
                "WorkforceRequestID": request_id,
            },
            uuid.uuid4(),
        )

        self.assertIsInstance(agent_id, uuid.UUID)
        role_query = str(database.execute.call_args_list[0].args[0])
        self.assertIn("FROM WorkforceRoleProfile", role_query)
        self.assertNotIn("JOIN Department", role_query)
        self.assertNotIn("JOIN Position", role_query)
        insert_params = database.execute.call_args_list[3].args[1]
        self.assertIsNone(insert_params["company_id"])
        self.assertIsNone(insert_params["department_id"])
        self.assertIsNone(insert_params["position_id"])

    def test_certified_candidates_need_latest_pass_for_all_required_evaluations(self):
        certified_id, incomplete_id = uuid.uuid4(), uuid.uuid4()
        rows = [
            {"AgentID": certified_id, "EvaluationType": name}
            for name in ("Capability", "Safety", "Security", "Governance")
        ] + [
            {"AgentID": incomplete_id, "EvaluationType": "Capability"},
            {"AgentID": incomplete_id, "EvaluationType": "Safety"},
            {"AgentID": incomplete_id, "EvaluationType": "Security"},
        ]
        result = Mock()
        result.mappings.return_value.all.return_value = rows
        database = Mock()
        database.execute.return_value = result

        self.assertEqual(WorkforcePlanner.certified_agent_ids(database), {certified_id})
        query = str(database.execute.call_args.args[0])
        self.assertIn("ROW_NUMBER() OVER(PARTITION BY AgentID,EvaluationType", query)
        self.assertIn("RowNumber=1 AND Passed=1", query)


if __name__ == "__main__":
    unittest.main()
