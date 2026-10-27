import ast
import unittest
from collections import Counter
from pathlib import Path

from app.main import app

API_DIR = Path(__file__).resolve().parents[1] / "app" / "api"


class RouteUniquenessTests(unittest.TestCase):
    def test_no_method_path_is_registered_twice(self):
        counts = Counter((method, route.path) for route in app.routes
                         for method in (getattr(route, "methods", None) or ()))
        self.assertEqual([key for key, n in counts.items() if n > 1], [])

    def test_operations_plan_endpoint_registered_once(self):
        matches = [r for r in app.routes
                   if getattr(r, "path", None) == "/workforce/factory/operations-plan"
                   and "POST" in (r.methods or ())]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].endpoint.__name__, "create_operations_plan")

    def test_no_duplicate_route_handler_names_in_api_modules(self):
        duplicates = []
        for path in API_DIR.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = Counter(node.name for node in tree.body
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                                    and isinstance(d.func.value, ast.Name) and d.func.value.id == "router"
                                    for d in node.decorator_list))
            duplicates += [f"{path.name}:{name}" for name, n in names.items() if n > 1]
        self.assertEqual(duplicates, [])


if __name__ == "__main__":
    unittest.main()
