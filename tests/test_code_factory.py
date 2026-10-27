import json
import unittest
from pydantic import ValidationError

from app.services.code_factory import BACKEND_LANGUAGES, build_code_package
from app.services.agent_factory import build_factory_blueprint
from app.api.workforce import FactoryCodePackageRequest, create_agent_code_package


class CodeFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = build_factory_blueprint(
            title="Secure analytics portal",
            description="Create a customer portal and API with audited analytics data.",
            technology_changes=["Angular", ".NET"],
            priority="High",
        )["technical_delivery_package"]

    def test_package_contains_all_delivery_asset_families_without_execution(self):
        package = build_code_package(self.blueprint, "python")
        paths = {item["path"] for item in package["files"]}

        self.assertIn("backend/app/main.py", paths)
        self.assertIn("backend/app/entities.py", paths)
        self.assertIn("backend/blueprint.json", paths)
        self.assertIn("database/schema.sql", paths)
        self.assertIn("api/openapi.json", paths)
        self.assertIn("frontend/src/App.tsx", paths)
        self.assertIn("security/SECURITY.md", paths)
        self.assertIn("tests/security/test_auth_fails_closed.py", paths)
        self.assertIn("devops/Dockerfile", paths)
        self.assertIn("devops/infra/main.tf", paths)
        dockerfile = next(item["content"] for item in package["files"] if item["path"] == "devops/Dockerfile")
        self.assertIn("COPY backend/requirements.txt", dockerfile)
        self.assertIn("delivery/blueprint-summary.json", paths)
        self.assertIn("CREATE TABLE IF NOT EXISTS data_source", next(
            item["content"] for item in package["files"] if item["path"] == "database/schema.sql"))
        ui_manifest = json.loads(next(item["content"] for item in package["files"]
                                      if item["path"] == "frontend/src/generatedBlueprint.json"))
        self.assertTrue(ui_manifest["screens"])
        self.assertFalse(package["controls"]["files_written"])
        self.assertFalse(package["controls"]["code_executed"])
        self.assertFalse(package["controls"]["deployed"])
        self.assertFalse(package["controls"]["infrastructure_created"])
        self.assertFalse(package["controls"]["secrets_included"])

    def test_supported_backend_languages_produce_distinct_scaffolds(self):
        packages = {language: build_code_package(self.blueprint, language)
                    for language in BACKEND_LANGUAGES}
        files_by_language = {
            language: {item["path"]: item["content"] for item in package["files"]}
            for language, package in packages.items()
        }

        self.assertIn("backend/app/main.py", files_by_language["python"])
        self.assertIn("backend/src/Controllers/RequirementsController.cs", files_by_language["dotnet"])
        self.assertIn("backend/src/routes/requirements.js", files_by_language["node"])
        self.assertNotEqual(files_by_language["python"], files_by_language["dotnet"])
        self.assertNotEqual(files_by_language["node"], files_by_language["dotnet"])
        self.assertIn("Identity provider validation is not configured", files_by_language["python"]["backend/app/security.py"])
        self.assertIn("Identity provider validation is not configured", files_by_language["node"]["backend/src/security/auth.js"])
        self.assertIn("FailClosedAuthenticationHandler", files_by_language["dotnet"]["backend/src/Program.cs"])
        self.assertIn("tenant_id UUID NOT NULL", files_by_language["python"]["database/schema.sql"])

    def test_openapi_is_valid_and_generated_sql_is_non_destructive(self):
        package = build_code_package(self.blueprint, "node")
        files = {item["path"]: item["content"] for item in package["files"]}
        spec = json.loads(files["api/openapi.json"])

        self.assertEqual(spec["openapi"], "3.1.0")
        self.assertIn("/api/v1/requirements", spec["paths"])
        self.assertIn("/api/v1/requirements/{requirement_id}", spec["paths"])
        create_operation = spec["paths"]["/api/v1/requirements"]["post"]
        self.assertEqual(create_operation["requestBody"]["content"]["application/json"]["schema"]["$ref"],
                 "#/components/schemas/RequirementCreate")
        self.assertIn("RequirementSummary", spec["components"]["schemas"])
        for path_item in spec["paths"].values():
            for operation in path_item.values():
                for response in operation.get("responses", {}).values():
                    schema_ref = response.get("content", {}).get("application/json", {}).get("schema", {}).get("$ref")
                    if schema_ref:
                        self.assertIn(schema_ref.rsplit("/", 1)[-1], spec["components"]["schemas"])
        self.assertIn("CREATE TABLE IF NOT EXISTS", files["database/schema.sql"])
        self.assertIn("FOREIGN KEY (tenant_id, requirement_id)", files["database/schema.sql"])
        self.assertIn("FOREIGN KEY (tenant_id, project_id)", files["database/schema.sql"])
        self.assertNotIn("DROP TABLE", files["database/schema.sql"].upper())
        self.assertNotIn("INSERT INTO", files["database/seed.sql"].upper())

    def test_project_title_is_not_injected_as_source_or_file_path(self):
        malicious_blueprint = build_factory_blueprint(
            title="../etc/passwd; import os",
            description="Create a secure portal requirement with a bounded scope.",
        )["technical_delivery_package"]

        package = build_code_package(malicious_blueprint, "python")
        paths = [item["path"] for item in package["files"]]
        all_contents = "\n".join(item["content"] for item in package["files"])

        self.assertTrue(all(not path.startswith("/") and ".." not in path.split("/") for path in paths))
        self.assertNotIn("import os", all_contents)
        self.assertNotIn("../etc/passwd", all_contents)

    def test_only_allowlisted_backend_languages_are_accepted(self):
        with self.assertRaises(ValueError):
            build_code_package(self.blueprint, "bash")

    def test_authorized_api_contract_returns_artifacts_without_database_or_side_effects(self):
        request = FactoryCodePackageRequest(
            title="Secure web portal",
            description="Create a secure portal with audited requirement management.",
            backend_language="python",
        )

        package = create_agent_code_package(request)

        self.assertEqual(package["backend_language"], "python")
        self.assertGreater(package["file_count"], 20)
        self.assertFalse(any(package["controls"].values()))

    def test_api_rejects_unbounded_technology_labels(self):
        with self.assertRaises(ValidationError):
            FactoryCodePackageRequest(
                title="Bounded request", description="This description is long enough for validation.",
                technology_changes=["x" * 101], backend_language="python",
            )

    def test_package_rejects_invalid_blueprint_table_identifiers(self):
        invalid_blueprint = {"artifacts": {
            "database_blueprint": {"tables": [{"table": "records; DROP TABLE users"}]},
            "api_catalog": {"endpoints": []}, "ui_blueprint": {},
        }}

        with self.assertRaises(ValueError):
            build_code_package(invalid_blueprint, "python")


if __name__ == "__main__":
    unittest.main()