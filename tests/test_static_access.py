import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.main import static_asset


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


if __name__ == "__main__":
    unittest.main()
