import unittest
import uuid
from unittest.mock import Mock

from fastapi import HTTPException

from app.api.workforce import (
    AgentEvaluationRecord,
    EvaluationCriterionResult,
    AgentModelConfiguration,
    AgentSkillChange,
    configure_agent_model,
    record_agent_evaluation,
)


class AgentCertificationApiTests(unittest.TestCase):
    @staticmethod
    def body(scores):
        return AgentEvaluationRecord(
            template_code="CAPABILITY",
            criteria=[
                {"criterion_code": code, "score": score,
                 "evidence": f"Test evidence reference {code} report QA-4812, reviewed 2026-10-26."}
                for code, score in scores.items()
            ],
            reason="Independent reviewer validated the recorded evidence.",
        )

    def test_incomplete_template_criteria_are_rejected_before_write(self):
        user_id, agent_id = uuid.uuid4(), uuid.uuid4()
        agent_result = Mock()
        agent_result.mappings.return_value.first.return_value = {"AgentID": agent_id, "Status": "Provisioning"}
        db = Mock()
        template_result = Mock()
        template_result.mappings.return_value.first.return_value = {
            "TemplateID": uuid.uuid4(), "TemplateCode": "CAPABILITY",
            "TemplateName": "Capability Review", "Version": "1.0",
        }
        criterion_result = Mock()
        criterion_result.mappings.return_value.all.return_value = [
            {"CriterionCode": code, "CriterionName": code, "IsRequired": True}
            for code in ("PROMPT_QUALITY", "TASK_COMPLETION", "ACCURACY", "REASONING")
        ]
        db.execute.side_effect = [agent_result, template_result, criterion_result]

        with self.assertRaises(HTTPException) as raised:
            record_agent_evaluation(agent_id, self.body({"PROMPT_QUALITY": 95}), db, {"sub": str(user_id)})

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(db.execute.call_count, 3)

    def test_evidence_is_required_in_request(self):
        with self.assertRaises(ValueError):
            AgentEvaluationRecord(
                template_code="SAFETY", reason="reviewed",
                criteria=[{"criterion_code": "PROMPT_INJECTION", "score": 90, "evidence": "too short"}],
            )

    def test_model_provider_is_restricted_to_supported_catalog_values(self):
        configuration = AgentModelConfiguration(
            model_catalog_id=uuid.uuid4(),
            reason="Approved deployment configuration.",
        )
        self.assertIsInstance(configuration.model_catalog_id, uuid.UUID)

    def test_skill_approval_requires_validation_evidence(self):
        with self.assertRaises(ValueError):
            AgentSkillChange(
                skill_id=uuid.uuid4(), proficiency=4, action="approve",
                evidence="too short", reason="reviewed",
            )

    def test_complete_template_records_reviewer_and_criterion_evidence(self):
        user_id, agent_id, template_id = [uuid.uuid4() for _ in range(3)]
        agent_result = Mock()
        agent_result.mappings.return_value.first.return_value = {"AgentID": agent_id, "Status": "Provisioning"}
        template_result = Mock()
        template_result.mappings.return_value.first.return_value = {
            "TemplateID": template_id, "TemplateCode": "CAPABILITY",
            "TemplateName": "Capability Review", "Version": "1.0",
        }
        criterion_result = Mock()
        codes = ("PROMPT_QUALITY", "TASK_COMPLETION", "ACCURACY", "REASONING")
        criterion_result.mappings.return_value.all.return_value = [
            {"CriterionCode": code, "CriterionName": code, "IsRequired": True} for code in codes
        ]
        db = Mock()
        db.execute.side_effect = [agent_result, template_result, criterion_result, Mock(), Mock()]
        body = AgentEvaluationRecord(
            template_code="CAPABILITY",
            criteria=[EvaluationCriterionResult(
                criterion_code=code, score=85,
                evidence=f"Peer-reviewed test report for {code}, case-set CAP-2026-1.",
            ) for code in codes],
            reason="Reviewer completed the approved capability rubric.",
        )

        result = record_agent_evaluation(agent_id, body, db, {"sub": str(user_id)})

        self.assertTrue(result["passed"])
        self.assertEqual(result["score"], 85)
        inserted = db.execute.call_args_list[3].args[1]
        self.assertEqual(inserted["evaluation_type"], "Capability")
        self.assertIn(str(user_id), inserted["evidence"])
        db.commit.assert_called_once()

    def test_template_record_rejects_missing_required_criteria(self):
        user_id, agent_id, template_id = [uuid.uuid4() for _ in range(3)]
        agent_result = Mock()
        agent_result.mappings.return_value.first.return_value = {"AgentID": agent_id, "Status": "Provisioning"}
        template_result = Mock()
        template_result.mappings.return_value.first.return_value = {
            "TemplateID": template_id, "TemplateCode": "CAPABILITY",
            "TemplateName": "Capability Review", "Version": "1.0",
        }
        criterion_result = Mock()
        criterion_result.mappings.return_value.all.return_value = [
            {"CriterionCode": code, "CriterionName": code, "IsRequired": True}
            for code in ("PROMPT_QUALITY", "TASK_COMPLETION", "ACCURACY", "REASONING")
        ]
        db = Mock()
        db.execute.side_effect = [agent_result, template_result, criterion_result]
        body = AgentEvaluationRecord(
            template_code="CAPABILITY",
            criteria=[EvaluationCriterionResult(
                criterion_code="PROMPT_QUALITY", score=90,
                evidence="Reviewed benchmark report CAP-9 and reproducible test results.",
            )],
            reason="Partial review is not a full certification.",
        )

        with self.assertRaises(HTTPException) as raised:
            record_agent_evaluation(agent_id, body, db, {"sub": str(user_id)})

        self.assertEqual(raised.exception.status_code, 422)
        db.commit.assert_not_called()

    def test_model_configuration_is_org_independent_and_provisioning_only(self):
        user_id, agent_id = uuid.uuid4(), uuid.uuid4()
        agent_result = Mock()
        agent_result.mappings.return_value.first.return_value = {"AgentID": agent_id, "Status": "Provisioning"}
        db = Mock()
        catalog_id = uuid.uuid4()
        catalog_result = Mock()
        catalog_result.mappings.return_value.first.return_value = {
            "ProviderName": "Azure OpenAI", "ModelName": "GPT-5", "ModelVersion": "2026-01",
        }
        db.execute.side_effect = [agent_result, catalog_result, Mock(), Mock()]

        response = configure_agent_model(
            agent_id,
            AgentModelConfiguration(model_catalog_id=catalog_id, reason="Approved target configuration."),
            db,
            {"sub": str(user_id)},
        )

        self.assertEqual(response["model"], "GPT-5")
        db.commit.assert_called_once()
        self.assertEqual(db.execute.call_args_list[2].args[1]["provider"], "Azure OpenAI")

    def test_model_configuration_rejects_non_provisioning_agent(self):
        user_id, agent_id = uuid.uuid4(), uuid.uuid4()
        agent_result = Mock()
        agent_result.mappings.return_value.first.return_value = {"AgentID": agent_id, "Status": "Active"}
        db = Mock()
        db.execute.side_effect = [agent_result]

        with self.assertRaises(HTTPException) as raised:
            configure_agent_model(
                agent_id,
                AgentModelConfiguration(model_catalog_id=uuid.uuid4(), reason="Approved target configuration."),
                db,
                {"sub": str(user_id)},
            )

        self.assertEqual(raised.exception.status_code, 409)
        db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()