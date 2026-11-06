import os
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from sqlalchemy.exc import OperationalError

from tools import runtime_reaper


class RuntimeReaperTests(unittest.TestCase):
    def test_run_once_invokes_existing_service_and_commits(self):
        db = Mock()
        identity = Mock()
        identity.scalar_one_or_none.return_value = 1
        lock = Mock()
        lock.scalar_one.return_value = 0
        db.execute.side_effect = [Mock(), identity, lock, Mock()]

        with patch.object(runtime_reaper, "SessionLocal", return_value=db), patch.object(
            runtime_reaper, "reap_expired_leases", return_value={"expired_count": 2}
        ) as reap:
            result = runtime_reaper.run_once(uuid4())

        self.assertEqual(result, {"expired_count": 2})
        reap.assert_called_once_with(db, actor_id="runtime-reaper")
        self.assertEqual(db.commit.call_count, 2)
        db.close.assert_called_once()
        applock_sql = str(db.execute.call_args_list[2].args[0])
        self.assertIn("@LockOwner='Transaction'", applock_sql)
        self.assertNotIn("sp_releaseapplock", " ".join(
            str(call.args[0]) for call in db.execute.call_args_list
        ))

    def test_run_once_skips_when_another_instance_holds_database_lock(self):
        db = Mock()
        identity = Mock()
        identity.scalar_one_or_none.return_value = 1
        lock = Mock()
        lock.scalar_one.return_value = -1
        db.execute.side_effect = [Mock(), identity, lock, Mock()]

        with patch.object(runtime_reaper, "SessionLocal", return_value=db), patch.object(
            runtime_reaper, "reap_expired_leases"
        ) as reap:
            result = runtime_reaper.run_once(uuid4())

        self.assertIsNone(result)
        reap.assert_not_called()
        db.rollback.assert_called_once()
        db.close.assert_called_once()

    def test_once_returns_failure_when_database_is_unavailable(self):
        with patch.dict(os.environ, {"RUNTIME_REAPER_USER_ID": str(uuid4())}), patch.object(
            runtime_reaper,
            "run_once",
            side_effect=OperationalError("connect", {}, Exception()),
        ):
            self.assertEqual(runtime_reaper.main(["--once"]), 1)

    def test_once_requires_configured_service_identity(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(runtime_reaper.main(["--once"]), 2)

    def test_invalid_poll_interval_is_rejected(self):
        with self.assertRaises(SystemExit):
            runtime_reaper.main(["--interval-seconds", "0"])


if __name__ == "__main__":
    unittest.main()
