import unittest
import uuid
from unittest.mock import Mock

from app.repositories.security_repository import SecurityRepository
from app.security.visibility import VisibilityContext


class SecurityRepositoryTests(unittest.TestCase):
    def test_visibility_context_parses_only_server_supplied_scope(self):
        user_id, company_id, department_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        context = VisibilityContext.from_user({
            "sub": str(user_id),
            "role": "MANAGER",
        })
        self.assertEqual(context.user_id, user_id)
        self.assertIsNone(context.company_id)
        self.assertIsNone(context.department_id)
        self.assertTrue(context.is_organization_scope)
        self.assertTrue(context.supported)

    def test_unknown_role_fails_closed_without_query(self):
        database = Mock()
        rows = SecurityRepository(database).GetVisibleRequirements({"sub": str(uuid.uuid4()), "role": "UNASSIGNED_ROLE"})
        self.assertEqual(rows, [])
        database.execute.assert_not_called()

    def test_workforce_manager_visibility_does_not_require_org_mappings(self):
        user_id = uuid.uuid4()
        result = Mock()
        result.mappings.return_value.all.return_value = []
        database = Mock()
        database.execute.return_value = result

        rows = SecurityRepository(database).GetVisibleRequirements({
            "sub": str(user_id), "role": "WORKFORCE_MANAGER",
        })

        self.assertEqual(rows, [])
        statement = str(database.execute.call_args.args[0])
        params = database.execute.call_args.args[1]
        self.assertIn("CreatedByUserID", statement)
        self.assertIn(":is_organization_scope = 1", statement)
        self.assertNotIn("owner_user.DepartmentID = :department_id", statement)
        self.assertEqual(params["user_id"], user_id)
        self.assertNotIn("company_id", params)
        self.assertNotIn("department_id", params)
        self.assertEqual(params["role"], "WORKFORCE_MANAGER")

    def test_notification_visibility_is_recipient_only_for_user_roles(self):
        user_id = uuid.uuid4()
        result = Mock()
        result.mappings.return_value.all.return_value = []
        database = Mock()
        database.execute.return_value = result

        SecurityRepository(database).GetVisibleNotifications({"sub": str(user_id), "role": "USER"})

        statement = str(database.execute.call_args.args[0])
        params = database.execute.call_args.args[1]
        self.assertIn("n.UserID=:user_id", statement)
        self.assertNotIn("owner_user.CompanyID", statement)
        self.assertNotIn("owner_user.DepartmentID", statement)
        self.assertEqual(params["user_id"], user_id)

    def test_super_admin_is_all_scope(self):
        context = VisibilityContext.from_user({"sub": str(uuid.uuid4()), "role": "SUPER_ADMIN"})
        self.assertTrue(context.is_super_admin)
        self.assertTrue(context.supported)


if __name__ == "__main__":
    unittest.main()
