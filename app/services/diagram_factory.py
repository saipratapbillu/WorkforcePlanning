"""Diagram specifications and text-based exports from blueprint packages; no rendering engine is run."""

from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape, quoteattr

DIAGRAM_TYPES = ("solution", "application", "database", "api", "security",
                 "deployment", "hosting", "operations", "enterprise")
NODE_W, NODE_H, X_GAP, Y_GAP, LANE_H = 180, 56, 80, 30, 120
EXECUTIVE_NODE_LIMIT = 6


def _slug(text: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in text).strip("_")[:48] or "node"


class _Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, str]] = {}
        self.edges: list[dict[str, str]] = []

    def node(self, label: str, lane: str, prefix: str = "n") -> str:
        nid = f"{prefix}_{_slug(label)}"
        self.nodes.setdefault(nid, {"id": nid, "label": str(label)[:60], "lane": lane})
        return nid

    def edge(self, a: str, b: str, label: str = "") -> None:
        if a != b and a in self.nodes and b in self.nodes and not any(e["from"] == a and e["to"] == b for e in self.edges):
            self.edges.append({"from": a, "to": b, "label": label})


def _layout(nodes: list[dict[str, Any]], edges: list[dict[str, str]], lanes: list[str]) -> dict[str, Any]:
    """Layered auto layout: column = longest path from a source; row = order within lane/column."""
    layer = {n["id"]: 0 for n in nodes}
    for _ in range(len(nodes)):
        changed = False
        for e in edges:
            if e["from"] in layer and e["to"] in layer and layer[e["to"]] < layer[e["from"]] + 1:
                layer[e["to"]] = layer[e["from"]] + 1
                changed = True
        if not changed:
            break
    slots: dict[tuple[int, str], int] = {}
    placed = []
    for n in nodes:
        lane = n["lane"] if n["lane"] in lanes else lanes[0]
        row = slots.get((layer[n["id"]], lane), 0)
        slots[(layer[n["id"]], lane)] = row + 1
        placed.append({**n, "lane": lane, "layer": layer[n["id"]], "row": row})
    heights = {lane: max(LANE_H, 20 + (NODE_H + Y_GAP) * max([r for (_, ln), r in slots.items() if ln == lane] or [1]))
               for lane in lanes}
    lane_y, offset = {}, 0
    for lane in lanes:
        lane_y[lane] = 40 + offset
        offset += heights[lane]
    for p in placed:
        p["x"] = 40 + p["layer"] * (NODE_W + X_GAP)
        p["y"] = lane_y[p["lane"]] + p["row"] * (NODE_H + Y_GAP)
    return {"nodes": placed, "width": 80 + (max(layer.values(), default=0) + 1) * (NODE_W + X_GAP),
            "height": 60 + offset, "lanes": [{"lane": l, "y": lane_y[l], "height": heights[l]} for l in lanes]}


