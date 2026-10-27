import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import HTTPException

from app.security.dependencies import get_current_user


class AuthenticatedRoleTests(unittest.TestCase):
    def make_request(self):
        return SimpleNamespace(cookies={})

    def make_credentials(self, token="valid-token"):
        return SimpleNamespace(credentials=token)

    def test_active_user_with_missing_role_is_rejected(self):
        user = SimpleNamespace(
            UserID=uuid.uuid4(),
            Email="user@example.test",
            DisplayName="Test User",
            Department=None,
            IsActive=True,
            Role=None,
        )
        database = Mock()
        database.get.return_value = user

        with unittest.mock.patch("app.security.dependencies.jwt.decode", return_value={"sub": str(user.UserID)}):
            with self.assertRaises(HTTPException) as raised:
                get_current_user(self.make_request(), self.make_credentials(), database)

        self.assertEqual(raised.exception.status_code, 401)

    def test_active_user_with_inactive_role_is_rejected(self):
        user = SimpleNamespace(
            UserID=uuid.uuid4(),
            Email="user@example.test",
            DisplayName="Test User",
            Department=None,
            IsActive=True,
            Role=SimpleNamespace(RoleCode="OWNER", IsActive=False),
        )
        database = Mock()
        database.get.return_value = user

        with unittest.mock.patch("app.security.dependencies.jwt.decode", return_value={"sub": str(user.UserID)}):
            with self.assertRaises(HTTPException) as raised:
                get_current_user(self.make_request(), self.make_credentials(), database)

        self.assertEqual(raised.exception.status_code, 401)

    def test_active_user_retains_current_active_role(self):
        user = SimpleNamespace(
            UserID=uuid.uuid4(),
            Email="owner@example.test",
            DisplayName="Test Owner",
            Department="Governance",
            IsActive=True,
            Role=SimpleNamespace(RoleCode="OWNER", IsActive=True),
        )
        database = Mock()
        database.get.return_value = user

        with unittest.mock.patch("app.security.dependencies.jwt.decode", return_value={"sub": str(user.UserID)}):
            result = get_current_user(self.make_request(), self.make_credentials(), database)

        self.assertEqual(result["role"], "PLATFORM_OWNER")
        self.assertEqual(result["legacy_role"], "OWNER")


if __name__ == "__main__":
    unittest.main()
