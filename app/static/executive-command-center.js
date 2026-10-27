(() => {
    const status = document.getElementById("dashboardStatus");
    const sections = document.getElementById("dashboardSections");
    const companyContext = document.getElementById("companyContext");
    const asOf = document.getElementById("asOf");
    const readinessRecommendation = document.getElementById("readinessRecommendation");
    const readinessMetrics = document.getElementById("readinessMetrics");
    const readinessBlockers = document.getElementById("readinessBlockers");
    const buttons = [...document.querySelectorAll("[data-view]")];
    let activeView = "ceo";

    function label(value) {
        return String(value).replaceAll("_", " ").replace(/([a-z])([A-Z])/g, "$1 $2");
    }

    function renderTable(records) {
        if (!records.length) {
            const empty = document.createElement("p");
            empty.className = "empty";
            empty.textContent = "No records in this company scope.";
            return empty;
        }
        const keys = Object.keys(records[0]);
        const table = document.createElement("table");
        const head = table.createTHead().insertRow();
        keys.forEach((key) => {
            const cell = document.createElement("th");
            cell.scope = "col";
            cell.textContent = label(key);
            head.append(cell);
        });
        const body = table.createTBody();
        records.forEach((record) => {
            const row = body.insertRow();
            keys.forEach((key) => {
                const cell = row.insertCell();
                const value = record[key];
                cell.textContent = value === null || value === undefined ? "Not recorded" : String(value);
            });
        });
        return table;
    }

    function render(payload) {
        sections.replaceChildren();
        Object.entries(payload.sections).forEach(([name, records]) => {
            const section = document.createElement("article");
            section.className = "exec-section";
            const heading = document.createElement("h2");
            heading.textContent = label(name);
            const body = document.createElement("div");
            body.className = "exec-section-body";
            body.append(renderTable(records));
            section.append(heading, body);
            sections.append(section);
        });
        companyContext.textContent = `Company ${payload.company_id} · metrics reflect authorized live records`;
        asOf.textContent = `As of ${new Date(payload.as_of_utc).toLocaleString()}`;
        status.classList.remove("error");
        status.textContent = `${label(payload.view)} view loaded from live database records.`;
    }

    function renderReadiness(payload) {
        readinessRecommendation.textContent = payload.recommendation;
        readinessRecommendation.classList.toggle("no-go", payload.recommendation === "NO-GO");
        readinessMetrics.replaceChildren();
        Object.entries(payload.scorecards).forEach(([key, metric]) => {
            const item = document.createElement("div");
            item.className = "readiness-metric";
            const value = document.createElement("strong");
            value.textContent = `${metric.percent}%`;
            const labelNode = document.createElement("span");
            labelNode.textContent = `${label(key)} · ${metric.passed}/${metric.total} gates`;
            item.append(value, labelNode);
            readinessMetrics.append(item);
        });
        readinessBlockers.replaceChildren();
        if (!payload.blockers.length) {
            readinessBlockers.textContent = "No measured readiness blockers.";
        } else {
            const list = document.createElement("ul");
            payload.blockers.forEach((blocker) => {
                const row = document.createElement("li");
                row.textContent = label(blocker);
                list.append(row);
            });
            readinessBlockers.append(list);
        }
    }

    async function load(view = activeView) {
        activeView = view;
        buttons.forEach((button) => {
            const selected = button.dataset.view === view;
            button.classList.toggle("active", selected);
            button.setAttribute("aria-pressed", String(selected));
        });
        status.classList.remove("error");
        status.textContent = "Loading live metrics…";
        sections.replaceChildren();
        try {
            const [response, readinessResponse] = await Promise.all([
                fetch(`/dashboard/api/executive/${view}`, { credentials: "same-origin" }),
                fetch(`/operations/executive-readiness/${view.toUpperCase()}`, { credentials: "same-origin" }),
            ]);
            const [result, readiness] = await Promise.all([response.json(), readinessResponse.json()]);
            if (!response.ok) throw new Error(result.detail || "Executive metrics are unavailable.");
            render(result);
            if (readinessResponse.ok) renderReadiness(readiness);
            else {
                readinessRecommendation.textContent = readiness.detail || "Readiness metrics are unavailable.";
                readinessMetrics.replaceChildren();
                readinessBlockers.replaceChildren();
            }
        } catch (error) {
            status.classList.add("error");
            status.textContent = error.message;
            companyContext.textContent = "Company scope could not be verified.";
            asOf.textContent = "No live data returned";
        }
    }

    buttons.forEach((button) => button.addEventListener("click", () => load(button.dataset.view)));
    document.getElementById("refreshButton").addEventListener("click", () => load());
    load();
})();
