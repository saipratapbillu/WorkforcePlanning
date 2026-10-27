import unittest

from app.security.middleware import forbidden_for_role


class AuthorizationMiddlewarePolicyTests(unittest.TestCase):
    def test_business_user_is_denied_restricted_interfaces(self):
        restricted = (
            "/workforce-center",
            "/static/workforce-center.html",
            "/static/owner-command-center.html",
            "/agents",
            "/runtime/monitor",
        )
        for path in restricted:
            with self.subTest(path=path):
                self.assertTrue(forbidden_for_role(path, "USER"))

    def test_canonical_roles_control_workforce_and_executive_interfaces(self):
        self.assertFalse(forbidden_for_role("/workforce-center", "WORKFORCE_MANAGER"))
        self.assertFalse(forbidden_for_role("/workforce-center", "DEPARTMENT_HEAD"))
        self.assertTrue(forbidden_for_role("/workforce-center", "BUSINESS_USER"))
        self.assertFalse(forbidden_for_role("/static/owner-command-center.html", "PLATFORM_OWNER"))
        self.assertFalse(forbidden_for_role("/static/owner-command-center.html", "EXECUTIVE"))
        self.assertTrue(forbidden_for_role("/runtime/monitor", "EXECUTIVE"))
        self.assertTrue(forbidden_for_role("/runtime/monitor", "BUSINESS_USER"))

    def test_runtime_mutation_endpoints_require_owner_authority(self):
        self.assertTrue(forbidden_for_role("/runtime/projects/abc/enqueue", "WORKFORCE_MANAGER"))
        self.assertFalse(forbidden_for_role("/runtime/projects/abc/enqueue", "PLATFORM_OWNER"))


if __name__ == "__main__":
    unittest.main()
