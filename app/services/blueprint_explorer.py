"""Read-only navigation, dependency, search, and impact views over generated factory packages."""

from __future__ import annotations

import json
from typing import Any

# (package_id, label, blueprint key; None = workforce blueprint root sections)
PACKAGES = (
    ("requirement", "Requirement", "requirement"),
    ("workforce_blueprint", "Workforce Blueprint", None),
    ("agent_lifecycle", "Agent Lifecycle Package", "agent_lifecycle_package"),
    ("assignment", "Assignment Recommendation Package", "assignment_recommendation_package"),
    ("approval_sandbox", "Approval Sandbox Package", "approval_sandbox_package"),
    ("technical_delivery", "Technical Delivery Package", "technical_delivery_package"),
    ("project", "Project Package", "project_delivery_package"),
    ("delivery", "Delivery Package", "delivery_execution_package"),
    ("code", "Code Package", "code_execution_package"),
    ("testing", "Testing Package", "testing_execution_package"),
    ("build", "Build Package", "build_execution_package"),
    ("deployment", "Deployment Package", "deployment_execution_package"),
    ("hosting", "Hosting Package", "hosting_execution_package"),
    ("operations", "Operations Package", "operations_execution_package"),
    ("autonomy", "Autonomy Package", "autonomy_execution_package"),
    ("enterprise_architecture", "Enterprise Architecture Package", "autonomous_enterprise_package"),
)
# (upstream, downstream): downstream consumes upstream output.
DEPENDENCIES = (
    ("requirement", "workforce_blueprint"), ("requirement", "technical_delivery"),
    ("workforce_blueprint", "agent_lifecycle"), ("workforce_blueprint", "assignment"),
    ("agent_lifecycle", "assignment"), ("technical_delivery", "project"),
    ("project", "delivery"), ("technical_delivery", "code"), ("code", "testing"),
    ("delivery", "testing"), ("code", "build"), ("testing", "build"),
    ("project", "build"), ("build", "deployment"), ("testing", "deployment"),
    ("deployment", "hosting"), ("technical_delivery", "hosting"),
    ("hosting", "operations"), ("delivery", "operations"),
    ("assignment", "approval_sandbox"), ("operations", "approval_sandbox"),
    ("approval_sandbox", "autonomy"), ("operations", "autonomy"), ("agent_lifecycle", "autonomy"),
    ("autonomy", "enterprise_architecture"),
)
LABELS = {pid: label for pid, label, _ in PACKAGES}
_NON_WORKFORCE_KEYS = {key for _, _, key in PACKAGES if key}
_NON_WORKFORCE_KEYS |= {"executive_command_center", "blueprint_explorer"}
_FLAGS = ("authority", "action_allowed", "persistence", "status", "package")


def _count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_count(v) for v in value.values()) or 0
    if isinstance(value, list):
        return sum(_count(v) for v in value) or 0
    return 1


def _paths(value: Any, prefix: str = "", depth: int = 0, limit: int = 3) -> list[str]:
    if not isinstance(value, dict) or depth >= limit:
        return []
    found = []
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        found.append(path)
        found.extend(_paths(child, path, depth + 1, limit))
    return found


def _package_content(blueprint: dict[str, Any], key: str | None) -> Any:
    if key is None:
        return {k: v for k, v in blueprint.items() if k not in _NON_WORKFORCE_KEYS}
    return blueprint.get(key)


def _closure(start: str, edges: dict[str, list[str]]) -> list[str]:
    seen: list[str] = []
    stack = list(edges.get(start, []))
    while stack:
        node = stack.pop()
        if node not in seen:
            seen.append(node)
            stack.extend(edges.get(node, []))
    return sorted(seen)


def analyze_impact(explorer: dict[str, Any], package_id: str) -> dict[str, Any] | None:
    """Return upstream/downstream packages for a package, or None if unknown."""
    if package_id not in LABELS:
        return None
    downstream: dict[str, list[str]] = {}
    upstream: dict[str, list[str]] = {}
    for src, dst in explorer["dependency_graph"]["edges_as_pairs"]:
        downstream.setdefault(src, []).append(dst)
        upstream.setdefault(dst, []).append(src)
    direct = sorted(downstream.get(package_id, []))
    affected = _closure(package_id, downstream)
    return {
        "package_id": package_id, "label": LABELS[package_id],
        "direct_dependents": direct, "all_affected_packages": affected,
        "depends_on": sorted(_closure(package_id, upstream)),
        "affected_count": len(affected),
        "guidance": "Changes to this package require regenerating and re-reviewing every affected package.",
        "read_only": True,
    }


