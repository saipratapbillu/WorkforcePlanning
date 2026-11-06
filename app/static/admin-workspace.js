(() => {
    const state = { catalogs: null, activeTab: "dashboard", loaded: new Set() };
    const $ = (id) => document.getElementById(id);
    const status = $("workspaceStatus");
    const labels = {
        dashboard: ["Platform dashboard", "Live administrative overview. Data availability is shown per source."],
        users: ["Users", "Active and disabled accounts visible to the platform owner."],
        roles: ["Roles", "Active application roles. Assignments are managed in User Administration."],
        skills: ["Skills", "Approved and active skills in the workforce catalog."],
        departments: ["Departments", "Departments available in the active organization catalog."],
        positions: ["Positions", "Positions available in the active organization catalog."],
        approvals: ["Approvals", "Visible approval records and current decisions."],
        projects: ["Projects", "Projects visible through the authorized project API."],
        workforce: ["Workforce", "Current capacity and availability records."],
        execution: ["Execution", "Execution actions remain in the governed delivery workspace."],
        audit: ["Audit", "Recent operations adapter audit records; this is not the complete platform audit ledger."],
        health: ["Health", "Application liveness and database readiness checks."],
        settings: ["Settings", "Integration configuration is managed through the operations control center."],
    };

    async function request(url, options = {}) {
        const response = await fetch(url, { credentials: "same-origin", cache: "no-store", ...options });
        let payload;
        try { payload = await response.json(); }
        catch { throw new Error(`Invalid server response (HTTP ${response.status}).`); }
        if (!response.ok) throw new Error(payload?.error?.message || payload?.detail || `Request failed (${response.status}).`);
        return payload;
    }

    function setStatus(message, failed = false) {
        status.textContent = message;
        status.classList.toggle("error", failed);
    }

    function addCell(row, value) {
        const cell = document.createElement("td");
        cell.textContent = value == null || value === "" ? "Not recorded" : String(value);
        row.append(cell);
    }

    function renderTable(container, headings, rows, emptyMessage) {
        container.replaceChildren();
        if (!rows.length) {
            const empty = document.createElement("p");
            empty.className = "empty";
            empty.textContent = emptyMessage;
            container.append(empty);
            return;
        }
        const table = document.createElement("table");
        const head = document.createElement("thead");
        const header = document.createElement("tr");
        headings.forEach((value) => {
            const cell = document.createElement("th");
            cell.scope = "col";
            cell.textContent = value;
            header.append(cell);
        });
        head.append(header);
        const body = document.createElement("tbody");
        rows.forEach((values) => {
            const row = document.createElement("tr");
            values.forEach((value) => addCell(row, value));
            body.append(row);
        });
        table.append(head, body);
        container.append(table);
    }

    function renderRecords(container, records, title, detail) {
        container.replaceChildren();
        if (!records.length) {
            const empty = document.createElement("p");
            empty.className = "empty";
            empty.textContent = "No active catalog records are available.";
            container.append(empty);
            return;
        }
        records.forEach((record) => {
            const item = document.createElement("article");
            item.className = "record";
            const heading = document.createElement("strong");
            heading.textContent = title(record);
            const subline = document.createElement("span");
            subline.textContent = detail(record);
            item.append(heading, subline);
            container.append(item);
        });
    }

    function renderMetrics(dashboard, catalogs, users, approvals, projects) {
        const metrics = [
            ["Active users", users.items?.filter((item) => item.is_active).length ?? "Unavailable", "First 100 visible records"],
            ["Roles", catalogs.roles.length, "Active role catalog"],
            ["Pending approvals", approvals.filter((item) => item.status === "Pending").length, "Visible approval records"],
            ["Projects", projects.length, "Visible project records"],
        ];
        const root = $("platformMetrics");
        root.replaceChildren();
        metrics.forEach(([label, value, note]) => {
            const card = document.createElement("article");
            card.className = "metric";
            const caption = document.createElement("span");
            caption.textContent = label;
            const number = document.createElement("strong");
            number.textContent = String(value);
            const description = document.createElement("small");
            description.textContent = note;
            card.append(caption, number, description);
            root.append(card);
        });
        void dashboard;
    }

    async function loadCatalogs() {
        if (state.catalogs) return state.catalogs;
        state.catalogs = await request("/admin/users/catalogs");
        return state.catalogs;
    }

    async function loadDashboard() {
        const [profile, dashboard, catalogs, users, approvals, projects] = await Promise.all([
            request("/auth/me"), request("/dashboard/api"), loadCatalogs(),
            request("/admin/users?limit=100&offset=0"),
            request("/approvals", { headers: { Accept: "application/json" } }),
            request("/projects", { headers: { Accept: "application/json" } }),
        ]);
        if (profile.role !== "PLATFORM_OWNER") throw new Error("Platform owner authorization is required.");
        $("adminIdentity").textContent = `${profile.display_name || profile.email} · ${profile.role}`;
        renderMetrics(dashboard, catalogs, users, approvals, projects);
        const sources = $("sourceStatus");
        sources.replaceChildren();
        [["Identity catalog", `${users.items?.length ?? 0} records in current page`], ["Organization catalog", `${catalogs.companies.length} companies · ${catalogs.departments.length} departments · ${catalogs.positions.length} positions`], ["Approvals", `${approvals.length} visible records`], ["Projects", `${projects.length} visible records`]].forEach(([name, value]) => {
            const row = document.createElement("div");
            row.className = "source-row";
            const key = document.createElement("strong");
            key.textContent = name;
            const detail = document.createElement("span");
            detail.textContent = value;
            row.append(key, detail);
            sources.append(row);
        });
        state.catalogs = catalogs;
        state.loaded.add("dashboard");
    }

    async function loadTab(name) {
        if (state.loaded.has(name)) return;
        if (["roles", "skills", "departments", "positions"].includes(name)) {
            const catalog = await loadCatalogs();
            if (name === "roles") renderRecords($("rolesContent"), catalog.roles, (x) => x.name, (x) => `${x.code} · ${x.id}`);
            if (name === "skills") renderRecords($("skillsContent"), catalog.skills, (x) => x.name, (x) => x.id);
            if (name === "departments") renderRecords($("departmentsContent"), catalog.departments, (x) => x.name, (x) => `Company ${x.company_id} · ${x.id}`);
            if (name === "positions") renderRecords($("positionsContent"), catalog.positions, (x) => x.name, (x) => `${x.grade || "Grade not set"} · department ${x.department_id}`);
        } else if (name === "users") {
            const result = await request("/admin/users?limit=100&offset=0");
            renderTable($("usersContent"), ["Email", "Name", "Role", "Department", "Status"], result.items.map((x) => [x.email, x.display_name, x.role_code, x.department, x.is_active ? "Active" : "Disabled"]), "No users are available.");
        } else if (name === "approvals") {
            const records = await request("/approvals", { headers: { Accept: "application/json" } });
            renderTable($("approvalsContent"), ["Request", "Stage", "Status", "Assigned to", "Submitted", "Decision"], records.map((x) => [x.requirement_title, x.stage, x.status, x.assigned_to_user_id, x.created_at_utc, x.decision_at_utc]), "No approvals are visible.");
        } else if (name === "projects") {
            const records = await request("/projects", { headers: { Accept: "application/json" } });
            renderTable($("projectsContent"), ["Project", "Status", "Created"], records.map((x) => [x.ProjectName, x.Status, x.CreatedAtUtc]), "No projects are visible.");
        } else if (name === "workforce") {
            const data = await request("/workforce/management/capacity");
            renderTable($("workforceContent"), ["Person", "Availability", "Available hours", "Reserved", "Remaining", "Readiness"], data.people.map((x) => [x.display_name, x.is_available ? "Available" : "Unavailable", x.available_hours, x.reserved_hours, x.remaining_hours, x.readiness]), "No workforce capacity records are available.");
        } else if (name === "audit") {
            const records = await request("/operations/execution-adapters/audit-history");
            renderTable($("auditContent"), ["When", "Actor", "Action", "Outcome", "Details"], records.map((x) => [x.CreatedAtUtc, x.ActorID, x.Action, x.Outcome, x.Details]), "No adapter audit records are available. This is not a full audit ledger.");
        } else if (name === "health") {
            await loadHealth();
        } else if (name === "settings") {
            const providers = await request("/operations/execution-adapters");
            const root = $("settingsContent");
            root.replaceChildren();
            providers.forEach((x) => {
                const row = document.createElement("div");
                row.className = "source-row";
                const name = document.createElement("strong");
                name.textContent = x.provider_name;
                const detail = document.createElement("span");
                detail.textContent = x.config?.Status || "Not configured";
                row.append(name, detail);
                root.append(row);
            });
        }
        state.loaded.add(name);
    }

    async function loadHealth() {
        const root = $("healthContent");
        root.replaceChildren();
        for (const [label, url] of [["Application liveness", "/health"], ["Database readiness", "/ready"]]) {
            const row = document.createElement("div");
            row.className = "source-row";
            const key = document.createElement("strong");
            key.textContent = label;
            const detail = document.createElement("span");
            try {
                const result = await request(url);
                detail.textContent = result.status || "Available";
            } catch (error) {
                detail.textContent = error.message;
                row.classList.add("error");
            }
            row.append(key, detail);
            root.append(row);
        }
        state.loaded.add("health");
    }

    async function activate(name, focus = false) {
        state.activeTab = name;
        document.querySelectorAll("[role=tab]").forEach((tab) => {
            const selected = tab.dataset.tab === name;
            tab.setAttribute("aria-selected", String(selected));
            tab.tabIndex = selected ? 0 : -1;
            if (selected && focus) tab.focus();
        });
        document.querySelectorAll(".tab-panel").forEach((panel) => { panel.hidden = panel.id !== `panel-${name}`; });
        $("pageTitle").textContent = labels[name][0];
        $("pageDescription").textContent = labels[name][1];
        try {
            await loadTab(name);
            setStatus("Connected to authorized platform records.");
        } catch (error) {
            setStatus(error.message, true);
        }
    }

    document.querySelectorAll("[role=tab]").forEach((tab, index, tabs) => {
        tab.addEventListener("click", () => activate(tab.dataset.tab));
        tab.addEventListener("keydown", (event) => {
            if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
            event.preventDefault();
            const target = event.key === "Home" ? tabs[0] : event.key === "End" ? tabs[tabs.length - 1]
                : tabs[(index + (event.key === "ArrowDown" ? 1 : tabs.length - 1)) % tabs.length];
            activate(target.dataset.tab, true);
        });
    });
    $("refreshCurrent").addEventListener("click", async () => {
        state.loaded.delete(state.activeTab);
        if (state.activeTab === "dashboard") state.catalogs = null;
        await activate(state.activeTab);
    });
    $("refreshHealth").addEventListener("click", loadHealth);

    loadDashboard().then(() => activate("dashboard")).catch((error) => setStatus(error.message, true));
})();