import ast
import unittest
from collections import Counter
from pathlib import Path

from fastapi.routing import APIRoute

from app.api.runtime import _worker_agent
from app.main import app
from app.security.dependencies import get_current_user
from app.security.middleware import AUTHENTICATED_PREFIXES, forbidden_for_role
from app.security.roles import has_role

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

    def test_registered_route_matrix_confines_reviewers_and_worker_credentials(self):
        def dependency_calls(dependant):
            calls = []
            if dependant.call is not None:
                calls.append(dependant.call)
            for child in dependant.dependencies:
                calls.extend(dependency_calls(child))
            return calls

        routes = [route for route in app.routes if isinstance(route, APIRoute)]
        self.assertGreater(len(routes), 0)
        covered = set()
        for route in routes:
            for method in route.methods or ():
                covered.add((method, route.path))
            calls = dependency_calls(route.dependant)
            route_roles = []
            for call in calls:
                if getattr(call, "__name__", None) == "checker":
                    route_roles.extend(
                        cell.cell_contents
                        for cell in (call.__closure__ or ())
                        if isinstance(cell.cell_contents, tuple)
                    )
            if route.path.startswith("/runtime/worker/"):
                self.assertIn(_worker_agent, calls, route.path)
            if route.path.startswith("/runtime/reviews/"):
                reviewer_guard = False
                for call in calls:
                    if getattr(call, "__name__", None) != "checker":
                        continue
                    closure_values = [
                        cell.cell_contents for cell in (call.__closure__ or ())
                    ]
                    reviewer_guard |= ("RUNTIME_REVIEWER",) in closure_values
                self.assertTrue(reviewer_guard, route.path)
                self.assertFalse(forbidden_for_role(route.path, "RUNTIME_REVIEWER"), route.path)
            else:
                self.assertFalse(
                    any(has_role("RUNTIME_REVIEWER", *roles) for roles in route_roles),
                    route.path,
                )
                if get_current_user in calls and route.path not in {"/auth/me", "/auth/logout"}:
                    if route.path.startswith(AUTHENTICATED_PREFIXES):
                        self.assertTrue(forbidden_for_role(route.path, "RUNTIME_REVIEWER"), route.path)
                    else:
                        self.assertTrue(route_roles, f"unprotected authenticated route {route.path}")

        self.assertEqual(len(covered), sum(len(route.methods or ()) for route in routes))


if __name__ == "__main__":
    unittest.main()
