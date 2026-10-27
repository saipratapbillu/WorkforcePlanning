import unittest
from unittest.mock import Mock

from app.main import readiness
from app.security.org_scope import organization_mapping_issues


class OrganizationScopeTests(unittest.TestCase):
    def test_mapping_issues_remain_diagnostic_metadata(self):
        row = {
            "MissingCompany": 4,
            "MissingDepartment": 4,
            "MissingPosition": 4,
            "DepartmentCompanyMismatch": 0,
            "PositionDepartmentMismatch": 0,
        }
        db = Mock()
        db.execute.return_value.mappings.return_value.one.return_value = row

        self.assertEqual(organization_mapping_issues(db), row)

    def test_readiness_checks_database_connectivity_only(self):
        db = Mock()

        self.assertEqual(readiness(db), {"status": "ready"})
        db.execute.assert_called_once()
        self.assertEqual(str(db.execute.call_args.args[0]), "SELECT 1")


if __name__ == "__main__":
    unittest.main()