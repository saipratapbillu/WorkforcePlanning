(function () {
    "use strict";
    const $ = (id) => document.getElementById(id);
    const API = "/execution";
    let projectId = null;
    let sprintOptions = [];

    async function request(path, options = {}) {
        const response = await fetch(path, {
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            ...options,
        });
        const text = await response.text();
        let data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
        if (response.status === 401) { window.location.href = "/login"; throw new Error("Session expired"); }
        if (!response.ok) {
            const detail = data && data.detail;
            throw new Error(typeof detail === "string" ? detail : "Request failed (" + response.status + ")");
        }
        return data;
    }

    function say(message, isError) {
        const el = $("status");
        el.textContent = message;
        el.className = isError ? "status error" : "status";
    }

    function cell(row, content) {
        const td = document.createElement("td");
        if (content instanceof Node) { td.appendChild(content); } else { td.textContent = content == null ? "" : String(content); }
        row.appendChild(td);
        return td;
    }

    function button(label, handler, secondary) {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = label;
        if (secondary) { b.className = "secondary"; }
        b.addEventListener("click", async () => {
            try { await handler(); await load(); } catch (e) { say(e.message, true); }
        });
        return b;
    }

    function bar(percent) {
        const wrap = document.createElement("div");
        wrap.className = "bar";
        const fill = document.createElement("div");
        fill.style.width = Math.min(Math.max(percent, 0), 100) + "%";
        wrap.appendChild(fill);
        const holder = document.createElement("span");
        holder.appendChild(wrap);
        holder.appendChild(document.createTextNode(percent + "%"));
        return holder;
    }

    function fill(tbodyId, rows, build) {
        const body = $(tbodyId);
        body.replaceChildren();
        rows.forEach((item) => { const tr = document.createElement("tr"); build(tr, item); body.appendChild(tr); });
        if (!rows.length) { const tr = document.createElement("tr"); cell(tr, "Nothing yet"); body.appendChild(tr); }
    }

    async function load() {
        projectId = $("project-id").value.trim();
        if (!projectId) { say("Enter a project ID.", true); return; }
        const base = API + "/projects/" + encodeURIComponent(projectId);
        const [dash, backlog] = await Promise.all([request(base + "/dashboard"), request(base + "/backlog-items")]);
        sprintOptions = dash.sprint_health.filter((s) => s.status === "Planned" || s.status === "Active");

        fill("epics", dash.epic_progress, (tr, e) => {
            cell(tr, e.title); cell(tr, e.status); cell(tr, e.completed_stories + "/" + e.stories);
            cell(tr, bar(e.percent_complete));
            const actions = document.createElement("span");
            if (e.status !== "Completed" && e.status !== "Cancelled") {
                actions.appendChild(button("Close", () => request(API + "/epics/" + e.epic_id + "/close", { method: "POST" }), true));
            }
            cell(tr, actions);
        });

        const sp = dash.story_progress;
        $("story-summary").textContent = sp.total + " stories, " + sp.percent_complete + "% complete. " +
            Object.entries(sp.by_status).map(([k, v]) => k + ": " + v).join(" | ");

        fill("sprints", dash.sprint_health, (tr, s) => {
            cell(tr, s.name + " (" + s.start_date + " - " + s.end_date + ")"); cell(tr, s.status);
            const h = cell(tr, s.health); h.className = s.health;
            cell(tr, s.completed_points + "/" + s.committed_points);
            cell(tr, s.committed_hours + "h / " + s.capacity_hours + "h");
            const actions = document.createElement("span");
            if (s.status === "Planned") { actions.appendChild(button("Start", () => request(API + "/sprints/" + s.sprint_id + "/start", { method: "POST" }))); }
            if (s.status === "Active") { actions.appendChild(button("Complete", () => request(API + "/sprints/" + s.sprint_id + "/complete", { method: "POST" }))); }
            cell(tr, actions);
        });

        const next = { Backlog: "Planned", Planned: "InProgress", InProgress: "Completed" };
        fill("backlog", backlog.items, (tr, s) => {
            cell(tr, s.Title); cell(tr, s.Status); cell(tr, "P" + s.Priority); cell(tr, s.StoryPoints); cell(tr, s.OpenDependencies);
            const actions = document.createElement("span");
            if (s.Status === "Backlog" && sprintOptions.length) {
                const sprint = sprintOptions[0];
                actions.appendChild(button("Plan into " + sprint.name, () => request(API + "/sprints/" + sprint.sprint_id + "/stories", { method: "POST", body: JSON.stringify({ story_id: s.StoryID }) }), true));
            }
            if (s.Status === "Planned" || s.Status === "InProgress") {
                actions.appendChild(button("Move to " + next[s.Status], () => request(API + "/stories/" + s.StoryID + "/transition", { method: "POST", body: JSON.stringify({ status: next[s.Status] }) })));
            }
            cell(tr, actions);
        });
        say("Loaded project " + projectId + ". Starting work requires a manager-approved assignment.");
    }

    $("load").addEventListener("click", () => load().catch((e) => say(e.message, true)));

    $("epic-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = new FormData(event.target);
        try {
            await request(API + "/projects/" + encodeURIComponent(projectId) + "/epics", { method: "POST", body: JSON.stringify({ title: form.get("title"), description: form.get("description") }) });
            event.target.reset();
            await load();
        } catch (e) { say(e.message, true); }
    });

    $("sprint-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = new FormData(event.target);
        try {
            await request(API + "/projects/" + encodeURIComponent(projectId) + "/sprints", { method: "POST", body: JSON.stringify({ name: form.get("name"), start_date: form.get("start_date"), end_date: form.get("end_date"), capacity_hours: Number(form.get("capacity_hours")) }) });
            event.target.reset();
            await load();
        } catch (e) { say(e.message, true); }
    });
})();
