import unittest
import xml.etree.ElementTree as ET

from app.api.workforce import FactoryBlueprintRequest, create_diagram_plan
from app.services.agent_factory import build_factory_blueprint
from app.services.diagram_factory import DIAGRAM_TYPES, build_diagram_package


class DiagramFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = build_factory_blueprint(
            title="Secure analytics portal",
            description="Create a customer analytics portal with SQL, identity, monitoring, and support.",
            technology_changes=["React", "Python"], priority="High",
        )
        cls.package = build_diagram_package(cls.blueprint)

    def test_all_nine_diagram_types_have_content_and_views(self):
        self.assertEqual(set(self.package["diagrams"]), set(DIAGRAM_TYPES))
        self.assertEqual(len(DIAGRAM_TYPES), 9)
        for kind, diagram in self.package["diagrams"].items():
            self.assertGreater(diagram["node_count"], 1, kind)
            self.assertGreater(diagram["edge_count"], 0, kind)
            self.assertTrue(diagram["dependency_map"] and diagram["relationship_map"] and diagram["swimlane_view"]["lanes"])
            self.assertLessEqual(len(diagram["executive_view"]["nodes"]), 6)
            self.assertGreaterEqual(len(diagram["technical_view"]["nodes"]), len(diagram["executive_view"]["nodes"]))

    def test_layout_places_nodes_without_overlap(self):
        for kind, diagram in self.package["diagrams"].items():
            boxes = [(n["x"], n["y"]) for n in diagram["technical_view"]["nodes"]]
            self.assertEqual(len(boxes), len(set(boxes)), kind)

    def test_svg_and_visio_exports_are_well_formed_text(self):
        for diagram in self.package["diagrams"].values():
            for view in ("technical_view", "executive_view"):
                svg = ET.fromstring(diagram[view]["svg"])
                self.assertTrue(svg.tag.endswith("svg"))
                visio = ET.fromstring(diagram[view]["visio_xml"])
                self.assertTrue(visio.tag.endswith("VisioDocument"))

    def test_png_pdf_pptx_are_plans_only_and_nothing_executes(self):
        for fmt in ("png", "pdf", "powerpoint"):
            self.assertEqual(self.package["export_formats"][fmt]["status"], "NOT_RENDERED")
        self.assertEqual(self.package["status"], "PLANNING_ONLY")
        self.assertEqual(self.package["authority"], "NONE")
        self.assertFalse(self.package["action_allowed"])
        self.assertFalse(self.package["persistence"])
        self.assertFalse(any(self.package["controls"].values()))

    def test_empty_input_and_api(self):
        empty = build_diagram_package(None)
        self.assertEqual(set(empty["diagrams"]), set(DIAGRAM_TYPES))
        result = create_diagram_plan(FactoryBlueprintRequest(
            title="Secure analytics portal", description="Create a secure portal with audited API access."))
        self.assertEqual(result["status"], "PLANNING_ONLY")


if __name__ == "__main__":
    unittest.main()
