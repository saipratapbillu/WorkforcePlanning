import unittest

from fastapi import HTTPException

from app.main import authorize_static_html
from app.security.middleware import AUTHENTICATED_PREFIXES, forbidden_for_role


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
        self.assertIn("/execution", AUTHENTICATED_PREFIXES)

    def test_reviewer_is_confined_to_review_and_session_endpoints(self):
        allowed = (
            "/runtime/reviews/claim",
            "/runtime/reviews/00000000-0000-0000-0000-000000000001",
            "/runtime/reviews/00000000-0000-0000-0000-000000000001/decision",
            "/auth/me",
            "/auth/logout",
        )
        denied = (
            "/runtime/monitor",
            "/runtime/defects",
            "/runtime/worker/claim",
            "/admin/users",
            "/admin/org-mappings",
            "/agents",
            "/dashboard/api",
            "/requirements",
            "/projects",
            "/tasks",
            "/approvals",
            "/notifications",
            "/operations",
            "/model-governance/models/catalog",
        )
        for path in allowed:
            with self.subTest(path=path):
                self.assertFalse(forbidden_for_role(path, "RUNTIME_REVIEWER"))
        for path in denied:
            with self.subTest(path=path):
                self.assertTrue(forbidden_for_role(path, "RUNTIME_REVIEWER"))

    def test_reviewer_cannot_fetch_any_static_html(self):
        for filename in ("dashboard.html", "requirement-chat.html", "user-management.html"):
            with self.subTest(filename=filename), self.assertRaises(HTTPException) as raised:
                authorize_static_html(filename, {"role": "RUNTIME_REVIEWER"})
            self.assertEqual(raised.exception.status_code, 403)
        with self.assertRaises(HTTPException) as raised:
            authorize_static_html("dashboard.html", {"role": "RUNTIME_REAPER"})
        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