def _svg(title: str, layout: dict[str, Any], edges: list[dict[str, str]]) -> str:
    pos = {n["id"]: n for n in layout["nodes"]}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{layout["width"]}" height="{layout["height"] + 30}" '
             f'viewBox="0 0 {layout["width"]} {layout["height"] + 30}" role="img">',
             f"<title>{escape(title)}</title>",
             '<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#444"/></marker></defs>']
    for lane in layout["lanes"]:
        parts.append(f'<rect x="0" y="{lane["y"] - 10}" width="{layout["width"]}" height="{lane["height"]}" fill="#f6f8fa" stroke="#d0d7de"/>')
        parts.append(f'<text x="6" y="{lane["y"] + 4}" font-size="11" fill="#57606a">{escape(lane["lane"])}</text>')
    for e in edges:
        a, b = pos.get(e["from"]), pos.get(e["to"])
        if a and b:
            parts.append(f'<line x1="{a["x"] + NODE_W}" y1="{a["y"] + NODE_H // 2}" x2="{b["x"]}" y2="{b["y"] + NODE_H // 2}" stroke="#444" marker-end="url(#a)"/>')
    for n in layout["nodes"]:
        parts.append(f'<rect x="{n["x"]}" y="{n["y"]}" width="{NODE_W}" height="{NODE_H}" rx="6" fill="#fff" stroke="#0969da"/>')
        parts.append(f'<text x="{n["x"] + NODE_W // 2}" y="{n["y"] + NODE_H // 2 + 4}" font-size="12" text-anchor="middle">{escape(n["label"])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _visio_xml(title: str, layout: dict[str, Any], edges: list[dict[str, str]]) -> str:
    ids = {n["id"]: i + 1 for i, n in enumerate(layout["nodes"])}
    shapes = []
    for n in layout["nodes"]:  # Visio origin is bottom-left, units are inches.
        x, y = (n["x"] + NODE_W / 2) / 96, (layout["height"] - n["y"] - NODE_H / 2) / 96
        shapes.append(f'<Shape ID="{ids[n["id"]]}" Type="Shape" Name={quoteattr(n["label"])}>'
                      f'<XForm><PinX>{x:.3f}</PinX><PinY>{y:.3f}</PinY><Width>{NODE_W / 96:.3f}</Width><Height>{NODE_H / 96:.3f}</Height></XForm>'
                      f'<Text>{escape(n["label"])}</Text></Shape>')
    base = len(ids)
    connects = []
    for i, e in enumerate(edges):
        if e["from"] in ids and e["to"] in ids:
            cid = base + i + 1
            shapes.append(f'<Shape ID="{cid}" Type="Shape" Name="Connector"><Text>{escape(e["label"])}</Text></Shape>')
            connects.append(f'<Connect FromSheet="{cid}" FromCell="BeginX" ToSheet="{ids[e["from"]]}" ToCell="PinX"/>'
                            f'<Connect FromSheet="{cid}" FromCell="EndX" ToSheet="{ids[e["to"]]}" ToCell="PinX"/>')
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<VisioDocument xmlns="http://schemas.microsoft.com/visio/2003/core" xml:space="preserve">'
            f'<Pages><Page ID="0" Name={quoteattr(title)}><Shapes>{"".join(shapes)}</Shapes>'
            f'<Connects>{"".join(connects)}</Connects></Page></Pages></VisioDocument>')


def _entity_names(entities: list[Any]) -> list[str]:
    return [e.get("name") if isinstance(e, dict) else str(e) for e in entities if e]


