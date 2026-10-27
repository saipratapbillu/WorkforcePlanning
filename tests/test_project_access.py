import unittest

from fastapi import HTTPException

from app.api.projects import require_project_scope


class ProjectAccessTests(unittest.TestCase):
    def test_known_roles_enter_registry_and_visibility_is_applied_by_repository(self):
        for role in ("BUSINESS_USER", "APPROVER", "EXECUTIVE", "WORKFORCE_MANAGER", "PLATFORM_OWNER", "USER"):
            with self.subTest(role=role):
                user = {"role": role}
                self.assertEqual(require_project_scope(user), user)

        with self.assertRaises(HTTPException) as raised:
            require_project_scope({"role": "UNASSIGNED_ROLE"})
        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
