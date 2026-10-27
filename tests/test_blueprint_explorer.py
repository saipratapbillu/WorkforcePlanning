import json
import unittest

from fastapi import HTTPException

from app.api.workforce import BlueprintExplorerRequest, create_blueprint_explorer
from app.services.agent_factory import build_factory_blueprint
from app.services.blueprint_explorer import (
    DEPENDENCIES, LABELS, analyze_impact, build_blueprint_explorer, search_packages,
)


class BlueprintExplorerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = build_factory_blueprint(
            title="Secure analytics portal",
            description="Create a customer analytics portal with SQL, identity, monitoring, and support.",
            technology_changes=["React", "Python"], priority="High",
        )
        cls.explorer = build_blueprint_explorer(cls.blueprint)

    def test_tree_lists_all_fifteen_plus_workforce_packages_and_all_are_present(self):
        children = self.explorer["tree_navigation"]["children"]
        self.assertEqual(len(children), 16)
        self.assertTrue(all(child["present"] for child in children), [c["id"] for c in children if not c["present"]])
        self.assertEqual(self.explorer["package_metrics"]["missing_packages"], [])
        self.assertEqual(len(self.explorer["artifact_summary"]), 16)

    def test_dependency_graph_is_acyclic_and_consistent(self):
        ids = set(LABELS)
        self.assertTrue(all(a in ids and b in ids for a, b in DEPENDENCIES))
        upstream = {}
        for a, b in DEPENDENCIES:
            upstream.setdefault(b, set()).add(a)
        for pid in ids:
            self.assertNotIn(pid, analyze_impact(self.explorer, pid)["all_affected_packages"])
        self.assertEqual(len(self.explorer["dependency_graph"]["edges"]), len(DEPENDENCIES))

    def test_impact_analysis_follows_transitive_dependents(self):
        impact = analyze_impact(self.explorer, "build")
        for expected in ("deployment", "hosting", "operations", "approval_sandbox", "autonomy", "enterprise_architecture"):
            self.assertIn(expected, impact["all_affected_packages"])
        self.assertNotIn("code", impact["all_affected_packages"])
        self.assertEqual(analyze_impact(self.explorer, "enterprise_architecture")["all_affected_packages"], [])
        self.assertIsNone(analyze_impact(self.explorer, "unknown"))

    def test_search_and_export(self):
        self.assertTrue(search_packages(self.explorer, "rollback"))
        self.assertEqual(search_packages(self.explorer, "  "), [])
        export = self.explorer["export_view"]
        self.assertIn("tree_navigation", json.loads(export["json"]))
        self.assertIn("Hosting Package", export["markdown"])
        self.assertFalse(export["file_written"])

    def test_version_history_is_honest_and_read_only(self):
        self.assertFalse(self.explorer["version_history"]["history_available"])
        self.assertEqual(self.explorer["authority"], "NONE")
        self.assertFalse(self.explorer["action_allowed"])
        self.assertFalse(self.explorer["persistence"])
        self.assertFalse(any(self.explorer["controls"].values()))

    def test_empty_input_and_blueprint_integration(self):
        empty = build_blueprint_explorer(None)
        self.assertEqual(empty["package_metrics"]["packages_present"], 0)
        self.assertEqual(self.blueprint["blueprint_explorer"]["status"], "READ_ONLY_VIEW")

    def test_api_supports_search_and_impact(self):
        body = BlueprintExplorerRequest(title="Secure analytics portal",
            description="Create a secure portal with audited API access.", query="rollback", impact_of="code")
        result = create_blueprint_explorer(body)
        self.assertTrue(result["search_results"])
        self.assertIn("testing", result["requested_impact"]["all_affected_packages"])
        with self.assertRaises(HTTPException):
            create_blueprint_explorer(BlueprintExplorerRequest(title="Secure analytics portal",
                description="Create a secure portal with audited API access.", impact_of="nope"))


if __name__ == "__main__":
    unittest.main()