def _build_graph(kind: str, bp: dict[str, Any]) -> tuple[_Graph, list[str]]:
    g = _Graph()
    art = (bp.get("technical_delivery_package") or {}).get("artifacts", {})
    if kind == "solution":
        lanes = ["Business", "Delivery", "Platform"]
        chain = [("Requirement", "Business"), ("Workforce Blueprint", "Business"), ("Technical Design", "Delivery"),
                 ("Project and Delivery Plan", "Delivery"), ("Code, Test and Build", "Delivery"),
                 ("Deployment and Hosting", "Platform"), ("Operations", "Platform")]
        ids = [g.node(label, lane, "s") for label, lane in chain]
        for a, b in zip(ids, ids[1:]):
            g.edge(a, b, "feeds")
    elif kind == "application":
        lanes = ["Experience", "Application", "Integration"]
        comps = (art.get("architecture_blueprint") or {}).get("components", [])
        ids = []
        for c in comps:
            name = c.get("name", "Component") if isinstance(c, dict) else str(c)
            low = name.lower()
            lane = "Experience" if any(t in low for t in ("user", "experience", "web")) else \
                   "Integration" if any(t in low for t in ("integration", "external", "event")) else "Application"
            ids.append(g.node(name, lane, "c"))
        for a, b in zip(ids, ids[1:]):
            g.edge(a, b, "calls")
        for i, point in enumerate((art.get("architecture_blueprint") or {}).get("integration_points", [])[:4]):
            pid = g.node(str(point.get("name", point) if isinstance(point, dict) else point), "Integration", "i")
            if ids:
                g.edge(ids[min(1, len(ids) - 1)], pid, "integrates")
    elif kind == "database":
        lanes = ["Entities"]
        entities = _entity_names((art.get("database_blueprint") or {}).get("entities", []))
        for name in entities:
            g.node(name, "Entities", "e")
        for rel in (art.get("database_blueprint") or {}).get("relationships", []):
            if isinstance(rel, dict):
                a, b = rel.get("from") or rel.get("source"), rel.get("to") or rel.get("target")
                found = [n for n in (a, b) if n]
            else:
                found = sorted((n for n in entities if n and n in str(rel)), key=lambda s: str(rel).find(s))
            if len(found) >= 2:
                g.edge(f"e_{_slug(found[0])}", f"e_{_slug(found[1])}", "relates")
    elif kind == "api":
        lanes = ["Client", "Endpoints", "Models"]
        client = g.node("API Client", "Client", "a")
        for ep in (art.get("api_catalog") or {}).get("endpoints", []):
            eid = g.node(f'{ep.get("method", "")} {ep.get("path", "")}', "Endpoints", "a")
            g.edge(client, eid, "request")
            if ep.get("response_model"):
                g.edge(eid, g.node(ep["response_model"], "Models", "m"), "returns")
    elif kind == "security":
        lanes = ["Identity", "Access", "Assurance"]
        sec = art.get("security_blueprint") or {}
        a = g.node("Authentication", "Identity", "x")
        b = g.node("Authorization", "Access", "x")
        c = g.node("Data Classification", "Access", "x")
        d = g.node("Audit Logging", "Assurance", "x")
        t = g.node("Threat Review", "Assurance", "x")
        for src, dst, lbl in ((a, b, "grants"), (b, c, "scopes"), (b, d, "recorded in"), (c, t, "informs")):
            g.edge(src, dst, lbl)
        _ = sec
    elif kind == "deployment":
        lanes = ["Build", "Environments"]
        build = g.node("Verified Build Artifact", "Build", "d")
        prev = build
        for env in (bp.get("deployment_execution_package") or {}).get("environment_plan", {}) or ("development", "qa", "uat", "production"):
            eid = g.node(str(env).title(), "Environments", "d")
            g.edge(prev, eid, "promotes")
            prev = eid
        g.edge(g.node("Rollback Plan", "Build", "d"), prev, "protects")
    elif kind == "hosting":
        lanes = ["Compute", "Data", "Security and Network"]
        host = (bp.get("hosting_execution_package") or {})
        model = (host.get("hosting_blueprint") or {}).get("hosting_model", "UNCONFIRMED")
        app = g.node(f"Hosting: {model}", "Compute", "h")
        for label, lane in (("Database Hosting", "Data"), ("Storage", "Data"), ("Key Vault", "Security and Network"),
                            ("Managed Identity", "Security and Network"), ("Network and Private Endpoints", "Security and Network"),
                            ("Monitoring Workspace", "Compute")):
            g.edge(app, g.node(label, lane, "h"), "uses")
    elif kind == "operations":
        lanes = ["Observe", "Respond", "Improve"]
        mon = g.node("Monitoring", "Observe", "o")
        obs = g.node("Observability", "Observe", "o")
        inc = g.node("Incident Management", "Respond", "o")
        chg = g.node("Change Management", "Respond", "o")
        prb = g.node("Problem Management", "Improve", "o")
        cap = g.node("Capacity and Cost", "Improve", "o")
        pat = g.node("Patch Management", "Improve", "o")
        for a, b, lbl in ((mon, inc, "alerts"), (obs, inc, "evidence"), (inc, prb, "root cause"),
                          (prb, chg, "fix via"), (chg, pat, "includes"), (mon, cap, "trends")):
            g.edge(a, b, lbl)
    else:
        lanes = ["Directors", "Control Plane", "Runtime"]
        dirs = [g.node(n, "Directors", "z") for n in ("AI CEO", "AI CTO", "AI Workforce Director",
                "AI Program Director", "AI Release Director", "AI Operations Director")]
        cp = g.node("Enterprise Control Plane", "Control Plane", "z")
        gov = g.node("Governance Model", "Control Plane", "z")
        rt = g.node("Enterprise Runtime (blueprint)", "Runtime", "z")
        for d in dirs:
            g.edge(d, cp, "governed by")
        g.edge(cp, gov, "enforces")
        g.edge(cp, rt, "controls")
    return g, lanes


