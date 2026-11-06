(() => {
    const status = document.getElementById("status");
    const panels = {
        capacity: document.getElementById("capacityPanel"),
        evidence: document.getElementById("evidencePanel"),
        planning: document.getElementById("planningPanel"),
        assignments: document.getElementById("assignmentsPanel"),
    };
    let people = [];
    let currentUserId = null;

    async function request(url, options = {}) {
        const response = await fetch(url, {
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", ...(options.headers || {}) },
            ...options,
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            const detail = payload.detail;
            throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail || `HTTP ${response.status}`));
        }
        return payload;
    }

    function showStatus(message, isError = false) {
        status.textContent = message;
        status.classList.toggle("error", isError);
    }

    function addText(parent, tag, text, className) {
        const element = document.createElement(tag);
        element.textContent = text;
        if (className) element.className = className;
        parent.append(element);
        return element;
    }

    function addDecisionButtons(parent, endpoint, payload, onDone, method = "POST") {
        for (const action of ["approve", "reject"]) {
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = action === "approve" ? "Approve" : "Reject";
            if (action === "reject") button.className = "secondary";
            button.addEventListener("click", async () => {
                const reason = window.prompt(`Reason to ${action}:`);
                if (!reason || reason.trim().length < 5) {
                    showStatus("A decision reason of at least five characters is required.", true);
                    return;
                }
                button.disabled = true;
                try {
                    await request(endpoint, {
                        method,
                        body: JSON.stringify({ ...payload, action, reason }),
                    });
                    showStatus(`Decision recorded: ${action}.`);
                    await onDone();
                } catch (error) {
                    showStatus(error.message, true);
                    button.disabled = false;
                }
            });
            parent.append(button);
        }
    }

    function renderCapacity(data) {
        people = data.people || [];
        document.getElementById("weekStart").textContent = data.week_start_date || "—";
        for (const selectId of ["capacityUser", "certificationUser"]) {
            const select = document.getElementById(selectId);
            const selectedId = select.value;
            select.replaceChildren();
            for (const person of people) {
                const option = document.createElement("option");
                option.value = person.user_id;
                option.textContent = `${person.display_name} (${person.readiness})`;
                select.append(option);
            }
            if (people.some((person) => person.user_id === selectedId)) select.value = selectedId;
        }
        const table = document.getElementById("capacityTable");
        table.replaceChildren();
        const tableElement = document.createElement("table");
        const head = document.createElement("thead");
        const headerRow = document.createElement("tr");
        for (const heading of ["Person", "Available", "Reserved", "Remaining", "Skills", "Certifications", "Readiness"]) {
            addText(headerRow, "th", heading);
        }
        head.append(headerRow);
        const body = document.createElement("tbody");
        for (const person of people) {
            const row = document.createElement("tr");
            addText(row, "td", person.display_name);
            addText(row, "td", `${person.available_hours}h${person.is_available ? "" : " (unavailable)"}`);
            addText(row, "td", `${person.reserved_hours}h`);
            addText(row, "td", `${person.remaining_hours}h`);
            addText(row, "td", (person.skills || []).map((item) => `${item.Name} ${item.Proficiency}/5 · ${item.Status}`).join(", ") || "None");
            addText(row, "td", (person.certifications || []).map((item) => `${item.CertificationName} · ${item.Status}`).join(", ") || "None");
            addText(row, "td", person.readiness);
            body.append(row);
        }
        tableElement.append(head, body);
        table.append(tableElement);
        document.getElementById("capacityUser").dispatchEvent(new Event("change"));
    }

    async function loadCapacity() {
        renderCapacity(await request("/workforce/management/capacity"));
    }

    async function loadEvidence() {
        const [skills, certifications] = await Promise.all([
            request("/workforce/management/skills/pending"),
            request("/workforce/management/certifications/pending"),
        ]);
        const skillContainer = document.getElementById("pendingSkills");
        skillContainer.replaceChildren();
        addText(skillContainer, "h3", `Pending skills (${skills.length})`);
        for (const item of skills) {
            const card = addText(skillContainer, "article", "", "card");
            addText(card, "h3", `${item.display_name} · ${item.skill_name}`);
            addText(card, "p", `Proficiency ${item.proficiency}/5`);
            if (item.evidence) addText(card, "p", `Evidence: ${item.evidence}`);
            addDecisionButtons(card, `/workforce/management/users/${item.user_id}/skills/${item.skill_id}/decision`, {}, loadEvidence, "PUT");
        }
        const certContainer = document.getElementById("pendingCertifications");
        certContainer.replaceChildren();
        addText(certContainer, "h3", `Pending certifications (${certifications.length})`);
        for (const item of certifications) {
            const card = addText(certContainer, "article", "", "card");
            addText(card, "h3", `${item.display_name} · ${item.certification_name}`);
            addText(card, "p", `Issuer: ${item.issuer || "Not specified"} · Expires: ${item.expires_at_utc || "No expiry"}`);
            addText(card, "p", `Evidence: ${item.evidence}`);
            addDecisionButtons(card, `/workforce/management/certifications/${item.certification_id}/decision`, {}, loadEvidence, "PUT");
        }
    }

    async function loadApprovals() {
        const items = await request("/workforce/management/recommendations/pending");
        const container = document.getElementById("pendingRecommendations");
        container.replaceChildren();
        if (!items.length) addText(container, "p", "No recommendations are awaiting approval.", "muted");
        for (const item of items) {
            const card = addText(container, "article", "", "card");
            addText(card, "h3", `${item.task_title} · ${item.candidate_name}`);
            addText(card, "p", `Match: ${item.match_score}% · Recommended ${item.recommended_at_utc}`);
            addText(card, "p", `Evidence: ${JSON.stringify(item.evidence)}`);
            if (item.manager_user_id === currentUserId) {
                addDecisionButtons(card, `/workforce/management/recommendations/${item.recommendation_id}/decision`, {}, loadApprovals);
            } else {
                addText(card, "p", "Only the candidate's assigned manager may decide this recommendation.", "muted");
            }
        }
    }

    document.querySelectorAll("[data-tab]").forEach((button) => {
        button.addEventListener("click", async () => {
            const tab = button.dataset.tab;
            document.querySelectorAll("[data-tab]").forEach((candidate) => {
                const active = candidate === button;
                candidate.setAttribute("aria-pressed", String(active));
            });
            Object.entries(panels).forEach(([name, panel]) => { panel.hidden = name !== tab; });
            try {
                if (tab === "capacity") await loadCapacity();
                if (tab === "evidence") await loadEvidence();
                if (tab === "assignments") await loadApprovals();
                showStatus("Workforce data refreshed.");
            } catch (error) {
                showStatus(error.message, true);
            }
        });
    });

    document.getElementById("capacityUser").addEventListener("change", (event) => {
        const person = people.find((item) => item.user_id === event.target.value);
        if (!person) return;
        document.getElementById("availableHours").value = person.available_hours;
        document.getElementById("isAvailable").value = String(person.is_available);
        document.getElementById("availabilityNote").value = "";
    });

    document.getElementById("capacityForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const person = people.find((item) => item.user_id === document.getElementById("capacityUser").value);
        if (!person) return showStatus("Select a workforce member first.", true);
        try {
            await request(`/workforce/management/users/${person.user_id}/capacity`, {
                method: "PUT",
                body: JSON.stringify({
                    week_start_date: document.getElementById("weekStart").textContent,
                    available_hours: Number(document.getElementById("availableHours").value),
                    is_available: document.getElementById("isAvailable").value === "true",
                    note: document.getElementById("availabilityNote").value || null,
                }),
            });
            showStatus("Availability saved.");
            await loadCapacity();
        } catch (error) {
            showStatus(error.message, true);
        }
    });

    document.getElementById("certificationForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const userId = document.getElementById("certificationUser").value;
        if (!userId) return showStatus("Select a workforce member first.", true);
        const expiry = document.getElementById("certificationExpiry").value;
        try {
            await request(`/workforce/management/users/${userId}/certifications`, {
                method: "POST",
                body: JSON.stringify({
                    certification_name: document.getElementById("certificationName").value,
                    issuer: document.getElementById("certificationIssuer").value || null,
                    expires_at_utc: expiry ? `${expiry}T00:00:00Z` : null,
                    evidence: document.getElementById("certificationEvidence").value,
                }),
            });
            event.currentTarget.reset();
            showStatus("Certification submitted for review.");
            await loadEvidence();
        } catch (error) {
            showStatus(error.message, true);
        }
    });

    document.getElementById("refreshCapacity").addEventListener("click", async () => {
        try { await loadCapacity(); showStatus("Workforce records refreshed."); }
        catch (error) { showStatus(error.message, true); }
    });

    document.getElementById("backlogForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const projectId = document.getElementById("projectId").value.trim();
        let backlog;
        try { backlog = JSON.parse(document.getElementById("backlogJson").value); }
        catch { return showStatus("Backlog must be valid JSON.", true); }
        try {
            const result = await request(`/workforce/management/projects/${encodeURIComponent(projectId)}/backlog`, {
                method: "POST",
                body: JSON.stringify(backlog),
            });
            document.getElementById("backlogResult").textContent = JSON.stringify(result, null, 2);
            showStatus("Project backlog saved.");
        } catch (error) { showStatus(error.message, true); }
    });

    document.getElementById("loadBacklog").addEventListener("click", async () => {
        const projectId = document.getElementById("projectId").value.trim();
        if (!projectId) return showStatus("Enter a project ID first.", true);
        try {
            const result = await request(`/workforce/management/projects/${encodeURIComponent(projectId)}/backlog`);
            document.getElementById("backlogResult").textContent = JSON.stringify(result, null, 2);
            showStatus("Existing project backlog loaded.");
        } catch (error) { showStatus(error.message, true); }
    });

    document.getElementById("recommendationForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const taskId = document.getElementById("taskId").value.trim();
        try {
            const result = await request(`/workforce/management/tasks/${encodeURIComponent(taskId)}/recommendations`, { method: "POST" });
            document.getElementById("recommendationResult").textContent = JSON.stringify(result, null, 2);
            showStatus(result.assignment_performed ? "Unexpected assignment occurred." : "Recommendations saved; no assignment was performed.");
            await loadApprovals();
        } catch (error) { showStatus(error.message, true); }
    });

    document.getElementById("refreshApprovals").addEventListener("click", async () => {
        try { await loadApprovals(); showStatus("Pending approvals refreshed."); }
        catch (error) { showStatus(error.message, true); }
    });

    document.getElementById("backlogJson").value = JSON.stringify({
        sprints: [],
        epics: [{
            title: "Offers intelligence",
            description: "Deliver consumer offer discovery and price history.",
            features: [{
                title: "Offer tracking",
                description: "Track retailer promotions and price changes.",
                stories: [{
                    title: "Search offers",
                    description: "As a UAE consumer, I can search current offers.",
                    acceptance_criteria: ["Search returns relevant active offers."],
                    story_points: 5,
                    required_skills: [{ name: "API Development", minimum_proficiency: 3 }],
                    required_certifications: [],
                    tasks: [{
                        title: "Implement offer search",
                        description: "Build and test the search endpoint.",
                        estimated_effort_hours: 8,
                        required_skills: [{ name: "API Development", minimum_proficiency: 3 }],
                        required_certifications: [],
                    }],
                }],
            }],
        }],
    }, null, 2);

    request("/auth/me")
        .then((user) => {
            currentUserId = user.user_id;
            return loadCapacity();
        })
        .then(() => showStatus("Workforce data loaded."))
        .catch((error) => showStatus(error.message, true));
})();
