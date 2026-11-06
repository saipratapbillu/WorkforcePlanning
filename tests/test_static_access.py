import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.main import static_asset

STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"


class StaticPageAccessTests(unittest.TestCase):
    def request_static_page(self, filename, role):
        with patch("app.main.get_current_user", return_value={"role": role}):
            return static_asset(filename, Mock(), None, Mock())

    def test_workforce_center_direct_url_requires_workforce_role(self):
        for role in ("BUSINESS_USER", "APPROVER"):
            with self.subTest(role=role):
                with self.assertRaises(HTTPException) as raised:
                    self.request_static_page("workforce-center.html", role)
                self.assertEqual(raised.exception.status_code, 403)

        for role in ("WORKFORCE_MANAGER", "MANAGER", "ADMIN", "PLATFORM_OWNER", "OWNER", "SUPER_ADMIN"):
            with self.subTest(role=role):
                self.assertIsNotNone(self.request_static_page("workforce-center.html", role))

    def test_executive_command_center_direct_url_is_executive_or_platform_owner(self):
        for role in ("BUSINESS_USER", "APPROVER", "WORKFORCE_MANAGER"):
            with self.subTest(role=role):
                with self.assertRaises(HTTPException) as raised:
                    self.request_static_page("owner-command-center.html", role)
                self.assertEqual(raised.exception.status_code, 403)

        for role in ("EXECUTIVE", "PLATFORM_OWNER", "OWNER", "SUPER_ADMIN"):
            with self.subTest(role=role):
                self.assertIsNotNone(self.request_static_page("owner-command-center.html", role))

    def test_other_private_pages_remain_available_to_authenticated_users(self):
        self.assertIsNotNone(self.request_static_page("dashboard.html", "USER"))

    def test_user_management_direct_url_requires_platform_owner(self):
        for role in ("BUSINESS_USER", "APPROVER", "EXECUTIVE", "WORKFORCE_MANAGER"):
            with self.subTest(role=role):
                with self.assertRaises(HTTPException) as raised:
                    self.request_static_page("user-management.html", role)
                self.assertEqual(raised.exception.status_code, 403)

        for role in ("PLATFORM_OWNER", "OWNER", "SUPER_ADMIN"):
            with self.subTest(role=role):
                self.assertIsNotNone(self.request_static_page("user-management.html", role))

    def test_admin_workspace_direct_static_url_requires_platform_owner(self):
        for role in ("BUSINESS_USER", "APPROVER", "EXECUTIVE", "WORKFORCE_MANAGER"):
            with self.subTest(role=role):
                with self.assertRaises(HTTPException) as raised:
                    self.request_static_page("admin-workspace.html", role)
                self.assertEqual(raised.exception.status_code, 403)
        for role in ("PLATFORM_OWNER", "OWNER", "SUPER_ADMIN"):
            with self.subTest(role=role):
                self.assertIsNotNone(self.request_static_page("admin-workspace.html", role))

    def test_workforce_management_direct_url_requires_management_role(self):
        for role in ("BUSINESS_USER", "APPROVER", "EXECUTIVE"):
            with self.subTest(role=role):
                with self.assertRaises(HTTPException) as raised:
                    self.request_static_page("workforce-management.html", role)
                self.assertEqual(raised.exception.status_code, 403)

        for role in ("WORKFORCE_MANAGER", "MANAGER", "ADMIN", "PLATFORM_OWNER", "OWNER", "SUPER_ADMIN"):
            with self.subTest(role=role):
                self.assertIsNotNone(self.request_static_page("workforce-management.html", role))

    def test_execution_management_page_is_manager_only(self):
        for role in ("BUSINESS_USER", "APPROVER", "EXECUTIVE"):
            with self.subTest(role=role):
                with self.assertRaises(HTTPException) as raised:
                    self.request_static_page("execution-management.html", role)
                self.assertEqual(raised.exception.status_code, 403)
        for role in ("WORKFORCE_MANAGER", "PLATFORM_OWNER"):
            with self.subTest(role=role):
                self.assertIsNotNone(self.request_static_page("execution-management.html", role))

    def test_dashboard_source_uses_utf8_and_svg_icons_without_mojibake(self):
        dashboard = (STATIC_DIR / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('<meta charset="utf-8">', dashboard.lower())
        self.assertIn('id="icon-overview"', dashboard)
        self.assertIn('id="icon-approvals"', dashboard)
        for artifact in ("â", "Ã", "Â·", "\ufffd"):
            self.assertNotIn(artifact, dashboard)

    def test_projects_approval_link_targets_the_ui_page(self):
        projects = (STATIC_DIR / "projects.html").read_text(encoding="utf-8")
        self.assertIn('href="/approval-center">Approvals</a>', projects)
        self.assertNotIn('href="/approvals">Approvals</a>', projects)

    def test_password_forms_use_concise_placeholder_and_single_toggle_script(self):
        for filename in ("login.html", "register.html"):
            with self.subTest(filename=filename):
                page = (STATIC_DIR / filename).read_text(encoding="utf-8")
                self.assertIn('placeholder="Password"', page)
                self.assertIn('minlength="4"', page)
        user_management = (STATIC_DIR / "user-management.html").read_text(encoding="utf-8")
        self.assertEqual(user_management.count("password-toggle.js"), 1)


if __name__ == "__main__":
    unittest.main()
