import unittest
import uuid
from unittest.mock import Mock

from fastapi import HTTPException

from app.api.operations import ModelRetirement, operational_readiness, retire_model


class OperationsDashboardTests(unittest.TestCase):
    def test_readiness_scorecard_reports_missing_operational_layers(self):
        users_result = Mock()
        users_result.mappings.return_value.one.return_value = {"Ready": 4, "Total": 4}
        agents_result = Mock()
        agents_result.mappings.return_value.one.return_value = {"Ready": 0, "Total": 56}
        model_result = Mock()
        model_result.scalar_one.return_value = 0
        assignments_result = Mock()
        assignments_result.scalar_one.return_value = 0
        executions_result = Mock()
        executions_result.scalar_one.return_value = 0
        deliverables_result = Mock()
        deliverables_result.scalar_one.return_value = 0
        policies_result = Mock()
        policies_result.scalar_one.return_value = 0
        db = Mock()
        db.execute.side_effect = [users_result, agents_result, model_result,
                                  assignments_result, executions_result, deliverables_result, policies_result]

        result = operational_readiness(db)

        self.assertEqual(result["status"], "not_operational")
        self.assertEqual(result["scorecard"]["users_ready"], {"ready": 4, "total": 4})
        self.assertEqual(result["scorecard"]["agents_ready"]["ready"], 0)
        self.assertEqual(result["readiness_percent"], 17)
        self.assertFalse(result["rls_enabled"])
        self.assertFalse(result["execution_adapter_configured"])

    def test_retirement_is_blocked_while_agent_uses_model(self):
        model_id, agent_id = uuid.uuid4(), uuid.uuid4()
        model_result = Mock()
        model_result.mappings.return_value.first.return_value = {
            "ModelCatalogID": model_id, "Status": "Approved", "ProviderCode": "OPENAI",
            "ProviderName": "OpenAI", "ModelName": "Model X", "ModelVersion": "v1",
        }
        usage_result = Mock()
        usage_result.mappings.return_value.first.return_value = {
            "AgentID": agent_id, "AgentName": "Provisioned Agent", "Status": "Provisioning",
        }
        db = Mock()
        db.execute.side_effect = [model_result, usage_result]

        with self.assertRaises(HTTPException) as raised:
            retire_model(model_id, ModelRetirement(
                reason="Provider model is being withdrawn.",
                evidence="Vendor deprecation notice reference VENDOR-2026-12.",
            ), db, {"sub": str(uuid.uuid4())})

        self.assertEqual(raised.exception.status_code, 409)
        db.commit.assert_not_called()

    def test_retirement_is_blocked_by_assignment_reference(self):
        model_id = uuid.uuid4()
        model_result = Mock()
        model_result.mappings.return_value.first.return_value = {
            "ModelCatalogID": model_id, "Status": "Approved", "ProviderCode": "OPENAI",
            "ProviderName": "OpenAI", "ModelName": "Model X", "ModelVersion": "v1",
        }
        no_agent_result = Mock()
        no_agent_result.mappings.return_value.first.return_value = None
        usage_result = Mock()
        usage_result.mappings.return_value.one.return_value = {
            "ActiveAssignmentCount": 1, "RunningExecutionCount": 0,
        }
        db = Mock()
        db.execute.side_effect = [model_result, no_agent_result, usage_result]

        with self.assertRaises(HTTPException) as raised:
            retire_model(model_id, ModelRetirement(
                reason="Retirement is under governed review.",
                evidence="Assignment impact evidence reference CHANGE-2026-09.",
            ), db, {"sub": str(uuid.uuid4())})

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["active_assignments"], 1)
        db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
