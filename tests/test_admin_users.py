import unittest
import uuid
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.api import admin_users
from app.api.admin_users import (
    OrganizationAssignment,
    PasswordReset,
    RoleAssignment,
    UserCreate,
    _protect_last_owner,
    _validate_organization,
    get_user_skills,
    list_users,
    reset_password,
)


class AdminUsersApiTests(unittest.TestCase):
    def test_routes_are_declared_and_require_platform_owner(self):
        expected = {
            ("GET", "/admin/users"),
            ("GET", "/admin/users/catalogs"),
            ("POST", "/admin/users"),
            ("PATCH", "/admin/users/{user_id}"),
            ("DELETE", "/admin/users/{user_id}"),
            ("POST", "/admin/users/{user_id}/disable"),
            ("POST", "/admin/users/{user_id}/enable"),
            ("POST", "/admin/users/{user_id}/reset-password"),
            ("PUT", "/admin/users/{user_id}/role"),
            ("PUT", "/admin/users/{user_id}/organization"),
            ("PUT", "/admin/users/{user_id}/skills"),
            ("GET", "/admin/users/{user_id}/skills"),
        }
        routes = [route for route in admin_users.router.routes if isinstance(route, APIRoute)]
        actual = {(method, route.path) for route in routes for method in route.methods}
        self.assertEqual(actual, expected)
        for route in routes:
            self.assertTrue(route.dependencies)
            closure_values = [
                cell.cell_contents
                for cell in (route.dependencies[0].dependency.__closure__ or ())
            ]
            self.assertIn(("PLATFORM_OWNER",), closure_values)

    def test_user_listing_omits_hash_and_supports_bounded_query(self):
        row = {
            "user_id": uuid.uuid4(),
            "email": "user@example.com",
            "display_name": "User",
            "is_active": True,
        }
        db = Mock()
        db.execute.return_value.mappings.return_value.all.return_value = [row]

        result = list_users(active=True, q="user", limit=20, offset=10, db=db)

        statement = str(db.execute.call_args.args[0])
        self.assertNotIn("PasswordHash", statement)
        self.assertEqual(result["items"], [row])
        self.assertEqual(result["limit"], 20)
        params = db.execute.call_args.args[1]
        self.assertEqual(params["active"], 1)
        self.assertEqual(params["query"], "%user%")

    def test_create_hashes_password_and_does_not_return_it(self):
        role_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        db = Mock()
        duplicate_result = Mock()
        duplicate_result.scalar_one_or_none.return_value = None
        role_result = Mock()
        role_result.mappings.return_value.first.return_value = {
            "RoleID": role_id,
            "RoleCode": "BUSINESS_USER",
        }
        db.execute.side_effect = [duplicate_result, role_result, Mock(), Mock()]
        body = UserCreate(
            email=" New.User@Example.com ",
            password="NotReturned12!",
            display_name="New User",
            role_id=role_id,
        )

        with patch("app.api.admin_users.hash_password", return_value="pbkdf2_sha256$test$salt$digest"):
            result = admin_users.create_user(body, db=db, user={"sub": str(actor_id)})

        self.assertEqual(result["email"], "new.user@example.com")
        self.assertNotIn("password", result)
        self.assertNotIn("password_hash", result)
        insert_params = db.execute.call_args_list[2].args[1]
        self.assertEqual(insert_params["password_hash"], "pbkdf2_sha256$test$salt$digest")
        self.assertEqual(insert_params["created_by_user_id"], str(actor_id))
        self.assertNotIn(body.password, insert_params["password_hash"])
        db.commit.assert_called_once()

    def test_create_user_rejects_reviewer_role_for_authenticated_email(self):
        actor_id = uuid.uuid4()
        role_id = uuid.uuid4()
        db = Mock()
        duplicate_result = Mock()
        duplicate_result.scalar_one_or_none.return_value = None
        role_result = Mock()
        role_result.mappings.return_value.first.return_value = {
            "RoleID": role_id,
            "RoleCode": "RUNTIME_REVIEWER",
        }
        db.execute.side_effect = [duplicate_result, role_result]
        body = UserCreate(
            email="owner@example.com",
            password="SecurePassword123!",
            display_name="Owner",
            role_id=role_id,
        )

        with self.assertRaises(HTTPException) as raised:
            admin_users.create_user(body, db=db, user={
                "sub": str(actor_id),
                "email": "OWNER@example.com",
            })

        self.assertEqual(raised.exception.status_code, 403)
        db.commit.assert_not_called()

    def test_create_user_cannot_create_a_second_reviewer_identity(self):
        actor_id = uuid.uuid4()
        role_id = uuid.uuid4()
        db = Mock()
        duplicate_result = Mock()
        duplicate_result.scalar_one_or_none.return_value = None
        role_result = Mock()
        role_result.mappings.return_value.first.return_value = {
            "RoleID": role_id,
            "RoleCode": "RUNTIME_REVIEWER",
        }
        db.execute.side_effect = [duplicate_result, role_result]
        body = UserCreate(
            email="separate.reviewer@example.com",
            password="SecurePassword123!",
            display_name="Separate Reviewer",
            role_id=role_id,
        )

        with self.assertRaises(HTTPException) as raised:
            admin_users.create_user(body, db=db, user={
                "sub": str(actor_id),
                "email": "owner@example.com",
            })

        self.assertEqual(raised.exception.status_code, 403)
        db.commit.assert_not_called()

    def test_role_update_rejects_reviewer_identity_created_by_actor(self):
        actor_id = uuid.uuid4()
        target_id = uuid.uuid4()
        role_id = uuid.uuid4()
        db = Mock()
        target_result = Mock()
        target_result.mappings.return_value.first.return_value = {
            "UserID": target_id,
            "IsActive": True,
            "CreatedByUserID": actor_id,
            "RoleCode": "BUSINESS_USER",
            "RoleIsActive": True,
        }
        role_result = Mock()
        role_result.mappings.return_value.first.return_value = {
            "RoleID": role_id,
            "RoleCode": "RUNTIME_REVIEWER",
        }
        db.execute.side_effect = [target_result, role_result]

        with self.assertRaises(HTTPException) as raised:
            admin_users.assign_role(
                target_id,
                RoleAssignment(role_id=role_id),
                db=db,
                user={"sub": str(actor_id)},
            )

        self.assertEqual(raised.exception.status_code, 403)
        db.commit.assert_not_called()

    def test_role_update_fails_closed_for_legacy_account_without_creator(self):
        actor_id = uuid.uuid4()
        target_id = uuid.uuid4()
        role_id = uuid.uuid4()
        db = Mock()
        target_result = Mock()
        target_result.mappings.return_value.first.return_value = {
            "UserID": target_id,
            "IsActive": True,
            "CreatedByUserID": None,
            "RoleCode": "BUSINESS_USER",
            "RoleIsActive": True,
        }
        role_result = Mock()
        role_result.mappings.return_value.first.return_value = {
            "RoleID": role_id,
            "RoleCode": "RUNTIME_REVIEWER",
        }
        db.execute.side_effect = [target_result, role_result]

        with self.assertRaises(HTTPException) as raised:
            admin_users.assign_role(
                target_id,
                RoleAssignment(role_id=role_id),
                db=db,
                user={"sub": str(actor_id)},
            )

        self.assertEqual(raised.exception.status_code, 403)
        db.commit.assert_not_called()

    def test_reviewer_role_assignment_to_independently_created_account_is_allowed(self):
        role = {"RoleCode": "RUNTIME_REVIEWER"}
        admin_users._guard_reviewer_role(
            role,
            str(uuid.uuid4()),
            uuid.uuid4(),
            target_creator_id=uuid.uuid4(),
        )

    def test_create_user_fails_closed_when_reviewer_actor_email_is_missing(self):
        actor_id = uuid.uuid4()
        role_id = uuid.uuid4()
        db = Mock()
        duplicate_result = Mock()
        duplicate_result.scalar_one_or_none.return_value = None
        role_result = Mock()
        role_result.mappings.return_value.first.return_value = {
            "RoleID": role_id,
            "RoleCode": "RUNTIME_REVIEWER",
        }
        db.execute.side_effect = [duplicate_result, role_result]
        body = UserCreate(
            email="reviewer@example.com",
            password="SecurePassword123!",
            display_name="Reviewer",
            role_id=role_id,
        )

        with self.assertRaises(HTTPException) as raised:
            admin_users.create_user(body, db=db, user={"sub": str(actor_id)})

        self.assertEqual(raised.exception.status_code, 403)
        db.commit.assert_not_called()

    def test_role_update_rejects_self_assignment_as_reviewer(self):
        actor_id = uuid.uuid4()
        role_id = uuid.uuid4()
        db = Mock()
        target_result = Mock()
        target_result.mappings.return_value.first.return_value = {
            "UserID": actor_id,
            "IsActive": True,
            "RoleCode": "PLATFORM_OWNER",
            "RoleIsActive": True,
        }
        role_result = Mock()
        role_result.mappings.return_value.first.return_value = {
            "RoleID": role_id,
            "RoleCode": "RUNTIME_REVIEWER",
        }
        db.execute.side_effect = [target_result, role_result]

        with self.assertRaises(HTTPException) as raised:
            admin_users.assign_role(
                actor_id,
                RoleAssignment(role_id=role_id),
                db=db,
                user={"sub": str(actor_id)},
            )

        self.assertEqual(raised.exception.status_code, 403)
        db.commit.assert_not_called()

    def test_reviewer_role_can_only_be_provisioned_by_platform_owner_routes(self):
        routes = [route for route in admin_users.router.routes if isinstance(route, APIRoute)]
        guarded_routes = {
            route.path: route
            for route in routes
            if route.path in {"/admin/users", "/admin/users/{user_id}/role"}
        }
        self.assertEqual(set(guarded_routes), {"/admin/users", "/admin/users/{user_id}/role"})
        for route in guarded_routes.values():
            dependency = route.dependencies[0].dependency
            closure_values = [
                cell.cell_contents for cell in (dependency.__closure__ or ())
            ]
            self.assertIn(("PLATFORM_OWNER",), closure_values)
            for role in ("BUSINESS_USER", "WORKFORCE_MANAGER", "RUNTIME_REVIEWER"):
                with self.subTest(path=route.path, role=role), self.assertRaises(HTTPException) as raised:
                    dependency(user={"role": role})
                self.assertEqual(raised.exception.status_code, 403)

    def test_reset_password_stores_only_hash_and_never_returns_password(self):
        user_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        db = Mock()
        target_result = Mock()
        target_result.mappings.return_value.first.return_value = {
            "UserID": user_id,
            "IsActive": True,
            "RoleCode": "BUSINESS_USER",
            "RoleIsActive": True,
        }
        db.execute.side_effect = [target_result, Mock(), Mock()]
        body = PasswordReset(password="Replacement12!")

        with patch("app.api.admin_users.hash_password", return_value="pbkdf2_sha256$test$salt$digest"):
            result = reset_password(user_id, body, db=db, user={"sub": str(actor_id)})

        self.assertEqual(result, {"user_id": str(user_id), "password_reset": True})
        update_params = db.execute.call_args_list[1].args[1]
        self.assertEqual(update_params["password_hash"], "pbkdf2_sha256$test$salt$digest")
        self.assertNotIn(body.password, update_params["password_hash"])
        db.commit.assert_called_once()

    def test_last_active_owner_cannot_demote_or_deactivate_self(self):
        actor_id = uuid.uuid4()
        target = {"RoleCode": "SUPER_ADMIN", "RoleIsActive": True, "IsActive": True}
        db = Mock()
        db.execute.return_value.scalar_one.return_value = 1

        with self.assertRaises(HTTPException) as raised:
            _protect_last_owner(db, target, actor_id, str(actor_id))

        self.assertEqual(raised.exception.status_code, 409)

    def test_non_last_self_owner_can_be_demoted(self):
        actor_id = uuid.uuid4()
        target = {"RoleCode": "OWNER", "RoleIsActive": True, "IsActive": True}
        db = Mock()
        db.execute.return_value.scalar_one.return_value = 2

        _protect_last_owner(db, target, actor_id, str(actor_id))

        db.execute.assert_called_once()

    def test_organization_assignment_requires_active_parent_relationships(self):
        db = Mock()
        db.execute.return_value.scalar_one_or_none.return_value = None
        assignment = OrganizationAssignment(
            company_id=uuid.uuid4(),
            department_id=uuid.uuid4(),
            position_id=uuid.uuid4(),
        )

        with self.assertRaises(HTTPException) as raised:
            _validate_organization(
                db,
                assignment.company_id,
                assignment.department_id,
                assignment.position_id,
            )

        self.assertEqual(raised.exception.status_code, 422)

    def test_skills_listing_joins_skill_catalog_and_user_assignments(self):
        user_id = uuid.uuid4()
        db = Mock()
        target_result = Mock()
        target_result.mappings.return_value.first.return_value = {
            "UserID": user_id,
            "IsActive": True,
            "RoleCode": "BUSINESS_USER",
            "RoleIsActive": True,
        }
        skills = [{"skill_id": uuid.uuid4(), "name": "Python", "proficiency": 4}]
        skill_result = Mock()
        skill_result.mappings.return_value.all.return_value = skills
        db.execute.side_effect = [target_result, skill_result]

        result = get_user_skills(user_id, db=db)

        self.assertEqual(result["skills"], skills)
        statement = str(db.execute.call_args_list[1].args[0])
        self.assertIn("JOIN dbo.Skill", statement)
        self.assertIn("dbo.AppUserSkill", statement)


if __name__ == "__main__":
    unittest.main()