def search_packages(explorer: dict[str, Any], query: str, limit: int = 50) -> list[dict[str, str]]:
    """Case-insensitive search over package names and section paths."""
    needle = (query or "").strip().lower()
    if not needle:
        return []
    results = []
    for item in explorer["search_index"]:
        if needle in item["path"].lower() or needle in item["label"].lower():
            results.append(item)
            if len(results) >= limit:
                break
    return results


def build_blueprint_explorer(blueprint: dict[str, Any] | None) -> dict[str, Any]:
    """Describe generated packages for navigation; never mutates or executes anything."""
    bp = blueprint if isinstance(blueprint, dict) else {}
    nodes, tree_children, summaries, metrics, index = [], [], [], [], []
    for pid, label, key in PACKAGES:
        content = _package_content(bp, key)
        present = bool(content)
        sections = list(content.keys()) if isinstance(content, dict) else []
        nodes.append({"id": pid, "label": label, "present": present})
        tree_children.append({"id": pid, "label": label, "present": present,
                              "children": [{"id": f"{pid}.{s}", "label": s} for s in sections]})
        meta = {k: content.get(k) for k in _FLAGS if isinstance(content, dict) and k in content}
        controls = content.get("controls") if isinstance(content, dict) else None
        summaries.append({"package_id": pid, "label": label, "present": present,
                          "status": meta.get("status"), "authority": meta.get("authority"),
                          "action_allowed": meta.get("action_allowed"), "persistence": meta.get("persistence"),
                          "sections": sections[:25]})
        metrics.append({"package_id": pid, "present": present, "section_count": len(sections),
                        "item_count": _count(content) if present else 0,
                        "all_controls_false": (not any(controls.values())) if isinstance(controls, dict) else None})
        index.append({"package_id": pid, "label": label, "path": pid})
        index.extend({"package_id": pid, "label": label, "path": f"{pid}.{p}"} for p in _paths(content))

    edges = [{"from": a, "to": b, "relationship": "feeds"} for a, b in DEPENDENCIES]
    graph = {"nodes": nodes, "edges": edges, "edges_as_pairs": [list(e) for e in DEPENDENCIES], "acyclic": True}
    relationships = [{"package_id": pid, "label": LABELS[pid],
                      "depends_on": sorted(a for a, b in DEPENDENCIES if b == pid),
                      "feeds": sorted(b for a, b in DEPENDENCIES if a == pid)} for pid in LABELS]
    version = (bp.get("build_execution_package", {}).get("version_plan", {}) or {}).get("semantic_version")
    version_history = {"current": {"generation": "TRANSIENT_ON_DEMAND", "proposed_release_version": version},
                       "entries": [], "history_available": False,
                       "basis": "Packages are generated on demand and not persisted, so no prior versions exist."}
    explorer = {
        "package": "Blueprint Explorer",
        "status": "READ_ONLY_VIEW",
        "authority": "NONE", "action_allowed": False, "persistence": False,
        "tree_navigation": {"id": "blueprint", "label": bp.get("requirement", {}).get("title") or "Blueprint",
                            "children": tree_children},
        "dependency_graph": graph,
        "relationship_view": relationships,
        "artifact_summary": summaries,
        "package_metrics": {"packages_total": len(PACKAGES), "packages_present": sum(n["present"] for n in nodes),
                            "missing_packages": [n["id"] for n in nodes if not n["present"]], "per_package": metrics},
        "search_index": index,
        "impact_analysis": {pid: analyze_impact({"dependency_graph": graph}, pid) for pid in LABELS},
        "version_history": version_history,
        "controls": {"packages_modified": False, "files_written": False, "actions_performed": False,
                     "runtime_started": False, "persistence": False},
    }
    outline = ["# Blueprint Explorer Export", ""]
    for child in tree_children:
        outline.append(f"- {child['label']}{'' if child['present'] else ' (not generated)'}")
        outline.extend(f"  - {c['label']}" for c in child["children"])
    exportable = {k: v for k, v in explorer.items() if k not in ("search_index",)}
    explorer["export_view"] = {
        "formats": ["json", "markdown"], "file_written": False,
        "json": json.dumps(exportable, default=str, sort_keys=True),
        "markdown": "\n".join(outline),
    }
    return explorer
