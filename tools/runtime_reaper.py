"""Poll the authoritative AgentRuntime lease reaper from a standalone process."""

import argparse
import logging
import math
import os
import sys
import time
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.services.agent_runtime import reap_expired_leases

LOGGER = logging.getLogger("ai_workforce.runtime_reaper")
LOCK_RESOURCE = "AIWorkforceOS:AgentRuntime:LeaseReaper"


def run_once(reaper_user_id: UUID) -> dict | None:
    """Run one reaper pass, returning None when another process owns the SQL lock."""
    db = SessionLocal()
    context_set = False
    try:
        db.execute(text("""
            EXEC sys.sp_set_session_context @key=N'UserID', @value=:user_id;
        """), {"user_id": reaper_user_id})
        context_set = True
        is_active_reaper = db.execute(text("""
            SELECT 1
            FROM dbo.AppUser u
            JOIN dbo.Role r ON r.RoleID=u.RoleID
            WHERE u.UserID=:user_id AND u.IsActive=1 AND r.IsActive=1
              AND r.RoleCode='RUNTIME_REAPER'
        """), {"user_id": reaper_user_id}).scalar_one_or_none()
        if not is_active_reaper:
            raise RuntimeError("RUNTIME_REAPER_USER_ID must identify an active RUNTIME_REAPER AppUser")

        lock_result = db.execute(text("""
            DECLARE @lock_result int;
            EXEC @lock_result = sys.sp_getapplock
                @Resource=:resource,
                @LockMode='Exclusive',
                @LockOwner='Transaction',
                @LockTimeout=0;
            SELECT @lock_result;
        """), {"resource": LOCK_RESOURCE}).scalar_one()
        if lock_result < 0:
            db.rollback()
            LOGGER.info("Another reaper process holds the database application lock; skipping this pass")
            return None

        result = reap_expired_leases(db, actor_id="runtime-reaper")
        db.commit()
        LOGGER.info("Runtime lease reaper completed: %s", result)
        return result
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        if context_set:
            try:
                db.execute(text("""
                    EXEC sys.sp_set_session_context @key=N'UserID', @value=NULL;
                """))
                db.commit()
            except SQLAlchemyError:
                LOGGER.exception("Could not clear the reaper SQL session identity")
                db.rollback()
        db.close()


def _positive_float(value: str) -> float:
    try:
        interval = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive number") from exc
    if not math.isfinite(interval) or interval <= 0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return interval


def _positive_int(value: str) -> int:
    try:
        count = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if count < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--interval-seconds",
        type=_positive_float,
        default=os.getenv("RUNTIME_REAPER_INTERVAL_SECONDS", "60"),
    )
    parser.add_argument(
        "--max-consecutive-failures",
        type=_positive_int,
        default=os.getenv("RUNTIME_REAPER_MAX_FAILURES", "5"),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one pass and exit; suitable for a repeating Task Scheduler trigger.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=os.getenv("RUNTIME_REAPER_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        reaper_user_id = UUID(os.environ["RUNTIME_REAPER_USER_ID"])
    except (KeyError, ValueError):
        LOGGER.error("RUNTIME_REAPER_USER_ID must be set to the dedicated reaper AppUser UUID")
        return 2

    if args.once:
        try:
            run_once(reaper_user_id)
        except SQLAlchemyError:
            LOGGER.exception("Runtime lease reaper database pass failed")
            return 1
        except RuntimeError as error:
            LOGGER.error("%s", error)
            return 2
        return 0

    consecutive_failures = 0
    try:
        while True:
            try:
                run_once(reaper_user_id)
                consecutive_failures = 0
            except SQLAlchemyError:
                consecutive_failures += 1
                LOGGER.exception(
                    "Runtime lease reaper database pass failed (%d/%d)",
                    consecutive_failures,
                    args.max_consecutive_failures,
                )
                if consecutive_failures >= args.max_consecutive_failures:
                    return 1
            except RuntimeError as error:
                LOGGER.error("%s", error)
                return 2
            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        LOGGER.info("Runtime lease reaper stopped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
