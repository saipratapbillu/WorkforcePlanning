import unittest
import uuid
from unittest.mock import Mock

from fastapi import HTTPException

from app.api.org_mappings import OrganizationMapping, _validate_mapping
from app.security.org_scope import organization_mapping_issues


class OrganizationMappingAdminTests(unittest.TestCase):
    def test_valid_company_department_position_path_is_accepted(self):
        ids = [uuid.uuid4() for _ in range(4)]
        user_id, company_id, department_id, position_id = ids
        db = Mock()
        db.execute.return_value.scalar_one_or_none.return_value = user_id

        _validate_mapping(db, user_id, OrganizationMapping(
            company_id=company_id,
            department_id=department_id,
            position_id=position_id,
        ))

        db.execute.assert_called_once()

    def test_wrong_parent_relationship_is_rejected(self):
        ids = [uuid.uuid4() for _ in range(4)]
        user_id, company_id, department_id, position_id = ids
        db = Mock()
        db.execute.return_value.scalar_one_or_none.return_value = None

        with self.assertRaises(HTTPException) as raised:
            _validate_mapping(db, user_id, OrganizationMapping(
                company_id=company_id,
                department_id=department_id,
                position_id=position_id,
            ))

        self.assertEqual(raised.exception.status_code, 422)

    def test_mapping_diagnostics_remain_available_as_optional_metadata(self):
        issues = {
            "MissingCompany": 1,
            "MissingDepartment": 1,
            "MissingPosition": 1,
            "DepartmentCompanyMismatch": 0,
            "PositionDepartmentMismatch": 0,
        }
        db = Mock()
        db.execute.return_value.mappings.return_value.one.return_value = issues

        self.assertEqual(organization_mapping_issues(db), issues)


if __name__ == "__main__":
    unittest.main()