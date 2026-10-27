import unittest
from unittest.mock import Mock

from fastapi import HTTPException

from app.api.dashboard import executive_dashboard


class ExecutiveDashboardTests(unittest.TestCase):
    def test_executive_metrics_do_not_require_company_mapping(self):
        result = Mock()
        result.mappings.return_value.all.return_value = []
        db = Mock()
        db.execute.return_value = result

        dashboard = executive_dashboard("ceo", db, {"sub": "user-id", "role": "EXECUTIVE"})

        self.assertEqual(dashboard["organization_scope"], "single_organization")
        self.assertEqual(dashboard["sections"]["projects"], [])
        self.assertEqual(db.execute.call_count, 5)
        self.assertTrue(all("CompanyID" not in str(call.args[0]) for call in db.execute.call_args_list))

    def test_unknown_executive_view_is_not_found(self):
        db = Mock()

        with self.assertRaises(HTTPException) as raised:
            executive_dashboard("cfo", db, {"sub": "user-id", "role": "SUPER_ADMIN"})

        self.assertEqual(raised.exception.status_code, 404)
        db.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()