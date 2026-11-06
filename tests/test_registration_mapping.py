import unittest
from unittest.mock import Mock

from fastapi import HTTPException

from app.api.users import register_user
from app.db.session import Base
from app.models.entities import AppUser
from app.schemas.schemas import UserRegister


class RegistrationMappingTests(unittest.TestCase):
    def test_user_mapping_resolves_all_foreign_key_tables(self):
        mapped_tables = {table.name for table in Base.metadata.sorted_tables}

        self.assertIn("Company", mapped_tables)
        self.assertIn("Department", mapped_tables)
        self.assertIn("Position", mapped_tables)

    def test_registration_creates_a_normalized_business_user(self):
        role = Mock(RoleID="business-user-role", RoleCode="BUSINESS_USER")
        role_result = Mock()
        role_result.scalars.return_value.first.return_value = role
        duplicate_result = Mock()
        duplicate_result.scalar_one_or_none.return_value = None
        db = Mock()
        db.execute.side_effect = [role_result, duplicate_result, None]
        body = UserRegister(
            first_name="  John ",
            last_name=" Business ",
            email=" QA.Business@Test.com ",
            password="Test@123456789",
        )

        result = register_user(body, db)

        created = db.add.call_args.args[0]
        self.assertEqual(created.Email, "qa.business@test.com")
        self.assertEqual(created.DisplayName, "John Business")
        self.assertEqual(created.RoleID, role.RoleID)
        self.assertEqual(result["message"], "User registered successfully")
        db.commit.assert_called_once()

    def test_registration_rejects_an_existing_email_without_creating_a_user(self):
        role_result = Mock()
        role_result.scalars.return_value.first.return_value = Mock(RoleID="business-role")
        existing_result = Mock()
        existing_result.scalar_one_or_none.return_value = object()
        db = Mock()
        db.execute.side_effect = [role_result, existing_result]
        body = UserRegister(
            first_name="John",
            last_name="Business",
            email=" QA.Business@Test.com ",
            password="Test@123456789",
        )

        with self.assertRaises(HTTPException) as raised:
            register_user(body, db)

        self.assertEqual(raised.exception.status_code, 409)
        db.add.assert_not_called()
        db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
