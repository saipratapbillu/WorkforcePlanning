import unittest
import uuid
from unittest.mock import Mock

from app.api.model_governance import ModelDecision, ModelProposal, decide_model, list_approved_models, propose_model


class ModelGovernanceTests(unittest.TestCase):
    def test_model_proposal_is_created_pending_and_requires_evidence(self):
        user_id = uuid.uuid4()
        no_provider = Mock()
        no_provider.mappings.return_value.first.return_value = None
        no_duplicate = Mock()
        no_duplicate.mappings.return_value.first.return_value = None
        db = Mock()
        db.execute.side_effect = [no_provider, Mock(), no_duplicate, Mock(), Mock()]
        body = ModelProposal(
            provider="Azure OpenAI", model="GPT-5", version="Enterprise-2026",
            reason="Submitted for enterprise security review.",
            evidence="Vendor contract and security review reference SEC-2026-91.",
        )

        result = propose_model(body, db, {"sub": str(user_id)})

        self.assertEqual(result["status"], "Pending")
        self.assertEqual(db.execute.call_args_list[3].args[1]["version"], "Enterprise-2026")
        self.assertIn("'Pending'", str(db.execute.call_args_list[3].args[0]))
        db.commit.assert_called_once()

    def test_catalog_listing_filters_to_approved_models(self):
        db = Mock()
        row = {"ModelName": "GPT-5", "ModelVersion": "Enterprise-2026", "Status": "Approved"}
        db.execute.return_value.mappings.return_value.all.return_value = [row]

        result = list_approved_models(db)

        self.assertEqual(result, [row])
        self.assertIn("m.Status='Approved'", str(db.execute.call_args.args[0]))
        self.assertIn("p.Status='Active'", str(db.execute.call_args.args[0]))

    def test_approval_decision_updates_catalog_and_records_reviewer_evidence(self):
        model_id, reviewer_id = uuid.uuid4(), uuid.uuid4()
        locked_item = Mock()
        locked_item.mappings.return_value.first.return_value = {
            "ModelCatalogID": model_id, "Status": "Pending", "ProviderStatus": "Active",
            "CreatedByUserID": uuid.uuid4(),
        }
        db = Mock()
        db.execute.side_effect = [locked_item, Mock(), Mock(), Mock(), Mock()]
        body = ModelDecision(
            decision="Approved", reason="Enterprise controls reviewed.",
            evidence="Security attestation and procurement approval record MODEL-42.",
        )

        result = decide_model(model_id, body, db, {"sub": str(reviewer_id)})

        self.assertEqual(result["status"], "Approved")
        self.assertEqual(db.execute.call_args_list[2].args[1]["decision"], "Approved")
        self.assertEqual(db.execute.call_args_list[2].args[1]["reviewer"], str(reviewer_id))
        db.commit.assert_called_once()

    def test_model_proposer_cannot_approve_own_proposal(self):
        model_id, user_id = uuid.uuid4(), uuid.uuid4()
        locked_item = Mock()
        locked_item.mappings.return_value.first.return_value = {
            "ModelCatalogID": model_id, "Status": "Pending", "ProviderStatus": "Active",
            "CreatedByUserID": user_id,
        }
        db = Mock()
        db.execute.return_value = locked_item
        body = ModelDecision(
            decision="Approved", reason="Review completed and verified.",
            evidence="Security and procurement reference MODEL-72.",
        )

        with self.assertRaises(Exception) as raised:
            decide_model(model_id, body, db, {"sub": str(user_id)})

        self.assertEqual(getattr(raised.exception, "status_code", None), 403)
        self.assertEqual(db.execute.call_count, 1)
        db.commit.assert_not_called()

    def test_model_proposal_and_decision_require_evidence(self):
        with self.assertRaises(ValueError):
            ModelProposal(provider="Google", model="Gemini", version="Enterprise", reason="short", evidence="short")
        with self.assertRaises(ValueError):
            ModelDecision(decision="Approved", reason="reviewed", evidence="short")


if __name__ == "__main__":
    unittest.main()