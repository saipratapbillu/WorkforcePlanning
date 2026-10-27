import unittest
import uuid
from unittest.mock import Mock

from fastapi import HTTPException

from app.api.runtime import _worker_agent
from app.services.agent_runtime import (
    AgentRuntime,
    can_retry,
    hash_worker_token,
    make_worker_token,
    structural_output_passes,
    worker_token_matches,
)
from app.services.workforce_planner import WorkforcePlanner


class AgentRuntimeTests(unittest.TestCase):
    def test_activation_readiness_requires_active_role_skills(self):
        profile_result = Mock()
        profile_result.mappings.return_value.first.return_value = {
            "RequiredSkillsJson": '[{"name":"SecurityReview","minimum_proficiency":4}]'
        }
        skills_result = Mock()
        skills_result.mappings.return_value.all.return_value = []
        evaluation_result = Mock()
        evaluation_result.all.return_value = [("Capability",), ("Safety",), ("Security",), ("Governance",)]
        db = Mock()
        db.execute.side_effect = [evaluation_result, profile_result, skills_result]
        agent = {
            "AgentID": uuid.uuid4(),
            "Status": "Provisioning",
            "ModelProvider": "Azure OpenAI",
            "Model": "approved-model",
            "ModelVersion": "2026-01",
            "WorkforceRoleCode": "SECURITY_ENGINEER",
        }

        blockers = WorkforcePlanner.agent_readiness_blockers(db, agent)

        self.assertEqual(blockers, ["required skills are not Active at the role minimum proficiency"])

    def test_activation_readiness_passes_only_with_active_minimum_skill(self):
        profile_result = Mock()
        profile_result.mappings.return_value.first.return_value = {
            "RequiredSkillsJson": '[{"name":"SecurityReview","minimum_proficiency":4}]'
        }
        skills_result = Mock()
        skills_result.mappings.return_value.all.return_value = [{"Name": "SecurityReview", "Proficiency": 4}]
        evaluation_result = Mock()
        evaluation_result.all.return_value = [("Capability",), ("Safety",), ("Security",), ("Governance",)]
        db = Mock()
        db.execute.side_effect = [evaluation_result, profile_result, skills_result]
        agent = {
            "AgentID": uuid.uuid4(),
            "Status": "Provisioning",
            "ModelProvider": "Azure OpenAI",
            "Model": "approved-model",
            "ModelVersion": "2026-01",
            "WorkforceRoleCode": "SECURITY_ENGINEER",
        }

        self.assertEqual(WorkforcePlanner.agent_readiness_blockers(db, agent), [])

    def test_worker_tokens_are_random_and_hash_verifiable(self):
        first = make_worker_token()
        second = make_worker_token()

        self.assertNotEqual(first, second)
        self.assertEqual(len(hash_worker_token(first)), 64)
        self.assertTrue(worker_token_matches(first, hash_worker_token(first)))
        self.assertFalse(worker_token_matches(second, hash_worker_token(first)))

    def test_retry_budget_is_bounded_by_max_attempts(self):
        self.assertTrue(can_retry(0, 3))
        self.assertTrue(can_retry(2, 3))
        self.assertFalse(can_retry(3, 3))
        self.assertFalse(can_retry(4, 3))

    def test_structural_output_check_does_not_claim_content_quality(self):
        self.assertTrue(structural_output_passes("report.txt", "content"))
        self.assertFalse(structural_output_passes(" ", "content"))
        self.assertFalse(structural_output_passes("report.txt", "  "))
        self.assertFalse(structural_output_passes("report.txt", "x" * 500_001))

    def test_execution_fails_closed_without_trusted_adapter(self):
        with self.assertRaisesRegex(RuntimeError, "No trusted agent execution adapter"):
            AgentRuntime().execute({"task_id": "not-executed"})

    def test_configured_adapter_is_called_explicitly(self):
        class TrustedExecutor:
            def execute(self, task_payload):
                return {"accepted": task_payload["task_id"]}

        result = AgentRuntime(TrustedExecutor()).execute({"task_id": "task-1"})

        self.assertEqual(result, {"accepted": "task-1"})

    def test_worker_identity_is_derived_from_stored_credential(self):
        token = make_worker_token()
        agent_id = uuid.uuid4()
        query_result = Mock()
        query_result.mappings.return_value.first.return_value = {
            "AgentID": agent_id,
            "TokenHash": hash_worker_token(token),
        }
        db = Mock()
        db.execute.side_effect = [query_result, Mock()]

        authenticated_agent_id = _worker_agent(f"Bearer {token}", db)

        self.assertEqual(authenticated_agent_id, agent_id)
        self.assertEqual(db.execute.call_count, 2)

    def test_invalid_worker_token_is_rejected_without_touching_last_used(self):
        query_result = Mock()
        query_result.mappings.return_value.first.return_value = None
        db = Mock()
        db.execute.return_value = query_result

        with self.assertRaises(HTTPException) as raised:
            _worker_agent("Bearer invalid", db)

        self.assertEqual(raised.exception.status_code, 401)
        db.execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
