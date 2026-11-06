(() => {
    const list = document.getElementById("projectList");
    const message = document.getElementById("projectsMessage");

    function addText(parent, tag, className, value) {
        const element = document.createElement(tag);
        element.className = className;
        element.textContent = value || "";
        parent.append(element);
        return element;
    }

    async function loadProjects() {
        message.textContent = "Loading projects…";
        list.replaceChildren();
        try {
            const response = await fetch("/projects", { credentials: "same-origin", headers: { Accept: "application/json" }, cache: "no-store" });
            const projects = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(projects.detail || "Projects are unavailable right now.");
            if (!projects.length) {
                message.textContent = "No projects are available for this account yet.";
                return;
            }
            message.textContent = `${projects.length} project${projects.length === 1 ? "" : "s"}`;
            projects.forEach((project) => {
                const row = document.createElement("article");
                row.className = "project-row";
                addText(row, "h2", "", project.ProjectName || "Untitled project");
                addText(row, "p", "project-objective", project.Objective || "No project objective recorded.");
                const metadata = document.createElement("div");
                metadata.className = "project-metadata";
                addText(metadata, "span", "project-status", project.Status || "Status unavailable");
                addText(metadata, "span", "", `Created ${project.CreatedAtUtc ? new Date(project.CreatedAtUtc).toLocaleDateString() : "date unavailable"}`);
                row.append(metadata);
                list.append(row);
            });
        } catch (error) {
            message.textContent = error.message || "Projects are unavailable right now.";
        }
    }

    document.getElementById("refreshProjects").addEventListener("click", loadProjects);
    loadProjects();
})();