"""Opt-in SQL Server integration tests against a marked synthetic database.

The test identity, database marker, explicit authorization flags, complete
fixture manifest, and row-state restoration are required before tests execute.
"""

import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.services.agent_runtime import (
    claim_next_task,
    claim_review,
    reap_expired_leases,
    review_execution,
    submit_output,
)
from tests.integration.sqlserver_safety import (
    DboStateSnapshot,
    acquire_test_lock,
    load_integration_target,
    release_test_lock,
    verify_connected_target,
)

DATABASE_URL = os.getenv("RUNTIME_IT_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "RUNTIME_IT_DATABASE_URL not set; SQL Server integration tests skipped")
class RuntimeReviewSqlServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target = load_integration_target(os.environ)
        cls.engine = create_engine(cls.target.url, pool_pre_ping=True, future=True, hide_parameters=True)
        cls._guard_connection = None
        cls._test_lock_acquired = False
        try:
            cls._guard_connection = cls.engine.connect()
            verify_connected_target(cls._guard_connection, cls.target)
            acquire_test_lock(cls._guard_connection)
            cls._test_lock_acquired = True
            cls._state_snapshot = DboStateSnapshot.capture(cls._guard_connection)
            cls.fixtures = cls.target.fixtures
        except Exception:
            if cls._test_lock_acquired:
                release_test_lock(cls._guard_connection)
            if cls._guard_connection is not None:
                cls._guard_connection.close()
            cls.engine.dispose()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            with cls.engine.begin() as connection:
                cls._state_snapshot.restore(connection)
        finally:
            try:
                if cls._test_lock_acquired:
                    release_test_lock(cls._guard_connection)
            finally:
                if cls._guard_connection is not None:
                    cls._guard_connection.close()
                cls.engine.dispose()

    def _fixture(self, name):
        fixture = self.fixtures.get(name)
        if not fixture:
            self.skipTest(f"RUNTIME_IT_FIXTURE_JSON has no {name!r} fixture")
        return fixture

    def _session(self):
        return Session(self.engine)

    def _prime_review(self, db, execution_id, reviewer_id=None):
        db.execute(text("""
            UPDATE AgentExecution
            SET Status='Review',ReviewDecision=NULL,ReviewKey=NULL,ReviewOwnerUserID=:reviewer,
                ReviewLeaseExpiresAtUtc=CASE WHEN :reviewer IS NULL THEN NULL
                    ELSE DATEADD(minute,5,SYSUTCDATETIME()) END,ReviewAttempt=0
            WHERE ExecutionID=:execution_id
        """), {"execution_id": execution_id, "reviewer": reviewer_id})
        db.execute(text("""
            UPDATE AgentTaskQueue
            SET Status='Review',AttemptCount=1,MaxAttempts=3,LeaseOwner=NULL,
                LeaseExpiresAtUtc=NULL,LastFailure=NULL
            WHERE QueueID=(SELECT QueueID FROM AgentExecution WHERE ExecutionID=:execution_id)
        """), {"execution_id": execution_id})

    def _approved_decision(self, db, execution_id, reviewer_id, review_key):
        return review_execution(
            db, execution_id, reviewer_id, True, "SQL Server integration approval",
            review_key=review_key, require_lease=True,
        )

    def test_migrations_23_then_27_expected_state_exists(self):
        """Check canonical RBAC and review schema after migrations 23 then 27."""
        with self._session() as db:
            role_codes = set(db.execute(text("""
                SELECT RoleCode FROM dbo.Role WHERE RoleCode IN
                    ('BUSINESS_USER','APPROVER','EXECUTIVE','WORKFORCE_MANAGER','PLATFORM_OWNER',
                     'RUNTIME_REVIEWER','RUNTIME_REAPER')
            """)).scalars())
            self.assertEqual(role_codes, {
                "BUSINESS_USER", "APPROVER", "EXECUTIVE", "WORKFORCE_MANAGER",
                "PLATFORM_OWNER", "RUNTIME_REVIEWER", "RUNTIME_REAPER",
            })
            columns = set(db.execute(text("""
                SELECT name FROM sys.columns
                WHERE object_id=OBJECT_ID('dbo.AgentExecution')
            """)).scalars())
            self.assertTrue({
                "ReviewOwnerUserID", "ReviewLeaseExpiresAtUtc", "ReviewAttempt",
                "ReviewKey", "ReviewDecision",
            } <= columns)
            app_user_columns = set(db.execute(text("""
                SELECT name FROM sys.columns WHERE object_id=OBJECT_ID('dbo.AppUser')
            """)).scalars())
            self.assertIn("CreatedByUserID", app_user_columns)
            self.assertEqual(1, db.execute(text("""
                SELECT COUNT(*) FROM sys.foreign_keys
                WHERE name='FK_AgentExecution_ReviewOwner'
            """)).scalar_one())

    def test_concurrent_reviewer_claims_lease_distinct_executions(self):
        case = self._fixture("concurrent_claims")
        execution_ids = [UUID(value) for value in case["execution_ids"]]
        reviewers = [UUID(value) for value in case["reviewer_ids"]]
        with self._session() as db:
            for execution_id in execution_ids:
                self._prime_review(db, execution_id)
            db.commit()

        barrier = threading.Barrier(2)

        def claim(reviewer_id):
            with self._session() as db:
                barrier.wait(timeout=10)
                result = claim_review(db, reviewer_id)
                db.commit()
                return result

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, reviewers))
        claimed = [result["execution_id"] for result in results if result]
        self.assertEqual(len(claimed), 2)
        self.assertEqual(len(set(claimed)), 2)
        self.assertTrue(set(claimed) <= {str(value) for value in execution_ids})

    def test_expired_review_lease_can_be_reclaimed(self):
        case = self._fixture("lease_expiration")
        execution_id, reviewer_id = UUID(case["execution_id"]), UUID(case["reviewer_id"])
        with self._session() as db:
            self._prime_review(db, execution_id, reviewer_id)
            db.execute(text("""
                UPDATE AgentExecution SET ReviewLeaseExpiresAtUtc='20000101'
                WHERE ExecutionID=:id
            """), {"id": execution_id})
            db.commit()
            result = claim_review(db, reviewer_id)
            db.commit()
        self.assertEqual(result["execution_id"], str(execution_id))

    def test_reviewer_crash_is_recovered_by_reaper(self):
        case = self._fixture("reviewer_crash_recovery")
        execution_id = UUID(case["execution_id"])
        first_reviewer, next_reviewer = UUID(case["reviewer_id"]), UUID(case["next_reviewer_id"])
        with self._session() as db:
            self._prime_review(db, execution_id)
            db.commit()
            claimed = claim_review(db, first_reviewer)
            db.commit()
        self.assertEqual(claimed["execution_id"], str(execution_id))

        with self._session() as db:
            db.execute(text("""
                UPDATE AgentExecution SET ReviewLeaseExpiresAtUtc='20000101'
                WHERE ExecutionID=:id
            """), {"id": execution_id})
            db.commit()
            result = reap_expired_leases(db, "integration-test-reaper")
            db.commit()
            self.assertEqual(result["expired_review_lease_count"], 1)
            claimed_again = claim_review(db, next_reviewer)
            db.commit()
        self.assertEqual(claimed_again["execution_id"], str(execution_id))

    def test_duplicate_decision_submission_is_idempotent(self):
        case = self._fixture("duplicate_decision")
        execution_id, reviewer_id = UUID(case["execution_id"]), UUID(case["reviewer_id"])
        review_key = case["review_key"]
        with self._session() as db:
            self._prime_review(db, execution_id, reviewer_id)
            db.commit()
            first = self._approved_decision(db, execution_id, reviewer_id, review_key)
            db.commit()
            replay = self._approved_decision(db, execution_id, reviewer_id, review_key)
            self.assertFalse(first.get("idempotent_replay", False))
            self.assertTrue(replay["idempotent_replay"])
            self.assertEqual(db.execute(text("""
                SELECT COUNT(*) FROM Deliverable
                WHERE ArtifactUri=(SELECT CONCAT('agent-execution-output:',OutputID)
                    FROM AgentExecutionOutput WHERE ExecutionID=:id)
            """), {"id": execution_id}).scalar_one(), 1)

    def test_concurrent_identical_review_submissions_create_one_deliverable(self):
        case = self._fixture("concurrent_reviews")
        execution_id, reviewer_id = UUID(case["execution_id"]), UUID(case["reviewer_id"])
        review_key = case["review_key"]
        with self._session() as db:
            self._prime_review(db, execution_id, reviewer_id)
            db.commit()

        barrier = threading.Barrier(2)

        def submit():
            with self._session() as db:
                barrier.wait(timeout=10)
                result = self._approved_decision(db, execution_id, reviewer_id, review_key)
                db.commit()
                return result

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: submit(), range(2)))
        self.assertEqual(sum(bool(result.get("idempotent_replay")) for result in results), 1)
        with self._session() as db:
            output_id = db.execute(text("""
                SELECT OutputID FROM AgentExecutionOutput WHERE ExecutionID=:id
            """), {"id": execution_id}).scalar_one()
            self.assertEqual(db.execute(text("""
                SELECT COUNT(*) FROM Deliverable WHERE ArtifactUri=:uri
            """), {"uri": f"agent-execution-output:{output_id}"}).scalar_one(), 1)

    def test_duplicate_deliverable_is_rejected(self):
        case = self._fixture("duplicate_deliverable")
        execution_id, reviewer_id = UUID(case["execution_id"]), UUID(case["reviewer_id"])
        with self._session() as db:
            self._prime_review(db, execution_id, reviewer_id)
            db.commit()
            self._approved_decision(db, execution_id, reviewer_id, case["first_review_key"])
            db.commit()
            self._prime_review(db, execution_id, reviewer_id)
            db.commit()
            with self.assertRaises(HTTPException) as raised:
                self._approved_decision(db, execution_id, reviewer_id, case["second_review_key"])
            self.assertEqual(raised.exception.status_code, 409)
            db.rollback()

    def test_output_hash_is_recomputed_from_persisted_content(self):
        case = self._fixture("hash_verification")
        execution_id, reviewer_id = UUID(case["execution_id"]), UUID(case["reviewer_id"])
        with self._session() as db:
            self._prime_review(db, execution_id, reviewer_id)
            db.execute(text("""
                UPDATE AgentExecutionOutput SET Content=N'persisted content deliberately altered'
                WHERE OutputID=:output_id
            """), {"output_id": UUID(case["output_id"])})
            db.commit()
            with self.assertRaises(HTTPException) as raised:
                self._approved_decision(db, execution_id, reviewer_id, case["review_key"])
            self.assertEqual(raised.exception.status_code, 409)
            db.rollback()

    def test_failed_approval_rolls_back_decision_and_evaluation(self):
        case = self._fixture("transaction_rollback")
        execution_id, reviewer_id = UUID(case["execution_id"]), UUID(case["reviewer_id"])
        with self._session() as db:
            self._prime_review(db, execution_id, reviewer_id)
            db.execute(text("""
                UPDATE AgentExecutionOutput SET Content=N'persisted content deliberately altered'
                WHERE OutputID=:output_id
            """), {"output_id": UUID(case["output_id"])})
            db.commit()
            before = db.execute(text("""
                SELECT COUNT(*) FROM Evaluation WHERE TaskID=:task_id AND EvaluationType='IndependentQA'
            """), {"task_id": UUID(case["task_id"])}).scalar_one()
            with self.assertRaises(HTTPException):
                self._approved_decision(db, execution_id, reviewer_id, case["review_key"])
            db.rollback()
            self.assertIsNone(db.execute(text("""
                SELECT ReviewDecision FROM AgentExecution WHERE ExecutionID=:id
            """), {"id": execution_id}).scalar_one())
            after = db.execute(text("""
                SELECT COUNT(*) FROM Evaluation WHERE TaskID=:task_id AND EvaluationType='IndependentQA'
            """), {"task_id": UUID(case["task_id"])}).scalar_one()
            self.assertEqual(before, after)

    def test_defect_lifecycle_open_in_progress_retest_closed(self):
        case = self._fixture("defect_lifecycle")
        execution_id, reviewer_id = UUID(case["execution_id"]), UUID(case["reviewer_id"])
        agent_id = UUID(case["agent_id"])
        with self._session() as db:
            self._prime_review(db, execution_id, reviewer_id)
            db.commit()
            rejected = review_execution(
                db, execution_id, reviewer_id, False, "Required business rules are missing",
                defect={
                    "root_cause": "Missing requirement traceability",
                    "business_impact": "Acceptance criteria are incomplete",
                    "technical_impact": "Document cannot be approved",
                    "fix_recommendation": "Add the missing coverage and resubmit",
                    "assigned_role_code": case["required_role_code"],
                },
                review_key=case["reject_review_key"], require_lease=True,
            )
            db.commit()
            self.assertEqual(rejected["status"], "Retry")
            defect_id = db.execute(text("""
                SELECT TOP 1 DefectID FROM AgentRuntimeDefect WHERE TaskID=:task_id ORDER BY CreatedAtUtc DESC
            """), {"task_id": UUID(case["task_id"])}).scalar_one()
            self.assertEqual(db.execute(text("""
                SELECT Status FROM AgentRuntimeDefect WHERE DefectID=:id
            """), {"id": defect_id}).scalar_one(), "Open")

            correction = claim_next_task(db, agent_id, agent_id)
            db.commit()
            self.assertEqual(correction["context"]["open_defects"][0]["defect_id"], str(defect_id))
            self.assertEqual(db.execute(text("""
                SELECT Status FROM AgentRuntimeDefect WHERE DefectID=:id
            """), {"id": defect_id}).scalar_one(), "InProgress")

            submit_output(
                db, UUID(correction["execution_id"]), agent_id, "corrected-requirements.json",
                "application/json", '{"corrections":"applied"}', agent_id,
            )
            db.commit()
            self.assertEqual(db.execute(text("""
                SELECT Status FROM AgentRuntimeDefect WHERE DefectID=:id
            """), {"id": defect_id}).scalar_one(), "Retest")

            review = claim_review(db, reviewer_id)
            self.assertEqual(review["execution_id"], correction["execution_id"])
            db.commit()
            review_execution(
                db, UUID(correction["execution_id"]), reviewer_id, True,
                "Correction verified", review_key=case["approve_review_key"], require_lease=True,
            )
            db.commit()
            self.assertEqual(db.execute(text("""
                SELECT Status FROM AgentRuntimeDefect WHERE DefectID=:id
            """), {"id": defect_id}).scalar_one(), "Closed")


if __name__ == "__main__":
    unittest.main()
