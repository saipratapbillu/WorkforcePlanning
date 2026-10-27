import unittest
import uuid
from unittest.mock import Mock

from app.api.requirements import create_requirement
from app.schemas.schemas import RequirementCreate


class RequirementCreationOwnershipTests(unittest.TestCase):
    def test_create_requirement_persists_authenticated_user_id(self):
        user_id = uuid.uuid4()
        db = Mock()
        body = RequirementCreate(
            title="Ownership propagation test",
            description="Verify normalized owner for a secure Angular .NET API.",
            requested_by="Ignored client label",
            priority="High",
        )

        response = create_requirement(body, db, {"sub": str(user_id), "name": "Test User"})

        created = db.add.call_args.args[0]
        self.assertEqual(created.CreatedBy, str(user_id))
        self.assertEqual(created.CreatedByUserID, user_id)
        self.assertIn("workforce_blueprint", response)
        self.assertIn("testing_execution_package", response["workforce_blueprint"])
        hosting_package = response["workforce_blueprint"]["hosting_execution_package"]
        self.assertEqual(hosting_package["authority"], "NONE")
        self.assertFalse(any(hosting_package["controls"].values()))
        operations_package = response["workforce_blueprint"]["operations_execution_package"]
        self.assertEqual(operations_package["authority"], "NONE")
        self.assertEqual(operations_package["operations_readiness_report"]["status"], "NOT READY")
        self.assertFalse(any(operations_package["controls"].values()))
        lifecycle = response["workforce_blueprint"]["agent_lifecycle_package"]
        self.assertEqual(lifecycle["authority"], "NONE")
        self.assertFalse(any(lifecycle["controls"].values()))
        self.assertTrue(all(profile["creation_status"] == "SIMULATED_NOT_CREATED"
                    for profile in lifecycle["agent_profiles"]))
        assignment_package = response["workforce_blueprint"]["assignment_recommendation_package"]
        self.assertEqual(assignment_package["authority"], "NONE")
        self.assertFalse(any(assignment_package["controls"].values()))
        self.assertEqual(assignment_package["assignment_readiness"]["status"], "NOT_READY")
        testing_package = response["workforce_blueprint"]["testing_execution_package"]
        self.assertEqual(testing_package["unit_test_report"]["execution_status"], "NOT_EXECUTED")
        self.assertFalse(any(testing_package["controls"].values()))
        self.assertIn("project_delivery_package", response["workforce_blueprint"])
        self.assertFalse(any(response["workforce_blueprint"]["project_delivery_package"]["controls"].values()))
        self.assertEqual(response["workforce_blueprint"]["requirement"]["title"], body.title)
        self.assertEqual(response["workforce_blueprint"]["requirement"]["technology_changes"], [".NET", "Angular"])
        self.assertEqual(response["workforce_blueprint"]["technical_delivery_package"]["artifacts"]["executive_assessment"]["priority"], "High")
        self.assertEqual(response["workforce_blueprint"]["technical_delivery_package"]["artifacts"]["executive_assessment"]["priority_basis"], "Requester-selected priority")
        self.assertEqual(response["workforce_blueprint"]["lifecycle_actions"]["mode"], "BLUEPRINT_ONLY")
        self.assertFalse(response["workforce_blueprint"]["lifecycle_actions"]["agent_records_created"])
        self.assertFalse(response["workforce_blueprint"]["technical_delivery_package"]["controls"]["code_generated"])
        self.assertFalse(response["workforce_blueprint"]["technical_delivery_package"]["controls"]["infrastructure_created"])
        self.assertFalse(response["workforce_blueprint"]["technical_delivery_package"]["controls"]["deployed"])
        db.execute.assert_not_called()
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()