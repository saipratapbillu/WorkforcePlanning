(() => {
    const form = document.getElementById("blueprintForm");
    const status = document.getElementById("status");
    let explorer = null;

    function setStatus(message, failed = false) {
        status.textContent = message;
        status.classList.toggle("error", failed);
    }

    function addResult(container, title, detail) {
        const row = document.createElement("div");
        row.className = "result-row";
        const heading = document.createElement("strong");
        heading.textContent = title;
        const body = document.createElement("span");
        body.textContent = detail;
        row.append(heading, body);
        container.append(row);
    }

    function drawGraph(graph) {
        const nodeMap = new Map(graph.nodes.map((item) => [item.id, item]));
        const layers = Object.fromEntries(graph.nodes.map((item) => [item.id, 0]));
        graph.edges.forEach((edge) => { layers[edge.to] = Math.max(layers[edge.to] || 0, (layers[edge.from] || 0) + 1); });
        const rows = {};
        const positions = {};
        graph.nodes.forEach((item) => {
            const layer = layers[item.id] || 0;
            const row = rows[layer] || 0;
            rows[layer] = row + 1;
            positions[item.id] = { x: 20 + layer * 230, y: 30 + row * 78 };
        });
        const maxLayer = Math.max(0, ...Object.values(layers));
        const maxRows = Math.max(1, ...Object.values(rows));
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        const width = 250 + maxLayer * 230;
        const height = 50 + maxRows * 78;
        svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
        svg.setAttribute("width", String(width));
        svg.setAttribute("height", String(height));
        svg.setAttribute("role", "img");
        svg.setAttribute("aria-label", "Blueprint package dependency graph");
        const title = document.createElementNS(svg.namespaceURI, "title");
        title.textContent = "Packages and downstream dependencies";
        svg.append(title);
        const defs = document.createElementNS(svg.namespaceURI, "defs");
        const marker = document.createElementNS(svg.namespaceURI, "marker");
        marker.setAttribute("id", "blueprint-arrow");
        marker.setAttribute("markerWidth", "8"); marker.setAttribute("markerHeight", "8");
        marker.setAttribute("refX", "7"); marker.setAttribute("refY", "4"); marker.setAttribute("orient", "auto");
        const arrow = document.createElementNS(svg.namespaceURI, "path");
        arrow.setAttribute("d", "M0 0L8 4L0 8Z"); arrow.setAttribute("fill", "#658172");
        marker.append(arrow); defs.append(marker); svg.append(defs);
        graph.edges.forEach((edge) => {
            const from = positions[edge.from]; const to = positions[edge.to];
            if (!from || !to) return;
            const line = document.createElementNS(svg.namespaceURI, "path");
            const startX = from.x + 185; const startY = from.y + 23; const endX = to.x; const endY = to.y + 23;
            line.setAttribute("d", `M ${startX} ${startY} C ${startX + 25} ${startY}, ${endX - 25} ${endY}, ${endX} ${endY}`);
            line.setAttribute("fill", "none"); line.setAttribute("stroke", "#96aa9a"); line.setAttribute("stroke-width", "1.4");
            line.setAttribute("marker-end", "url(#blueprint-arrow)"); svg.append(line);
        });
        graph.nodes.forEach((item) => {
            const point = positions[item.id];
            const group = document.createElementNS(svg.namespaceURI, "g");
            const rect = document.createElementNS(svg.namespaceURI, "rect");
            rect.setAttribute("x", point.x); rect.setAttribute("y", point.y); rect.setAttribute("width", "185"); rect.setAttribute("height", "48");
            rect.setAttribute("rx", "4"); rect.setAttribute("fill", item.present ? "#ffffff" : "#f3f5f2");
            rect.setAttribute("stroke", item.present ? "#5c8c69" : "#cbd4cc");
            const label = document.createElementNS(svg.namespaceURI, "text");
            label.setAttribute("x", point.x + 9); label.setAttribute("y", point.y + 19); label.setAttribute("font-size", "11"); label.setAttribute("fill", "#23392d");
            label.textContent = item.label;
            const state = document.createElementNS(svg.namespaceURI, "text");
            state.setAttribute("x", point.x + 9); state.setAttribute("y", point.y + 36); state.setAttribute("font-size", "9"); state.setAttribute("fill", "#718177");
            state.textContent = item.present ? "Generated" : "Not generated";
            group.append(rect, label, state); svg.append(group);
        });
        const canvas = document.getElementById("graph");
        canvas.replaceChildren(svg);
    }

    function renderExplorer(data) {
        explorer = data;
        document.getElementById("results").hidden = false;
        const metrics = data.package_metrics;
        const summary = document.getElementById("summary");
        summary.replaceChildren();
        [[metrics.packages_total, "Total packages"], [metrics.packages_present, "Packages generated"], [metrics.missing_packages.length, "Not generated"], [data.dependency_graph.acyclic ? "Acyclic" : "Review", "Dependency graph"]].forEach(([value, label]) => {
            const card = document.createElement("article"); card.className = "summary-item";
            const number = document.createElement("strong"); number.textContent = String(value);
            const caption = document.createElement("span"); caption.textContent = label;
            card.append(number, caption); summary.append(card);
        });
        drawGraph(data.dependency_graph);
        const selector = document.getElementById("impactPackage");
        const previous = selector.value;
        selector.replaceChildren();
        const placeholder = document.createElement("option"); placeholder.value = ""; placeholder.textContent = "Select a package"; selector.append(placeholder);
        data.dependency_graph.nodes.forEach((node) => {
            const option = document.createElement("option"); option.value = node.id; option.textContent = node.label; selector.append(option);
        });
        if (data.dependency_graph.nodes.some((node) => node.id === previous)) selector.value = previous;
        const searchResults = document.getElementById("searchResults"); searchResults.replaceChildren();
        (data.search_results || []).forEach((item) => addResult(searchResults, item.label, item.path));
        if (!searchResults.childElementCount) addResult(searchResults, "No matching paths", "Try a package name or section label.");
        const impact = document.getElementById("impactResult"); impact.replaceChildren();
        if (data.requested_impact) {
            const result = data.requested_impact;
            addResult(impact, result.label, `Affected downstream packages: ${result.affected_count}`);
            addResult(impact, "Direct dependents", result.direct_dependents.join(", ") || "None");
            addResult(impact, "Depends on", result.depends_on.join(", ") || "None");
            addResult(impact, "Guidance", result.guidance);
        } else {
            addResult(impact, "Impact analysis", "Choose a package above and generate the view to see downstream effects.");
        }
        const version = data.version_history;
        const versionView = document.getElementById("versionView"); versionView.replaceChildren();
        addResult(versionView, `Current generation: ${version.current.generation}`, version.basis);
        addResult(versionView, "Saved versions", version.history_available ? String(version.entries.length) : "No persisted version history exists.");
        document.getElementById("exportJson").disabled = false;
        document.getElementById("exportMarkdown").disabled = false;
    }

    async function generate(event) {
        event.preventDefault();
        const button = form.querySelector("button[type=submit]"); button.disabled = true;
        setStatus("Generating read-only blueprint view...");
        const payload = {
            title: document.getElementById("requirementTitle").value.trim(),
            description: document.getElementById("requirementDescription").value.trim(),
            domain: document.getElementById("domain").value.trim() || null,
            technology_changes: document.getElementById("technologies").value.split(",").map((item) => item.trim()).filter(Boolean),
            priority: document.getElementById("priority").value,
            query: document.getElementById("packageSearch").value.trim() || null,
            impact_of: document.getElementById("impactPackage").value || null,
        };
        try {
            const response = await fetch("/workforce/factory/blueprint-explorer", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(payload) });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result?.error?.message || result.detail || `Generation failed (${response.status}).`);
            renderExplorer(result);
            setStatus("Explorer generated. No package was persisted or executed.");
        } catch (error) { setStatus(error.message, true); }
        finally { button.disabled = false; }
    }

    function download(name, content, type) {
        const url = URL.createObjectURL(new Blob([content], { type }));
        const link = document.createElement("a"); link.href = url; link.download = name; link.click();
        URL.revokeObjectURL(url);
    }
    document.getElementById("exportJson").addEventListener("click", () => explorer && download("blueprint-explorer.json", explorer.export_view.json, "application/json"));
    document.getElementById("exportMarkdown").addEventListener("click", () => explorer && download("blueprint-outline.md", explorer.export_view.markdown, "text/markdown"));
    form.addEventListener("submit", generate);
})();
