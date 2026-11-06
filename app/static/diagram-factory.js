(() => {
    const form = document.getElementById("diagramForm");
    const status = document.getElementById("status");
    let packageData = null;
    let svgObjectUrl = null;

    function setStatus(message, failed = false) {
        status.textContent = message;
        status.classList.toggle("error", failed);
    }

    function selectedView() {
        const type = document.getElementById("diagramType").value;
        const view = document.getElementById("diagramView").value;
        return packageData?.diagrams?.[type]?.[view] || null;
    }

    function renderDiagram() {
        const type = document.getElementById("diagramType").value;
        const diagram = packageData?.diagrams?.[type];
        const view = selectedView();
        const canvas = document.getElementById("diagramCanvas");
        canvas.replaceChildren();
        if (!view?.svg) {
            const empty = document.createElement("p"); empty.className = "empty";
            empty.textContent = "This diagram view is not available in the generated package.";
            canvas.append(empty);
            document.getElementById("downloadSvg").disabled = true;
            return;
        }
        if (svgObjectUrl) URL.revokeObjectURL(svgObjectUrl);
        svgObjectUrl = URL.createObjectURL(new Blob([view.svg], { type: "image/svg+xml" }));
        const image = document.createElement("img");
        image.src = svgObjectUrl;
        image.alt = `${diagram.title}, ${document.getElementById("diagramView").selectedOptions[0].textContent} view`;
        canvas.append(image);
        document.getElementById("diagramTitle").textContent = diagram.title;
        document.getElementById("diagramMeta").textContent = `${diagram.node_count} nodes · ${diagram.edge_count} relationships · ${diagram.source_basis}`;
        document.getElementById("downloadSvg").disabled = false;
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = form.querySelector("button[type=submit]"); button.disabled = true;
        setStatus("Generating deterministic diagram specification...");
        const payload = {
            title: document.getElementById("requirementTitle").value.trim(),
            description: document.getElementById("requirementDescription").value.trim(),
            domain: document.getElementById("domain").value.trim() || null,
            technology_changes: document.getElementById("technologies").value.split(",").map((item) => item.trim()).filter(Boolean),
            priority: document.getElementById("priority").value,
        };
        try {
            const response = await fetch("/workforce/factory/diagram-plan", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(payload) });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result?.error?.message || result.detail || `Diagram generation failed (${response.status}).`);
            packageData = result;
            renderDiagram();
            setStatus("Diagram generated from transient blueprint data. No files or deployment artifacts were created.");
        } catch (error) { setStatus(error.message, true); }
        finally { button.disabled = false; }
    });

    document.getElementById("diagramType").addEventListener("change", renderDiagram);
    document.getElementById("diagramView").addEventListener("change", renderDiagram);
    document.getElementById("downloadSvg").addEventListener("click", () => {
        const view = selectedView();
        if (!view?.svg) return;
        const type = document.getElementById("diagramType").value;
        const mode = document.getElementById("diagramView").value.replace("_view", "");
        const url = URL.createObjectURL(new Blob([view.svg], { type: "image/svg+xml" }));
        const link = document.createElement("a"); link.href = url; link.download = `${type}-${mode}-diagram.svg`; link.click();
        URL.revokeObjectURL(url);
    });
})();
