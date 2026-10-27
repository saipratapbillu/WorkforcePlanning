import unittest
from unittest.mock import Mock, patch

from app.services.execution_adapters import (
    LocalEnvironmentSecretResolver,
    SecretNotFound,
    _validated_endpoint,
    probe_provider,
)


class ExecutionAdapterTests(unittest.TestCase):
    def test_local_secret_reference_resolves_only_environment_variable_names(self):
        with patch.dict("os.environ", {"OPENAI_TEST_KEY": "do-not-return-this"}):
            self.assertEqual(LocalEnvironmentSecretResolver().resolve("env://OPENAI_TEST_KEY"), "do-not-return-this")
        with self.assertRaises(SecretNotFound):
            LocalEnvironmentSecretResolver().resolve("do-not-store-secret-here")

    def test_provider_endpoint_hostname_is_allowlisted(self):
        self.assertEqual(
            _validated_endpoint("OPENAI", "https://api.openai.com"),
            "https://api.openai.com",
        )
        with self.assertRaises(ValueError):
            _validated_endpoint("OPENAI", "https://api.openai.com.attacker.invalid")
        with self.assertRaises(ValueError):
            _validated_endpoint("OPENAI", "http://api.openai.com")

    @patch("app.services.execution_adapters.requests.get")
    def test_probe_reports_healthy_only_after_real_success_response(self, get):
        get.return_value = Mock(status_code=200)

        result = probe_provider("OPENAI", "https://api.openai.com", "unused", "private-api-key")

        self.assertEqual(result.status, "Healthy")
        self.assertEqual(result.http_status, 200)
        self.assertNotIn("private-api-key", result.details)
        get.assert_called_once()
        self.assertFalse(get.call_args.kwargs["allow_redirects"])
        self.assertEqual(get.call_args.kwargs["timeout"], (3.05, 5))

    @patch("app.services.execution_adapters.requests.get")
    def test_authentication_failure_is_not_healthy_and_body_is_not_disclosed(self, get):
        response = Mock(status_code=401, text="provider included credential echo")
        get.return_value = response

        result = probe_provider("ANTHROPIC", "https://api.anthropic.com", "unused", "private-api-key")

        self.assertEqual(result.status, "Unhealthy")
        self.assertEqual(result.http_status, 401)
        self.assertNotIn(response.text, result.details)
        self.assertNotIn("private-api-key", result.details)


if __name__ == "__main__":
    unittest.main()