def _view(graph: _Graph, lanes: list[str], executive: bool) -> dict[str, Any]:
    nodes = list(graph.nodes.values())
    edges = list(graph.edges)
    if executive:
        nodes = nodes[:EXECUTIVE_NODE_LIMIT]
        keep = {n["id"] for n in nodes}
        edges = [e for e in edges if e["from"] in keep and e["to"] in keep]
    used = [l for l in lanes if any(n["lane"] == l for n in nodes)] or lanes[:1]
    layout = _layout(nodes, edges, used)
    return {"nodes": layout["nodes"], "edges": edges, "lanes": layout["lanes"],
            "canvas": {"width": layout["width"], "height": layout["height"]}, "_layout": layout}


def build_diagram_package(blueprint: dict[str, Any] | None) -> dict[str, Any]:
    """Build all nine diagram specifications with layout and text exports; nothing is rendered."""
    bp = blueprint if isinstance(blueprint, dict) else {}
    title = (bp.get("requirement") or {}).get("title") or "Proposed Solution"
    diagrams = {}
    for kind in DIAGRAM_TYPES:
        graph, lanes = _build_graph(kind, bp)
        views = {}
        for name, executive in (("technical_view", False), ("executive_view", True)):
            v = _view(graph, lanes, executive)
            label = f"{title} - {kind.title()} Architecture ({name.split('_')[0]})"
            layout = v.pop("_layout")
            v["svg"] = _svg(label, layout, v["edges"])
            v["visio_xml"] = _visio_xml(label, layout, v["edges"])
            views[name] = v
        depends = {n["id"]: sorted(e["from"] for e in graph.edges if e["to"] == n["id"]) for n in graph.nodes.values()}
        diagrams[kind] = {
            "diagram_type": kind, "title": f"{kind.title()} Architecture", "source_basis": "Generated from blueprint packages; proposed, unverified.",
            "node_count": len(graph.nodes), "edge_count": len(graph.edges),
            "auto_layout": {"algorithm": "LAYERED_LONGEST_PATH", "node_size": [NODE_W, NODE_H]},
            "dependency_map": depends,
            "relationship_map": graph.edges,
            "swimlane_view": {"lanes": views["technical_view"]["lanes"],
                              "assignments": {n["id"]: n["lane"] for n in graph.nodes.values()}},
            "technical_view": views["technical_view"],
            "executive_view": {**views["executive_view"], "rule": f"First {EXECUTIVE_NODE_LIMIT} nodes in flow order"},
        }
    formats = {
        "svg": {"status": "TEXT_SERIALIZED_NOT_RENDERED", "available_in": "each diagram view (svg)"},
        "visio_xml": {"status": "TEXT_SERIALIZED_NOT_VALIDATED_IN_VISIO", "available_in": "each diagram view (visio_xml)"},
        "png": {"status": "NOT_RENDERED", "plan": "Rasterize the SVG with an approved renderer at 2x scale."},
        "pdf": {"status": "NOT_RENDERED", "plan": "One diagram per page, executive view first, then technical view."},
        "powerpoint": {"status": "NOT_RENDERED", "plan": "Title slide, then per diagram: executive slide and technical slide; embed SVG/PNG.",
                       "slide_count_estimate": 1 + 2 * len(DIAGRAM_TYPES)},
    }
    return {
        "package": "Architecture Diagram Factory Plan",
        "status": "PLANNING_ONLY",
        "authority": "NONE", "action_allowed": False, "persistence": False,
        "diagram_types": list(DIAGRAM_TYPES),
        "diagrams": diagrams,
        "export_formats": formats,
        "features": ["auto_layout", "dependency_mapping", "relationship_mapping", "swimlane_view", "executive_view", "technical_view"],
        "controls": {"rendering_engine_executed": False, "files_written": False, "external_tools_called": False,
                     "packages_modified": False, "persistence": False},
    }
