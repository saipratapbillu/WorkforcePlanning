"""Mocked unit tests for review governance.

These verify branching and authorization logic only. They do NOT prove SQL Server
locking or concurrency; see tests/integration/ for that (requires a live database).
"""
import unittest
import uuid
from unittest.mock import Mock

from fastapi import HTTPException

from app.api.runtime import router
from app.security.middleware import forbidden_for_role
from app.security.roles import has_role
from app.services import agent_runtime as rt


def _result(**kw):
    r = Mock()
    r.mappings.return_value.first.return_value = kw.get("first")
    r.scalar_one_or_none.return_value = kw.get("scalar")
    return r


class IndependenceTests(unittest.TestCase):
    def test_non_reviewer_role_denied(self):
        db = Mock()
        db.execute.return_value = _result(scalar="WORKFORCE_MANAGER")
        with self.assertRaises(HTTPException) as e:
            rt._assert_independent(db, uuid.uuid4(), uuid.uuid4())
        self.assertEqual(e.exception.status_code, 403)

    def test_null_creator_fails_closed(self):
        db = Mock()
        db.execute.side_effect = [
            _result(scalar="RUNTIME_REVIEWER"),
            _result(first={"TaskCreator": None, "ProjectCreator": uuid.uuid4(), "RequirementCreator": uuid.uuid4()}),
        ]
        with self.assertRaises(HTTPException) as e:
            rt._assert_independent(db, uuid.uuid4(), uuid.uuid4())
        self.assertEqual(e.exception.status_code, 403)

    def test_creator_cannot_review(self):
        me = uuid.uuid4()
        db = Mock()
        db.execute.side_effect = [
            _result(scalar="RUNTIME_REVIEWER"),
            _result(first={"TaskCreator": uuid.uuid4(), "ProjectCreator": me, "RequirementCreator": uuid.uuid4()}),
        ]
        with self.assertRaises(HTTPException):
            rt._assert_independent(db, uuid.uuid4(), me)

    def test_unrelated_reviewer_allowed(self):
        db = Mock()
        db.execute.side_effect = [
            _result(scalar="RUNTIME_REVIEWER"),
            _result(first={"TaskCreator": uuid.uuid4(), "ProjectCreator": uuid.uuid4(), "RequirementCreator": uuid.uuid4()}),
        ]
        rt._assert_independent(db, uuid.uuid4(), uuid.uuid4())


class ReviewDecisionTests(unittest.TestCase):
    def _execution(self, **over):
        base = {"ExecutionID": uuid.uuid4(), "QueueID": uuid.uuid4(), "TaskID": uuid.uuid4(), "AgentID": uuid.uuid4(),
                "Status": "Review", "QueueStatus": "Review", "AttemptCount": 1, "MaxAttempts": 3, "ProjectID": uuid.uuid4(),
                "RequiredRoleCode": "X", "RiskLevel": "Low", "ReviewKey": None, "ReviewDecision": None,
                "ReviewOwnerUserID": None, "ReviewLeaseExpiresAtUtc": None}
        base.update(over)
        return base

    def test_replay_same_decision_is_idempotent(self):
        db = Mock()
        db.execute.return_value = _result(first=self._execution(Status="Completed", ReviewKey="key-12345", ReviewDecision="Approved"))
        out = rt.review_execution(db, uuid.uuid4(), uuid.uuid4(), True, "ok", review_key="key-12345", require_lease=True)
        self.assertTrue(out["idempotent_replay"])

    def test_replay_different_decision_conflicts(self):
        db = Mock()
        db.execute.return_value = _result(first=self._execution(Status="Completed", ReviewKey="key-12345", ReviewDecision="Approved"))
        with self.assertRaises(HTTPException) as e:
            rt.review_execution(db, uuid.uuid4(), uuid.uuid4(), False, "no", review_key="key-12345", require_lease=True)
        self.assertEqual(e.exception.status_code, 409)

    def test_lease_owned_by_other_reviewer_rejected(self):
        db = Mock()
        db.execute.return_value = _result(first=self._execution(
            ReviewOwnerUserID=uuid.uuid4(), ReviewLeaseExpiresAtUtc=rt.utcnow().replace(year=2999)))
        with self.assertRaises(HTTPException) as e:
            rt.review_execution(db, uuid.uuid4(), uuid.uuid4(), True, "ok", review_key="key-12345", require_lease=True)
        self.assertEqual(e.exception.status_code, 409)

    def test_expired_lease_rejected(self):
        me = uuid.uuid4()
        db = Mock()
        db.execute.return_value = _result(first=self._execution(
            ReviewOwnerUserID=me, ReviewLeaseExpiresAtUtc=rt.utcnow().replace(year=2000)))
        with self.assertRaises(HTTPException) as e:
            rt.review_execution(db, uuid.uuid4(), me, True, "ok", review_key="key-12345", require_lease=True)
        self.assertEqual(e.exception.status_code, 409)

    def test_review_package_is_not_visible_without_the_active_lease(self):
        db = Mock()
        db.execute.return_value = _result(first=None)
        with self.assertRaises(HTTPException) as e:
            rt.get_review_package(db, uuid.uuid4(), uuid.uuid4())
        self.assertEqual(e.exception.status_code, 404)
        db.execute.assert_called_once()

    def test_claim_review_skips_unknown_or_self_created_provenance(self):
        reviewer_id = uuid.uuid4()
        db = Mock()
        db.execute.return_value = _result(first=None)

        result = rt.claim_review(db, reviewer_id)

        self.assertIsNone(result)
        statement = str(db.execute.call_args.args[0])
        self.assertIn("CreatedByUserID IS NOT NULL", statement)
        self.assertIn("CreatedByUserID<>:reviewer_id", statement)
        self.assertEqual(db.execute.call_args.args[1]["reviewer_id"], reviewer_id)


class RouteAuthorizationTests(unittest.TestCase):
    def test_reviewer_role_is_not_an_admin_alias(self):
        for role in ("PLATFORM_OWNER", "WORKFORCE_MANAGER", "ADMIN", "OWNER", "SUPER_ADMIN", "EXECUTIVE", "APPROVER", "BUSINESS_USER"):
            self.assertFalse(has_role("RUNTIME_REVIEWER", role), role)
            self.assertFalse(has_role(role, "RUNTIME_REVIEWER"), role)

    def test_middleware_confines_reviewer_to_review_paths(self):
        self.assertFalse(forbidden_for_role("/runtime/reviews/claim", "RUNTIME_REVIEWER"))
        for path in ("/runtime/defects", "/runtime/reap-expired-leases", "/runtime/worker/claim", "/runtime/enqueue", "/agents", "/workforce-center"):
            self.assertTrue(forbidden_for_role(path, "RUNTIME_REVIEWER"), path)
        for role in ("PLATFORM_OWNER", "WORKFORCE_MANAGER", "BUSINESS_USER"):
            self.assertTrue(forbidden_for_role("/runtime/reviews/claim", role), role)
        self.assertTrue(forbidden_for_role("/runtime/reviews/claim", "RUNTIME_REAPER"))

    def test_legacy_review_route_removed(self):
        paths = {r.path for r in router.routes}
        self.assertNotIn("/runtime/executions/{execution_id}/review", paths)
        self.assertIn("/runtime/reviews/{execution_id}/decision", paths)
        self.assertIn("/runtime/worker/executions/{execution_id}/context", paths)


if __name__ == "__main__":
    unittest.main()
