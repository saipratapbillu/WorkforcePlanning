import unittest

from app.api.errors import api_error_code, api_error_response


class ApiErrorResponseTests(unittest.TestCase):
    def test_error_response_has_stable_envelope_and_legacy_detail(self):
        response = api_error_response(404, "not_found", "Project not found", detail="Project not found")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.body, b'{"success":false,"error":{"code":"not_found","message":"Project not found"},"detail":"Project not found"}')

    def test_validation_details_are_json_encoded(self):
        response = api_error_response(
            422,
            "validation_error",
            "Request validation failed",
            detail=[{"loc": ("body", "name"), "msg": "Field required"}],
        )

        self.assertIn(b'"loc":["body","name"]', response.body)

    def test_http_status_maps_to_error_code(self):
        self.assertEqual(api_error_code(401), "authentication_required")
        self.assertEqual(api_error_code(500), "request_failed")


if __name__ == "__main__":
    unittest.main()