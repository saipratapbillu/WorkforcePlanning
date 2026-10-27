(() => {
    const state = { requests: [], selectedId: null };
    const byId = (id) => document.getElementById(id);
    const requestList = byId("requestList");
    const detail = byId("requestDetail");
    const filter = byId("statusFilter");
    const search = byId("requestSearch");
    const alertBox = byId("trackerAlert");
    const stageLabels = { intake: "Request submitted", assessment: "AI CEO assessment", approval: "Human approval", delivery: "Project planning / delivery" };

    function formatDate(value) {
        if (!value) return "Not recorded";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "Not recorded";
        return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
    }

    function statusTone(status) {
        const value = String(status || "").toLowerCase();
        if (["rejected", "assessmentfailed", "notfeasible"].includes(value)) return "blocked";
        if (["pendingapproval", "informationrequired", "pending"].includes(value)) return "waiting";
        if (["approved", "assessed", "inprogress", "completed"].includes(value)) return "active";
        return "";
    }

    function displayStatus(status) {
        const names = {
            Submitted: "Submitted",
            Assessed: "Assessed",
            PendingApproval: "Pending approval",
            AssessmentFailed: "Assessment failed",
            InformationRequired: "Information required",
            Approved: "Approved",
            Rejected: "Rejected",
        };
        return names[status] || status || "Status unavailable";
    }

    function setAlert(message) {
        alertBox.textContent = message;
        alertBox.hidden = !message;
    }

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = String(text);
        return node;
    }

    function renderList() {
        const query = search.value.trim().toLowerCase();
        const selectedStatus = filter.value;
        const items = state.requests.filter((item) => {
            const statusMatches = !selectedStatus || item.status === selectedStatus;
            const searchMatches = !query || `${item.title} ${item.requirement_id}`.toLowerCase().includes(query);
            return statusMatches && searchMatches;
        });
        byId("requestCount").textContent = String(items.length);
        requestList.replaceChildren();

        if (!items.length) {
            requestList.append(element("div", "list-empty", state.requests.length ? "No requests match these filters." : "You have not submitted a request yet."));
            return;
        }

        items.forEach((item) => {
            const button = element("button", `request-item${state.selectedId === item.requirement_id ? " selected" : ""}`);
            button.type = "button";
            button.setAttribute("aria-pressed", String(state.selectedId === item.requirement_id));
            const title = element("span", "request-item-title", item.title);
            const meta = element("span", "request-item-meta");
            const pill = element("span", `status-pill ${statusTone(item.status)}`, displayStatus(item.status));
            const date = element("time", "", formatDate(item.created_at_utc));
            meta.append(pill, date);
            button.append(title, meta);
            button.addEventListener("click", () => loadTracking(item.requirement_id));
            requestList.append(button);
        });
    }

    function renderStage(stage, currentStage) {
        const row = element("article", `timeline-stage ${stage.state || "upcoming"}`);
        const markerText = stage.state === "completed" ? "✓" : stage.state === "current" ? "•" : ["not_assigned", "blocked"].includes(stage.state) ? "!" : "·";
        row.append(element("span", "stage-marker", markerText));
        const copy = element("div", "stage-copy");
        copy.append(element("h4", "", stage.label || stageLabels[stage.key] || "Workflow stage"));

        let description = "Not started";
        if (stage.state === "completed") description = `Completed · ${formatDate(stage.at_utc)}`;
        else if (stage.state === "current") description = currentStage === "intake" ? "Request is in the intake queue." : "This is the current recorded workflow stage.";
        else if (stage.state === "not_assigned") description = "Required, but no approval assignment is recorded.";
        else if (stage.state === "blocked") description = "Approval was rejected. This request is closed until it is revised and resubmitted.";

        if (stage.key === "assessment" && stage.summary) description += ` · ${stage.summary}`;
        if (stage.key === "approval" && stage.items?.length) {
            const latest = stage.items[stage.items.length - 1];
            description = `Approval ${displayStatus(latest.status)} · ${latest.stage || "Review"} · created ${formatDate(latest.created_at_utc)}`;
            if (latest.decided_at_utc) description += ` · decided ${formatDate(latest.decided_at_utc)}`;
        }
        if (stage.key === "delivery" && stage.projects?.length) {
            description = stage.projects.map((project) => `${project.name}: ${displayStatus(project.status)}`).join("; ");
            if (stage.projects.every((project) => project.status === "Planned") && !stage.projects.some((project) => project.assigned_task_count > 0)) {
                description += " · Planning only; no task agents assigned and no development started.";
            }
        }
        copy.append(element("p", "", description));
        row.append(copy, element("time", "stage-time", stage.at_utc ? formatDate(stage.at_utc) : ""));
        return row;
    }

    function renderTracking(data) {
        detail.replaceChildren();
        const req = data.requirement;
        const header = element("header", "detail-header");
        const titleBlock = element("div");
        titleBlock.append(element("h2", "", req.title), element("p", "", `Request ${req.requirement_id} · submitted ${formatDate(req.created_at_utc)} · ${req.priority} priority`));
        const pill = element("span", `status-pill detail-status ${statusTone(req.status)}`, displayStatus(req.status));
        header.append(titleBlock, pill);
        detail.append(header);

        const next = element("section", "detail-next");
        next.append(element("span", "next-mark", "→"));
        const nextCopy = element("div");
        nextCopy.append(element("strong", "", "WHAT HAPPENS NEXT"), element("p", "", data.next_action || "No next action is recorded."));
        next.append(nextCopy);
        detail.append(next);

        const timelineHeader = element("div", "timeline-heading");
        const currentStage = data.stages?.find((stage) => stage.key === data.current_stage);
        timelineHeader.append(element("h3", "", "Workflow timeline"), element("span", "", `Current stage · ${currentStage?.label || stageLabels[data.current_stage] || data.current_stage}`));
        detail.append(timelineHeader);
        const timeline = element("div", "timeline");
        (data.stages || []).forEach((stage) => timeline.append(renderStage(stage, data.current_stage)));
        detail.append(timeline);

        const evidenceHeader = element("h3", "evidence-heading", "Recorded evidence");
        detail.append(evidenceHeader);
        const evidence = element("div", "detail-evidence");
        const assessment = data.latest_assessment;
        evidence.append(evidenceCard("AI CEO assessment", assessment ? `Version ${assessment.version} · ${displayStatus(assessment.status)}` : "No assessment record", assessment ? `${assessment.feasibility} · ${assessment.risk_level} risk` : "Assessment evidence will appear here when recorded."));
        const approvals = data.stages?.find((stage) => stage.key === "approval")?.items || [];
        evidence.append(evidenceCard("Approval record", approvals.length ? `${approvals.length} recorded` : data.approval_required ? "Required · not assigned" : "No approval record", approvals.length ? `Latest: ${displayStatus(approvals[approvals.length - 1].status)}` : "The tracker does not treat a status label as an approval decision."));
        const projects = data.stages?.find((stage) => stage.key === "delivery")?.projects || [];
        evidence.append(evidenceCard("Project", projects.length ? `${projects.length} linked project(s)` : "Not created", projects.length ? projects.map((project) => displayStatus(project.status)).join(", ") : "Project Factory has not created a linked project record."));
        const planning = data.planning;
        if (planning) {
            const uncovered = planning.skills.filter((skill) => !skill.qualified_active_agents).map((skill) => skill.skill);
            const staffingNote = planning.required_skill_count
                ? `${planning.skills_with_active_agent_coverage}/${planning.required_skill_count} required skills have active agent coverage; ${planning.assigned_task_count}/${planning.task_count} tasks assigned. ${planning.unestimated_task_count} task(s) lack effort estimates, so ~${planning.indicative_person_days_at_8h} person-days is not a complete delivery estimate. ${uncovered.length ? `No active agent matches: ${uncovered.join(", ")}. ` : ""}${planning.open_workforce_request_count ? `${planning.open_workforce_request_count} role requisitions await review. ` : ""}Calendar dates need confirmed capacity and a target start date.`
                : "No assessed skill-effort data is available to create a schedule.";
            const effortValue = planning.estimated_skill_hours
                ? `${planning.estimated_skill_hours} skill-hours · ~${planning.indicative_person_days_at_8h} person-days`
                : "Not estimated";
            evidence.append(evidenceCard("Timeline & staffing", effortValue, staffingNote));
        }
        evidence.append(evidenceCard("Last updated", formatDate(req.modified_at_utc), `Last recorded by ${req.modified_by || "system"}`));
        detail.append(evidence);

        const plannedTasks = projects.flatMap((project) => project.tasks || []);
        if (plannedTasks.length) {
            detail.append(element("h3", "evidence-heading", "Planned task breakdown"));
            const taskList = element("ol", "history-list");
            plannedTasks.forEach((task) => {
                const item = element("li");
                const estimate = task.estimated_effort_hours === null ? "estimate not recorded" : `${task.estimated_effort_hours} hours`;
                const assignment = task.assigned_agent || "unassigned";
                item.append(
                    element("span", "", `${task.sequence}. ${task.description} · ${task.required_role || "role not mapped"} · ${displayStatus(task.status)} · ${estimate} · ${assignment}`),
                    element("time", "", "")
                );
                taskList.append(item);
            });
            detail.append(taskList);
        }

        if (data.history?.length) {
            const historyHeading = element("h3", "evidence-heading", "Activity history");
            historyHeading.style.marginTop = "16px";
            detail.append(historyHeading);
            const historyList = element("ul", "history-list");
            data.history.forEach((event) => {
                const item = element("li");
                item.append(element("span", "", `${event.action} · ${event.outcome}`), element("time", "", formatDate(event.at_utc)));
                historyList.append(item);
            });
            detail.append(historyList);
        }
    }

    function evidenceCard(label, value, note) {
        const card = element("article", "evidence-card");
        card.append(element("span", "", label), element("strong", "", value), element("p", "", note));
        return card;
    }

    async function loadTracking(requirementId) {
        state.selectedId = requirementId;
        renderList();
        detail.replaceChildren(element("div", "list-empty", "Loading workflow evidence…"));
        setAlert("");
        try {
            const response = await fetch(`/requirements/${encodeURIComponent(requirementId)}/tracking`, { credentials: "same-origin" });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.detail || `Unable to load request (${response.status}).`);
            renderTracking(data);
        } catch (error) {
            detail.replaceChildren(element("div", "detail-empty", error.message));
            setAlert(error.message);
        }
    }

    async function loadRequests() {
        setAlert("");
        requestList.replaceChildren(element("div", "list-empty", "Loading your requests…"));
        try {
            const profileResponse = await fetch("/auth/me", { credentials: "same-origin" });
            if (!profileResponse.ok) throw new Error("Your session has expired. Sign in again to view requests.");
            const profile = await profileResponse.json();
            const visibilityText = {
                MANAGER: "Your requests and assigned direct reports.",
                ADMIN: "All company request flows.",
                OWNER: "All company request flows.",
                SUPER_ADMIN: "All company request flows.",
            };
            byId("visibilityNote").textContent = visibilityText[profile.role] || "Only your requests are shown.";

            const response = await fetch("/requirements", { credentials: "same-origin" });
            const data = await response.json().catch(() => []);
            if (!response.ok) throw new Error(data.detail || `Unable to load requests (${response.status}).`);
            state.requests = Array.isArray(data) ? data : [];
            renderList();
            if (state.requests.length) {
                const selected = state.requests.find((item) => item.requirement_id === state.selectedId) || state.requests[0];
                await loadTracking(selected.requirement_id);
            } else {
                state.selectedId = null;
                detail.replaceChildren();
                const empty = element("div", "detail-empty");
                empty.append(element("span", "empty-mark", "＋"), element("h2", "", "No requests yet"), element("p", "", "Submit a business requirement to see its workflow status and next steps here."));
                detail.append(empty);
            }
        } catch (error) {
            setAlert(error.message);
            requestList.replaceChildren(element("div", "list-empty", "Could not load your requests."));
            detail.replaceChildren(element("div", "detail-empty", "Sign in again or refresh to retry."));
        }
    }

    filter.addEventListener("change", renderList);
    search.addEventListener("input", renderList);
    byId("refreshRequests").addEventListener("click", loadRequests);
    loadRequests();
})();
