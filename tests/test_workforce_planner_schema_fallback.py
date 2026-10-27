import unittest
from unittest.mock import Mock

from app.services.workforce_planner import WorkforcePlanner


class WorkforcePlannerSchemaFallbackTests(unittest.TestCase):
    def test_missing_reuse_migration_is_detected_without_querying_missing_table(self):
        db = Mock()
        db.execute.return_value.scalar_one.return_value = 0

        available = WorkforcePlanner.reuse_assessments_available(db)

        self.assertFalse(available)
        self.assertIn("OBJECT_ID", str(db.execute.call_args.args[0]))
        self.assertIn("WorkforceReuseAssessment", str(db.execute.call_args.args[0]))


if __name__ == "__main__":
    unittest.main()