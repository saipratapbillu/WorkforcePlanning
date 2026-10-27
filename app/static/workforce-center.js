(() => {
    const state = { roles: [], requests: [], selectedId: null, candidates: [], role: "USER", reuseAssessments: [] };
    const byId = (id) => document.getElementById(id);
    const list = byId("requestList");
    const detail = byId("detailPanel");
    const alertBox = byId("wfAlert");

    function node(tag, className, text) {
        const item = document.createElement(tag);
        if (className) item.className = className;
        if (text !== undefined) item.textContent = String(text);
        return item;
    }

    function parseJson(value, fallback = []) {
        try { return JSON.parse(value || ""); } catch { return fallback; }
    }

    function alert(message, isError = false) {
        alertBox.textContent = message;
        alertBox.classList.toggle("error", isError);
        alertBox.hidden = !message;
    }

    function visibleRequests() {
        const status = byId("statusFilter").value;
        return state.requests.filter((item) => !status || item.Status === status);
    }

    function renderRequests() {
        const items = visibleRequests();
        byId("requestCount").textContent = String(items.length);
        list.replaceChildren();
        if (!items.length) {
            list.append(node("p", "wf-muted", "No workforce requests match this filter."));
            return;
        }
        items.forEach((item) => {
            const button = node("button", `wf-request${state.selectedId === item.WorkforceRequestID ? " selected" : ""}`);
            button.type = "button";
            const title = node("strong", "", item.PositionName);
            const status = node("span", "wf-status", item.Status);
            title.append(status);
            button.append(title, node("span", "", `${item.ProjectName || "Project"} · ${item.DepartmentName} · ${new Date(item.RequestedAtUtc).toLocaleDateString()}`));
            button.addEventListener("click", () => showRequest(item.WorkforceRequestID));
            list.append(button);
        });
    }

    function renderProfiles() {
        const container = byId("profileList");
        container.replaceChildren();
        byId("profileCount").textContent = `${state.roles.length} profiles`;
        state.roles.forEach((profile) => {
            const card = node("article", "wf-profile");
            card.append(node("h3", "", profile.PositionName), node("small", "", `${profile.DepartmentName} · ${profile.Grade} · v${profile.ProfileVersion}`));
            if (profile.OrgLayer || profile.ReportsToRoleCode) {
                card.append(node("small", "", `${profile.OrgLayer || "Role"}${profile.ReportsToRoleCode ? ` · reports to ${profile.ReportsToRoleCode}` : " · top-level"}`));
            }
            card.append(node("p", "", profile.JobDescription));
            const skills = node("div", "wf-skills");
            parseJson(profile.RequiredSkillsJson).forEach((skill) => skills.append(node("span", "wf-skill", `${skill.name} · ${skill.minimum_proficiency}/5`)));
            card.append(skills);
            const governance = node("small", "", `Scope: ${profile.ApprovalScope || "none"} · autonomy ceiling ${profile.MaxRecommendedAutonomy ?? "not set"}/5 · gates: ${parseJson(profile.QualityGatesJson).join(", ") || "none"}`);
            governance.style.display = "block";
            governance.style.marginTop = "9px";
            card.append(governance);
            container.append(card);
        });
    }

    function renderGovernanceCatalog(catalog) {
        const gateList = byId("gateList");
        gateList.replaceChildren();
        catalog.gates.forEach((gate) => {
            const item = node("article", "wf-gate");
            item.append(
                node("h3", "", `${gate.SequenceNumber}. ${gate.GateName}`),
                node("small", "", `${gate.GateCode} · ${gate.OwnerRoleCode} · ${gate.AppliesTo}`),
                node("p", "", `${gate.BlocksProgress ? "Blocking gate" : "Advisory gate"} · ${gate.RequiresHumanApproval ? "human decision required" : "evidence/review required"} · ${parseJson(gate.RequiredEvidenceJson).join(", ")}`)
            );
            gateList.append(item);
        });
        const escalationList = byId("escalationList");
        escalationList.replaceChildren();
        catalog.escalations.forEach((step) => {
            const item = node("article", "wf-escalation");
            item.append(node("strong", "", `${step.EscalationCode} · ${step.TargetRoleCode}`));
            item.append(node("span", "", `${step.TriggerDescription}${step.TargetResponseMinutes ? ` · target ${step.TargetResponseMinutes} min` : ""}`));
            escalationList.append(item);
        });
    }

    function renderActivationBlockers(requests) {
        const list = byId("blockerList");
        list.replaceChildren();
        const blockers = requests.flatMap((request) => parseJson(request.ActivationBlockersJson).map((blocker) => ({
            ...blocker,
            agent: request.ProvisionedAgentName || request.PositionName,
            role: request.RoleCode,
            requestStatus: request.Status,
        })));
        byId("blockerCount").textContent = String(blockers.length);
        if (!blockers.length) {
            list.append(node("p", "wf-muted", "No open activation blockers."));
            return;
        }
        blockers.forEach((blocker) => {
            const card = node("article", "wf-blocker");
            card.append(node("strong", "", `${blocker.agent} · ${blocker.code}`));
            card.append(node("small", "", `${blocker.role} · ${blocker.requestStatus}`));
            card.append(node("p", "", blocker.description));
            list.append(card);
        });
    }

    function renderOrganizationStatus(runs) {
        const title = byId("orgStatusTitle");
        const detail = byId("orgStatusDetail");
        const badge = byId("orgStatusBadge");
        const latest = runs[0];
        if (!latest) {
            title.textContent = "Organization bootstrap will run after an Owner/Super Admin approval.";
            detail.textContent = "It creates/reuses role-based Agent records in Provisioning. It does not activate agents or run tasks.";
            badge.textContent = "Not run";
            return;
        }
        title.textContent = `Organization ${latest.Status.toLowerCase()}: ${latest.CreatedAgentCount} new agents, ${latest.ReusedAgentCount} reused, ${latest.RoleCount} roles.`;
        detail.textContent = `Triggered by approved requirement ${latest.TriggerRequirementID}. All new agents remain non-active until provider configuration and evaluations pass.`;
        badge.textContent = latest.Status;
    }

    function renderReusePanel(metrics, assessments) {
        const panel = byId("reusePanel");
        panel.hidden = false;
        const metricList = byId("reuseMetrics");
        metricList.replaceChildren();
        [
            [metrics.workforce_requests_prevented, "Workforce requests prevented"],
            [metrics.reused_agents, "Reused agents"],
            [metrics.upskill_candidates, "Upskill candidates"],
            [`${metrics.upskill_success_rate_percent}%`, "Upskill success rate"],
            [`${metrics.workforce_utilization_percent}%`, "Workforce utilization"],
            [`${metrics.workforce_reuse_percent}%`, "Workforce reuse"],
            ["Not priced", "Workforce savings"],
        ].forEach(([value, label]) => {
            const metric = node("div", "wf-reuse-metric");
            metric.append(node("strong", "", value), node("span", "", label));
            if (label === "Workforce savings") {
                metric.append(node("span", "", metrics.workforce_savings?.basis || "Approved cost basis is not recorded."));
            }
            metricList.append(metric);
        });

        const list = byId("reuseAssessments");
        list.replaceChildren();
        if (!assessments.length) {
            list.append(node("p", "wf-muted", "No workforce reuse plans are awaiting review."));
            return;
        }
        assessments.forEach((assessment) => {
            const item = node("article", "wf-reuse-item");
            item.append(
                node("h3", "", `${assessment.PositionName} · ${assessment.Classification} · ${assessment.MatchScore}%`),
                node("p", "wf-reuse-meta", `${assessment.ProjectName} · ${assessment.AgentName} (${assessment.AgentStatus}) · workload ${assessment.CurrentWorkload ?? 0}% · ${assessment.AssessmentStatus}`),
                node("p", "wf-reuse-meta", `Estimated readiness: ${assessment.EstimatedReadinessDays} day(s) · ${assessment.CapacityAvailable ? "capacity available" : "capacity unavailable"}`),
            );
            const skills = node("div", "wf-reuse-skills");
            parseJson(assessment.SkillPlanJson).forEach((skill) => {
                const row = node("div", "wf-reuse-skill");
                row.append(
                    node("span", "", `${skill.required_skill} · current ${skill.current_skill}/5`),
                    node("span", "", `Required ${skill.required_proficiency}/5 · gap ${skill.gap}`),
                    node("span", "", skill.recommendation),
                );
                skills.append(row);
            });
            item.append(skills);
            const missingCertifications = parseJson(assessment.MissingCertificationsJson);
            item.append(node("p", "wf-reuse-blockers", missingCertifications.length
                ? `Certification gaps: ${missingCertifications.join(", ")}.`
                : "All required certifications are current."));
            if (assessment.AssessmentStatus === "PendingApproval" && state.role === "WORKFORCE_MANAGER") {
                const actions = node("div", "wf-reuse-actions");
                const reason = document.createElement("textarea");
                reason.placeholder = "Decision rationale (minimum 5 characters)";
                reason.setAttribute("aria-label", `Decision rationale for ${assessment.AgentName}`);
                [["approve", "Approve plan", ""], ["reject", "Reject plan", "reject"]].forEach(([action, label, className]) => {
                    const button = node("button", className, label);
                    button.type = "button";
                    button.addEventListener("click", async () => {
                        if (reason.value.trim().length < 5) return alert("Enter a decision rationale of at least five characters.", true);
                        button.disabled = true;
                        try {
                            const response = await fetch(`/workforce/reuse-assessments/${assessment.AssessmentID}/decision`, {
                                method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({ action, reason: reason.value.trim() }),
                            });
                            const result = await response.json();
                            if (!response.ok) throw new Error(result.detail || "Reuse decision failed.");
                            alert("Decision recorded. Agent skills, certifications, workload, and activation were not changed.");
                            await loadData();
                        } catch (error) { alert(error.message, true); button.disabled = false; }
                    });
                    actions.append(button);
                });
                actions.prepend(reason);
                item.append(actions);
            } else if (assessment.AssessmentStatus === "Approved" && assessment.Classification === "Upskill Candidate" && state.role === "WORKFORCE_MANAGER") {
                const complete = node("button", "", "Record verified completion");
                complete.type = "button";
                complete.addEventListener("click", async () => {
                    const evidence = window.prompt("Enter evidence reference for verified active skills and current certifications:");
                    if (!evidence || evidence.trim().length < 20) return;
                    complete.disabled = true;
                    try {
                        const response = await fetch(`/workforce/reuse-assessments/${assessment.AssessmentID}/complete`, {
                            method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ evidence: evidence.trim() }),
                        });
                        const result = await response.json();
                        if (!response.ok) throw new Error(result.detail || "Completion could not be verified.");
                        alert("Upskill plan completion recorded; no agent activation was performed.");
                        await loadData();
                    } catch (error) { alert(error.message, true); complete.disabled = false; }
                });
                const actions = node("div", "wf-reuse-actions");
                actions.append(complete);
                item.append(actions);
            } else if ((assessment.AssessmentStatus === "Approved" || assessment.AssessmentStatus === "Completed") && state.role === "WORKFORCE_MANAGER") {
                const assign = node("button", "", "Assign to assessed task");
                assign.type = "button";
                assign.addEventListener("click", async () => {
                    const reason = window.prompt("Record the Workforce Manager assignment rationale:");
                    if (!reason || reason.trim().length < 5) return;
                    assign.disabled = true;
                    try {
                        const response = await fetch(`/workforce/reuse-assessments/${assessment.AssessmentID}/assign`, {
                            method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ reason: reason.trim() }),
                        });
                        const result = await response.json();
                        if (!response.ok) throw new Error(result.detail || "Agent assignment failed.");
                        alert("Approved agent assigned to the assessed task. No activation or skill changes were performed.");
                        await loadData();
                    } catch (error) { alert(error.message, true); assign.disabled = false; }
                });
                const actions = node("div", "wf-reuse-actions");
                actions.append(assign);
                item.append(actions);
            } else {
                item.append(node("p", "wf-reuse-meta", assessment.AssessmentStatus === "Assigned"
                    ? "Agent is assigned to the assessed task and remains Active; no activation or skill changes were performed."
                    : "Reuse plan is recorded."));
            }
            list.append(item);
        });
    }

    function renderFactoryDashboard(metrics) {
        const container = byId("wfFactoryMetrics");
        container.replaceChildren();
        const values = [
            [metrics.total_agents, "Total agents"],
            [metrics.active_agents, "Active agents"],
            [metrics.available_agents, "Available agents"],
            [metrics.assigned_agents, "Assigned agents"],
            [metrics.certification_coverage_percent == null ? "Unavailable" : `${metrics.certification_coverage_percent}%`, "Certification coverage"],
            [metrics.skill_coverage_percent == null ? "Unavailable" : `${metrics.skill_coverage_percent}%`, "Skill coverage"],
            [metrics.capacity_utilization_percent == null ? "Unavailable" : `${metrics.capacity_utilization_percent}%`, "Capacity utilization"],
            [metrics.skills_gap_count, "Skill gaps"],
            [metrics.workforce_readiness_percent == null ? "Unavailable" : `${metrics.workforce_readiness_percent}%`, "Workforce readiness"],
        ];
        values.forEach(([value, label]) => {
            const metric = node("div", "wf-factory-metric");
            metric.append(node("strong", "", value ?? "Unavailable"), node("span", "", label));
            container.append(metric);
        });
        container.setAttribute("aria-label", `Workforce readiness as of ${metrics.as_of_utc || "unknown time"}`);
    }

    async function renderRequestActions(item, profile, section) {
        const actions = node("div", "wf-actions");
        if (!["OWNER", "SUPER_ADMIN"].includes(state.role)) {
            actions.append(node("p", "wf-muted", "Decision authority is reserved to Owner/Super Admin. You can review role profiles and request status."));
            section.append(actions);
            return;
        }
        if (item.Status === "PendingApproval") {
            const reason = document.createElement("textarea");
            reason.placeholder = "Required decision rationale (minimum 5 characters)";
            reason.setAttribute("aria-label", "Workforce decision reason");
            const buttons = node("div", "wf-button-row");
            [["approve_recruiting", "Authorize recruiting", "wf-button"], ["reject", "Reject request", "wf-button danger"]].forEach(([action, label, className]) => {
                const button = node("button", className, label);
                button.type = "button";
                button.addEventListener("click", async () => {
                    if (reason.value.trim().length < 5) return alert("Enter a decision reason of at least five characters.", true);
                    button.disabled = true;
                    try {
                        const response = await fetch(`/workforce/requests/${item.WorkforceRequestID}/decision`, {
                            method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ action, reason: reason.value.trim() }),
                        });
                        const result = await response.json();
                        if (!response.ok) throw new Error(result.detail || "Decision failed.");
                        alert(result.message);
                        await loadData();
                        showRequest(item.WorkforceRequestID);
                    } catch (error) { alert(error.message, true); button.disabled = false; }
                });
                buttons.append(button);
            });
            actions.append(reason, buttons);
        } else if (item.Status === "Recruiting") {
            const provisionButton = node("button", "wf-button", "Create agent provisioning record");
            provisionButton.type = "button";
            provisionButton.addEventListener("click", async () => {
                provisionButton.disabled = true;
                try {
                    const response = await fetch(`/workforce/requests/${item.WorkforceRequestID}/provision`, {
                        method: "POST", credentials: "same-origin",
                    });
                    const result = await response.json();
                    if (!response.ok) throw new Error(result.detail || "Provisioning failed.");
                    alert("Agent record created in Provisioning. It is not active and cannot execute tasks until a model is configured and safety/capability evaluations pass.");
                    await loadData();
                    showRequest(item.WorkforceRequestID);
                } catch (error) { alert(error.message, true); provisionButton.disabled = false; }
            });
            actions.append(node("p", "wf-muted", "Recruiting authorization is recorded. Provisioning creates a non-active agent profile from this role charter; no model is configured and no task runs yet."), provisionButton);
        } else if (item.Status === "Provisioning") {
            const activateButton = node("button", "wf-button", "Validate and activate agent");
            activateButton.type = "button";
            const modelConfigured = item.ModelProvider && item.ModelProvider !== "UNCONFIGURED" && item.Model && item.Model !== "UNCONFIGURED" && item.ModelVersion && item.ModelVersion !== "UNCONFIGURED";
            const evaluationsPassed = Boolean(item.CapabilityEvaluationPassed) && Boolean(item.SafetyEvaluationPassed)
                && Boolean(item.SecurityEvaluationPassed) && Boolean(item.GovernanceEvaluationPassed);
            activateButton.disabled = !modelConfigured || !evaluationsPassed;
            activateButton.addEventListener("click", async () => {
                const reason = window.prompt("Record why activation is authorized after model configuration and passed Safety and Capability evaluations:");
                if (!reason || reason.trim().length < 5) return;
                activateButton.disabled = true;
                try {
                    const response = await fetch(`/workforce/requests/${item.WorkforceRequestID}/activate`, {
                        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ reason: reason.trim() }),
                    });
                    const result = await response.json();
                    if (!response.ok) throw new Error(result.detail || "Activation is blocked.");
                    alert(result.message);
                    await loadData();
                    showRequest(item.WorkforceRequestID);
                } catch (error) { alert(error.message, true); activateButton.disabled = false; }
            });
                actions.append(
                    node("p", "wf-muted", `Provisioned agent: ${item.ProvisionedAgentName || "not linked"} · state ${item.AgentStatus || "unknown"} · provider/model/version ${item.ModelProvider || "unconfigured"} / ${item.Model || "unconfigured"} / ${item.ModelVersion || "unconfigured"}. Capability: ${item.CapabilityEvaluationPassed ? "passed" : "not passed"}; Safety: ${item.SafetyEvaluationPassed ? "passed" : "not passed"}; Security: ${item.SecurityEvaluationPassed ? "passed" : "not passed"}; Governance: ${item.GovernanceEvaluationPassed ? "passed" : "not passed"}; pending skills: ${item.PendingSkillCount || 0}; open blockers: ${item.OpenActivationBlockerCount || 0}.`),
                activateButton
            );
        } else if (item.Status === "AgentActive") {
            actions.append(node("p", "wf-muted", `${item.ProvisionedAgentName || "Agent"} is active and role-qualified. The planner has queued matching tasks; this app still has no model execution runtime.`));
        } else if (["CandidateReady"].includes(item.Status)) {
            const candidateSelect = document.createElement("select");
            candidateSelect.setAttribute("aria-label", "Qualified available agent");
            candidateSelect.append(new Option("Loading qualified agents…", ""));
            const reason = document.createElement("textarea");
            reason.placeholder = "Required rationale confirming the selected agent was validated";
            reason.setAttribute("aria-label", "Agent assignment reason");
            const fillButton = node("button", "wf-button", "Assign qualified agent");
            fillButton.type = "button";
            fillButton.disabled = true;
            try {
                const response = await fetch(`/workforce/candidates?role_code=${encodeURIComponent(item.RoleCode)}`, { credentials: "same-origin" });
                const candidates = await response.json();
                if (!response.ok) throw new Error(candidates.detail || "Could not load candidates.");
                candidateSelect.replaceChildren(new Option(candidates.length ? "Select a qualified agent" : "No qualified active agents available", ""));
                candidates.forEach((candidate) => candidateSelect.append(new Option(`${candidate.agent_name} · ${candidate.active_assignments}/${candidate.concurrent_task_limit} tasks`, candidate.agent_id)));
                fillButton.disabled = !candidates.length;
                state.candidates = candidates;
            } catch (error) {
                candidateSelect.replaceChildren(new Option(error.message, ""));
            }
            fillButton.addEventListener("click", async () => {
                if (!candidateSelect.value || reason.value.trim().length < 5) return alert("Select a qualified agent and enter a reason.", true);
                fillButton.disabled = true;
                try {
                    const response = await fetch(`/workforce/requests/${item.WorkforceRequestID}/fill`, {
                        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ agent_id: candidateSelect.value, reason: reason.value.trim() }),
                    });
                    const result = await response.json();
                    if (!response.ok) throw new Error(result.detail || "Agent assignment failed.");
                    alert(`Role filled. ${result.tasks_assigned} task(s) assigned; the agent remains active in the workforce pool after work is released.`);
                    await loadData();
                    showRequest(item.WorkforceRequestID);
                } catch (error) { alert(error.message, true); fillButton.disabled = false; }
            });
            actions.append(candidateSelect, reason, fillButton);
        } else {
            actions.append(node("p", "wf-muted", item.Status === "Filled" ? "A validated active agent is assigned. Task completion releases its assignment; the agent remains eligible for later work." : "No action is available in this state."));
        }
        section.append(actions);
    }

    async function showRequest(requestId) {
        state.selectedId = requestId;
        renderRequests();
        const item = state.requests.find((row) => row.WorkforceRequestID === requestId);
        if (!item) return;
        const profile = state.roles.find((row) => row.RoleCode === item.RoleCode);
        detail.replaceChildren();
        const header = node("div", "wf-detail-head");
        const heading = node("div");
        heading.append(node("h2", "", item.PositionName), node("div", "wf-subtitle", `${item.DepartmentName} · ${item.Status} · ${item.ProjectName || item.ProjectID}`));
        header.append(heading, node("span", "wf-status", item.Status));
        detail.append(header);
        const why = node("section", "wf-detail-section");
        why.append(node("h3", "", "Why this role is requested"), node("p", "", item.RequestReason));
        detail.append(why);
        if (profile) {
            const jd = node("section", "wf-detail-section");
            jd.append(node("h3", "", "Role charter"), node("p", "", profile.JobDescription));
            const skillWrap = node("div", "wf-skills");
            parseJson(profile.RequiredSkillsJson).forEach((skill) => skillWrap.append(node("span", "wf-skill", `${skill.name} · minimum ${skill.minimum_proficiency}/5`)));
            jd.append(skillWrap);
            detail.append(jd);
        }
        if (item.DecisionReason) {
            const decision = node("section", "wf-detail-section");
            decision.append(node("h3", "", "Recorded decision"), node("p", "", `${item.DecisionBy || "Authorized reviewer"}: ${item.DecisionReason}`));
            detail.append(decision);
        }
        const actionSection = node("section", "wf-detail-section");
        actionSection.append(node("h3", "", "Governance action"));
        detail.append(actionSection);
        await renderRequestActions(item, profile, actionSection);
    }

    async function loadData() {
        alert("");
        try {
            const profileResponse = await fetch("/auth/me", { credentials: "same-origin" });
            const user = await profileResponse.json();
            if (!profileResponse.ok) throw new Error(user.detail || "Your session could not be verified.");
            state.role = user.role || "USER";
            byId("roleLabel").textContent = state.role.replaceAll("_", " ");

            const factoryResponse = await fetch("/workforce/factory/dashboard", { credentials: "same-origin" });
            const factoryDashboard = await factoryResponse.json();
            if (!factoryResponse.ok) throw new Error(factoryDashboard.detail || "Workforce readiness is unavailable.");
            renderFactoryDashboard(factoryDashboard);

            if (state.role === "WORKFORCE_MANAGER") {
                const [rolesResponse, assessmentsResponse, metricsResponse] = await Promise.all([
                    fetch("/workforce/roles", { credentials: "same-origin" }),
                    fetch("/workforce/reuse-assessments", { credentials: "same-origin" }),
                    fetch("/workforce/reuse-metrics", { credentials: "same-origin" }),
                ]);
                const [roles, assessments, metrics] = await Promise.all([
                    rolesResponse.json(), assessmentsResponse.json(), metricsResponse.json(),
                ]);
                if (!rolesResponse.ok || !assessmentsResponse.ok || !metricsResponse.ok) {
                    throw new Error(assessments.detail || metrics.detail || roles.detail || "Your role cannot access workforce reuse review.");
                }
                state.roles = roles;
                state.reuseAssessments = assessments;
                document.querySelector(".wf-grid").hidden = true;
                document.querySelector(".wf-org-status").hidden = true;
                document.querySelector(".wf-blockers").hidden = true;
                document.querySelector(".wf-catalog").hidden = true;
                document.querySelector(".wf-governance").hidden = true;
                renderReusePanel(metrics, assessments);
                return;
            }

            const [rolesResponse, requestsResponse, governanceResponse, organizationResponse] = await Promise.all([
                fetch("/workforce/roles", { credentials: "same-origin" }),
                fetch("/workforce/requests", { credentials: "same-origin" }),
                fetch("/workforce/governance-catalog", { credentials: "same-origin" }),
                fetch("/workforce/organization/status", { credentials: "same-origin" }),
            ]);
            const roles = await rolesResponse.json();
            const requests = await requestsResponse.json();
            const governance = await governanceResponse.json();
            const organization = await organizationResponse.json();
            if (!rolesResponse.ok || !requestsResponse.ok || !governanceResponse.ok || !organizationResponse.ok) {
                throw new Error(requests.detail || roles.detail || governance.detail || organization.detail || "Your role cannot access workforce planning.");
            }
            state.roles = roles;
            state.requests = requests;
            byId("reusePanel").hidden = true;
            renderProfiles();
            renderGovernanceCatalog(governance);
            renderActivationBlockers(requests);
            renderOrganizationStatus(organization);
            if (!governance.runtime_enforced) {
                alert(`${governance.notice} This registry does not itself block work.`, false);
            }
            if (state.role === "PLATFORM_OWNER") {
                const [assessmentsResponse, metricsResponse] = await Promise.all([
                    fetch("/workforce/reuse-assessments", { credentials: "same-origin" }),
                    fetch("/workforce/reuse-metrics", { credentials: "same-origin" }),
                ]);
                const [assessments, metrics] = await Promise.all([assessmentsResponse.json(), metricsResponse.json()]);
                if (assessmentsResponse.ok && metricsResponse.ok) renderReusePanel(metrics, assessments);
            }
            renderRequests();
            const selected = state.requests.find((item) => item.WorkforceRequestID === state.selectedId);
            if (selected) await showRequest(selected.WorkforceRequestID);
            else if (state.requests.length) await showRequest(state.requests[0].WorkforceRequestID);
            else detail.innerHTML = "<div class='wf-empty'><span>✓</span><h2>No staffing gaps</h2><p>Planned tasks currently have qualified workforce coverage.</p></div>";
        } catch (error) {
            alert(error.message, true);
            list.replaceChildren(node("p", "wf-muted", "Could not load workforce records."));
        }
    }

    byId("statusFilter").addEventListener("change", renderRequests);
    byId("refreshButton").addEventListener("click", loadData);
    byId("factoryBlueprintForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = byId("factoryGenerateButton");
        const output = byId("wfFactoryResult");
        button.disabled = true;
        output.hidden = false;
        output.textContent = "Generating deterministic recommendation…";
        try {
            const response = await fetch("/workforce/factory/blueprint", {
                method: "POST", credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    title: byId("factoryTitle").value.trim(),
                    description: byId("factoryDescription").value.trim(),
                    technology_changes: byId("factoryTechnologies").value.split(",").map((item) => item.trim()).filter(Boolean),
                }),
            });
            const blueprint = await response.json();
            if (!response.ok) throw new Error(blueprint.detail || "Blueprint generation failed.");
            output.textContent = JSON.stringify(blueprint, null, 2);
            alert(`${blueprint.roles.length} role blueprints generated. No agent records or assignments were created.`);
        } catch (error) {
            output.textContent = error.message;
            alert(error.message, true);
        } finally {
            button.disabled = false;
        }
    });
    byId("factoryCodePackageButton").addEventListener("click", async () => {
        const button = byId("factoryCodePackageButton");
        const output = byId("wfFactoryResult");
        if (!byId("factoryBlueprintForm").reportValidity()) return;
        button.disabled = true;
        try {
            const response = await fetch("/workforce/factory/code-package", {
                method: "POST", credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    title: byId("factoryTitle").value.trim(),
                    description: byId("factoryDescription").value.trim(),
                    technology_changes: byId("factoryTechnologies").value.split(",").map((item) => item.trim()).filter(Boolean),
                    backend_language: byId("factoryBackendLanguage").value,
                }),
            });
            const packageData = await response.json();
            if (!response.ok) throw new Error(packageData.detail || "Code package generation failed.");
            const packageBlob = new Blob([JSON.stringify(packageData, null, 2)], { type: "application/json" });
            const downloadUrl = URL.createObjectURL(packageBlob);
            const download = document.createElement("a");
            download.href = downloadUrl;
            download.download = `workforce-code-package-${packageData.backend_language}.json`;
            document.body.append(download);
            download.click();
            download.remove();
            window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 0);
            output.hidden = false;
            output.textContent = `${packageData.file_count} source artifact files prepared for ${packageData.backend_language}. JSON package downloaded. No files were written by the server, no code was run, and no deployment or infrastructure action occurred.`;
            alert("Code artifact package downloaded. Review and configure all security/persistence adapters before use.");
        } catch (error) {
            output.hidden = false;
            output.textContent = error.message;
            alert(error.message, true);
        } finally {
            button.disabled = false;
        }
    });
    byId("factoryDeliveryPlanButton").addEventListener("click", async () => {
        const button = byId("factoryDeliveryPlanButton");
        const output = byId("wfFactoryResult");
        if (!byId("factoryBlueprintForm").reportValidity()) return;
        button.disabled = true;
        try {
            const response = await fetch("/workforce/factory/delivery-plan", {
                method: "POST", credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    title: byId("factoryTitle").value.trim(),
                    description: byId("factoryDescription").value.trim(),
                    technology_changes: byId("factoryTechnologies").value.split(",").map((item) => item.trim()).filter(Boolean),
                }),
            });
            const deliveryPlan = await response.json();
            if (!response.ok) throw new Error(deliveryPlan.detail || "Delivery plan generation failed.");
            const packageBlob = new Blob([JSON.stringify(deliveryPlan, null, 2)], { type: "application/json" });
            const downloadUrl = URL.createObjectURL(packageBlob);
            const download = document.createElement("a");
            download.href = downloadUrl;
            download.download = "delivery-simulation-plan.json";
            document.body.append(download);
            download.click();
            download.remove();
            window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 0);
            output.hidden = false;
            output.textContent = `Delivery plan downloaded: ${deliveryPlan.delivery_blueprint.critical_path_sprint_estimate} estimated sprint(s), ${deliveryPlan.risk_register.risk_count} planning risks. Readiness is ${deliveryPlan.project_health.readiness_status}; all resources remain unassigned and no execution occurred.`;
            alert("Delivery simulation downloaded. Capacity/velocity are assumptions; no assignments or execution were performed.");
        } catch (error) {
            output.hidden = false;
            output.textContent = error.message;
            alert(error.message, true);
        } finally {
            button.disabled = false;
        }
    });
    byId("factoryAssignmentPlanButton").addEventListener("click", async () => {
        const button = byId("factoryAssignmentPlanButton");
        const output = byId("wfFactoryResult");
        if (!byId("factoryBlueprintForm").reportValidity()) return;
        button.disabled = true;
        try {
            const response = await fetch("/workforce/factory/assignment-plan", {
                method: "POST", credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    title: byId("factoryTitle").value.trim(),
                    description: byId("factoryDescription").value.trim(),
                    technology_changes: byId("factoryTechnologies").value.split(",").map((item) => item.trim()).filter(Boolean),
                    candidate_evidence: [],
                }),
            });
            const assignmentPackage = await response.json();
            if (!response.ok) throw new Error(assignmentPackage.detail || "Assignment recommendation generation failed.");
            const packageBlob = new Blob([JSON.stringify(assignmentPackage, null, 2)], { type: "application/json" });
            const downloadUrl = URL.createObjectURL(packageBlob);
            const download = document.createElement("a");
            download.href = downloadUrl;
            download.download = "assignment-recommendation-plan.json";
            document.body.append(download);
            download.click();
            download.remove();
            window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 0);
            output.hidden = false;
            output.textContent = `Assignment package downloaded. Readiness: ${assignmentPackage.assignment_readiness.status}; verified readiness score: unavailable without independently verified candidate evidence. No assignments were made.`;
            alert("Assignment recommendations downloaded. No candidate roster was supplied and no assignments were made.");
        } catch (error) {
            output.hidden = false;
            output.textContent = error.message;
            alert(error.message, true);
        } finally {
            button.disabled = false;
        }
    });
    byId("factoryTestSimulationButton").addEventListener("click", async () => {
        const button = byId("factoryTestSimulationButton");
        const output = byId("wfFactoryResult");
        if (!byId("factoryBlueprintForm").reportValidity()) return;
        button.disabled = true;
        try {
            const response = await fetch("/workforce/factory/test-simulation", {
                method: "POST", credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    title: byId("factoryTitle").value.trim(),
                    description: byId("factoryDescription").value.trim(),
                    technology_changes: byId("factoryTechnologies").value.split(",").map((item) => item.trim()).filter(Boolean),
                    backend_language: byId("factoryBackendLanguage").value,
                }),
            });
            const testPackage = await response.json();
            if (!response.ok) throw new Error(testPackage.detail || "Test simulation generation failed.");
            const packageBlob = new Blob([JSON.stringify(testPackage, null, 2)], { type: "application/json" });
            const downloadUrl = URL.createObjectURL(packageBlob);
            const download = document.createElement("a");
            download.href = downloadUrl;
            download.download = "testing-simulation-package.json";
            document.body.append(download);
            download.click();
            download.remove();
            window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 0);
            output.hidden = false;
            output.textContent = `Testing package downloaded. Status: ${testPackage.status}; coverage design map ${testPackage.test_coverage_map.coverage_percent}%; observed pass rate: unavailable; release gate ${testPackage.release_assessment.status}. No test or CI job was executed.`;
            alert("Testing simulation downloaded. All pass/fail and quality values are forecasts, not test results.");
        } catch (error) {
            output.hidden = false;
            output.textContent = error.message;
            alert(error.message, true);
        } finally {
            button.disabled = false;
        }
    });
    byId("factoryBuildPlanButton").addEventListener("click", async () => {
        const button = byId("factoryBuildPlanButton");
        const output = byId("wfFactoryResult");
        if (!byId("factoryBlueprintForm").reportValidity()) return;
        button.disabled = true;
        try {
            const response = await fetch("/workforce/factory/build-plan", {
                method: "POST", credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    title: byId("factoryTitle").value.trim(),
                    description: byId("factoryDescription").value.trim(),
                    technology_changes: byId("factoryTechnologies").value.split(",").map((item) => item.trim()).filter(Boolean),
                    backend_language: byId("factoryBackendLanguage").value,
                    semantic_version: "0.1.0",
                }),
            });
            const buildPlan = await response.json();
            if (!response.ok) throw new Error(buildPlan.detail || "Build release plan generation failed.");
            const packageBlob = new Blob([JSON.stringify(buildPlan, null, 2)], { type: "application/json" });
            const downloadUrl = URL.createObjectURL(packageBlob);
            const download = document.createElement("a");
            download.href = downloadUrl;
            download.download = `build-release-plan-${buildPlan.version_plan.semantic_version}.json`;
            document.body.append(download);
            download.click();
            download.remove();
            window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 0);
            output.hidden = false;
            output.textContent = `Build plan downloaded. Readiness: ${buildPlan.build_readiness_assessment.status} (${buildPlan.build_readiness_assessment.readiness_score_percent}%). Compilation ${buildPlan.compilation_assessment.execution_status}; no container, CI, package publication, or infrastructure action occurred.`;
            alert("Build release plan downloaded. No compilation, container build, CI/CD, publishing, or deployment was performed.");
        } catch (error) {
            output.hidden = false;
            output.textContent = error.message;
            alert(error.message, true);
        } finally {
            button.disabled = false;
        }
    });
    byId("factoryDeploymentPlanButton").addEventListener("click", async () => {
        const button = byId("factoryDeploymentPlanButton");
        const output = byId("wfFactoryResult");
        if (!byId("factoryBlueprintForm").reportValidity()) return;
        button.disabled = true;
        try {
            const response = await fetch("/workforce/factory/deployment-plan", {
                method: "POST", credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    title: byId("factoryTitle").value.trim(),
                    description: byId("factoryDescription").value.trim(),
                    technology_changes: byId("factoryTechnologies").value.split(",").map((item) => item.trim()).filter(Boolean),
                    backend_language: byId("factoryBackendLanguage").value,
                    semantic_version: "0.1.0",
                }),
            });
            const deploymentPlan = await response.json();
            if (!response.ok) throw new Error(deploymentPlan.detail || "Deployment planning failed.");
            const packageBlob = new Blob([JSON.stringify(deploymentPlan, null, 2)], { type: "application/json" });
            const downloadUrl = URL.createObjectURL(packageBlob);
            const download = document.createElement("a");
            download.href = downloadUrl;
            download.download = "deployment-plan.json";
            document.body.append(download);
            download.click();
            download.remove();
            window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 0);
            output.hidden = false;
            output.textContent = `Deployment plan downloaded. Readiness: ${deploymentPlan.readiness_report.status}; ${deploymentPlan.release_plan.waves.length} proposed waves; environment readiness ${deploymentPlan.infrastructure_readiness_report.identity_readiness.status}. No cloud calls, infrastructure changes, CI/CD, or deployments occurred.`;
            alert("Deployment plan downloaded. Readiness is blocked pending real build, test, security, infrastructure, rollback, and approval evidence.");
        } catch (error) {
            output.hidden = false;
            output.textContent = error.message;
            alert(error.message, true);
        } finally {
            button.disabled = false;
        }
    });
    byId("factoryHostingPlanButton").addEventListener("click", async () => {
        const button = byId("factoryHostingPlanButton");
        const output = byId("wfFactoryResult");
        if (!byId("factoryBlueprintForm").reportValidity()) return;
        button.disabled = true;
        try {
            const response = await fetch("/workforce/factory/hosting-plan", {
                method: "POST", credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    title: byId("factoryTitle").value.trim(),
                    description: byId("factoryDescription").value.trim(),
                    technology_changes: byId("factoryTechnologies").value.split(",").map((item) => item.trim()).filter(Boolean),
                    backend_language: byId("factoryBackendLanguage").value,
                    semantic_version: "0.1.0",
                }),
            });
            const hostingPlan = await response.json();
            if (!response.ok) throw new Error(hostingPlan.detail || "Hosting plan generation failed.");
            const packageBlob = new Blob([JSON.stringify(hostingPlan, null, 2)], { type: "application/json" });
            const downloadUrl = URL.createObjectURL(packageBlob);
            const download = document.createElement("a");
            download.href = downloadUrl;
            download.download = "hosting-plan.json";
            document.body.append(download);
            download.click();
            download.remove();
            window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 0);
            output.hidden = false;
            output.textContent = `Hosting plan downloaded. Recommendation: ${hostingPlan.application_hosting.recommended_option || "unconfirmed"}; readiness ${hostingPlan.hosting_readiness_report.status}; no Azure calls or infrastructure actions occurred.`;
            alert("Hosting plan downloaded. Service choices are proposals; no Azure APIs or infrastructure were used.");
        } catch (error) {
            output.hidden = false;
            output.textContent = error.message;
            alert(error.message, true);
        } finally {
            button.disabled = false;
        }
    });
    byId("factoryOperationsPlanButton").addEventListener("click", async () => {
        const button = byId("factoryOperationsPlanButton");
        const output = byId("wfFactoryResult");
        if (!byId("factoryBlueprintForm").reportValidity()) return;
        button.disabled = true;
        try {
            const response = await fetch("/workforce/factory/operations-plan", {
                method: "POST", credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    title: byId("factoryTitle").value.trim(),
                    description: byId("factoryDescription").value.trim(),
                    technology_changes: byId("factoryTechnologies").value.split(",").map((item) => item.trim()).filter(Boolean),
                    backend_language: byId("factoryBackendLanguage").value,
                    semantic_version: "0.1.0",
                }),
            });
            const operationsPlan = await response.json();
            if (!response.ok) throw new Error(operationsPlan.detail || "Operations plan generation failed.");
            const packageBlob = new Blob([JSON.stringify(operationsPlan, null, 2)], { type: "application/json" });
            const downloadUrl = URL.createObjectURL(packageBlob);
            const download = document.createElement("a");
            download.href = downloadUrl;
            download.download = "operations-sre-plan.json";
            document.body.append(download);
            download.click();
            download.remove();
            window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 0);
            output.hidden = false;
            output.textContent = `Operations plan downloaded. Readiness: ${operationsPlan.operations_readiness_report.status}; monitoring is planned but not configured; no alerts, tickets, integrations, or runtime activities were created.`;
            alert("Operations plan downloaded. No monitoring, alert, ticket, integration, or runtime action was performed.");
        } catch (error) {
            output.hidden = false;
            output.textContent = error.message;
            alert(error.message, true);
        } finally {
            button.disabled = false;
        }
    });
    loadData();
})();
