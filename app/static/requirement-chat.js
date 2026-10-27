(() => {
    const questions = [
        { key: "problem", label: "Business problem", prompt: "What business problem or opportunity should we address? Tell me what is happening today and what is difficult." },
        { key: "outcome", label: "Expected outcome", prompt: "What should be different when this work is successful? Describe the outcome or measurable result you need." },
        { key: "users", label: "Users and stakeholders", prompt: "Who will use or be affected by the solution? Include teams, approximate user counts, and decision owners if known." },
        { key: "systems", label: "Systems and data", prompt: "Which systems, data sources, or integrations are involved? It is fine to say that these are not known yet." },
        { key: "constraints", label: "Constraints and security", prompt: "What constraints should the delivery team know about, such as security, privacy, compliance, accessibility, or budget? Do not include secrets." },
        { key: "deadline", label: "Timing and dependencies", prompt: "Is there a target date, deadline, or dependency? What is driving the timing?" },
    ];
    const state = { answers: {}, queue: [...questions], position: 0, priority: "Medium", requester: "Business User", savedId: null, dynamicAsked: new Set() };
    const byId = (id) => document.getElementById(id);
    const messages = byId("chatMessages");
    const form = byId("chatForm");
    const input = byId("answerInput");
    const sendButton = byId("sendButton");
    const submitButton = byId("submitRequirement");
    const priorityButtons = [...document.querySelectorAll("[data-priority]")];
    let toastTimer;

    function requesterName() {
        return localStorage.getItem("userName") || "Business User";
    }

    function escapeHtml(value) {
        return String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
    }

    function addMessage(role, text) {
        const row = document.createElement("div");
        row.className = `message-row ${role}`;
        const avatar = role === "assistant" ? '<span class="message-avatar">CE</span>' : "";
        const safeText = escapeHtml(text);
        row.innerHTML = `${avatar}<div class="message-bubble">${safeText}<span class="message-time">${new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date())}</span></div>`;
        messages.append(row);
        messages.scrollTop = messages.scrollHeight;
    }

    function showToast(text, isError = false) {
        const toast = byId("toast");
        toast.textContent = text;
        toast.classList.toggle("error", isError);
        toast.classList.add("visible");
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => toast.classList.remove("visible"), 4200);
    }

    function syncSummary() {
        const mapping = { problem: "summaryProblem", outcome: "summaryOutcome", users: "summaryUsers", systems: "summarySystems", constraints: "summaryConstraints" };
        Object.entries(mapping).forEach(([key, id]) => {
            const target = byId(id);
            const value = state.answers[key];
            target.textContent = value || (key === "problem" || key === "outcome" ? "Waiting for your response" : "Not discussed yet");
            target.classList.toggle("filled", Boolean(value));
        });
        byId("summaryRequester").textContent = state.requester;
        const completedTopics = questions.filter((question) => state.answers[question.key]).length;
        const step = Math.min(completedTopics + 1, questions.length);
        document.querySelector(".step-current").textContent = String(step).padStart(2, "0");
        document.querySelector(".step-line").style.background = `linear-gradient(90deg,#5aa87b 0 ${Math.min(completedTopics / questions.length * 100, 100)}%,#e0e8e0 ${Math.min(completedTopics / questions.length * 100, 100)}%)`;
        submitButton.disabled = !(state.answers.problem && state.answers.outcome && state.position >= state.queue.length);
    }

    function showQuestion(acknowledgment = "") {
        syncSummary();
        const current = state.queue[state.position];
        if (!current) {
            addMessage("assistant", `${acknowledgment ? `${acknowledgment}\n\n` : ""}Your business brief is ready to review. Check the summary, choose the urgency, and submit when it looks right. You can still add context above before submitting.`);
            byId("promptHint").textContent = "Your draft is not saved until you submit it.";
            input.placeholder = "Add any final context or clarification…";
            input.required = false;
            sendButton.querySelector("span:first-child").textContent = "Add context";
            return;
        }
        byId("promptHint").textContent = `Discovery topic ${state.position + 1}: ${current.label}. You can answer “not sure” and we’ll record it as an open question.`;
        input.placeholder = "Type your response…";
        input.required = true;
        sendButton.querySelector("span:first-child").textContent = "Send answer";
        addMessage("assistant", `${acknowledgment ? `${acknowledgment}\n\n` : ""}${current.prompt}`);
    }

    function acknowledgeAnswer(question, answer) {
        if (/^(not sure|unknown|i don't know|i do not know|n\/a)$/i.test(answer.trim())) {
            return `I’ve marked ${question.label.toLowerCase()} as an open question so the team won’t have to guess.`;
        }
        return `I’ve added your response to the ${question.label.toLowerCase()} section of the live brief.`;
    }

    function selectPriority(priority) {
        state.priority = priority;
        priorityButtons.forEach((button) => {
            const selected = button.dataset.priority === priority;
            button.classList.toggle("selected", selected);
            button.setAttribute("aria-pressed", String(selected));
        });
        if (priority === "High" || priority === "Critical") {
            byId("promptHint").textContent = "High and Critical requests are automatically sent to the current AI CEO assessment endpoint after submission. This MVP assessment is rule-based.";
        }
    }

    function addConditionalQuestion(answer) {
        const text = answer.toLowerCase();
        let followUp = null;
        if (/(personal data|personal information|employee (contact )?data|health data|privacy|gdpr|pii)/.test(text) && !state.dynamicAsked.has("privacy")) {
            state.dynamicAsked.add("privacy");
            followUp = { key: "clarification_privacy", label: "Data privacy detail", prompt: "You mentioned sensitive or personal data. Which data categories are involved, who may access them, and are there retention or residency requirements? Please do not share actual personal records." };
        } else if (/(integrat|api|sharepoint|salesforce|servicenow|power bi|powerbi|sap|oracle|sql server|microsoft 365)/.test(text) && !state.dynamicAsked.has("integration")) {
            state.dynamicAsked.add("integration");
            followUp = { key: "clarification_integration", label: "Integration detail", prompt: "You mentioned existing systems. Which system should be the source of truth, and does the solution need to read data, write data, or both? Unknown is a valid answer." };
        }
        if (followUp) state.queue.splice(state.position + 1, 0, followUp);
    }

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        const answer = input.value.trim();
        if (!answer) return;
        if (state.position >= state.queue.length) {
            state.answers.final_context = [state.answers.final_context, answer].filter(Boolean).join("\n");
            addMessage("user", answer);
            addMessage("assistant", "Added that context to your draft. Review the brief on the right, then submit when ready.");
            input.value = "";
            byId("characterCount").textContent = "0 / 2000";
            return;
        }
        const current = state.queue[state.position];
        state.answers[current.key] = answer;
        addMessage("user", answer);
        addConditionalQuestion(answer);
        state.position += 1;
        input.value = "";
        byId("characterCount").textContent = "0 / 2000";
        showQuestion(acknowledgeAnswer(current, answer));
        input.focus();
    });

    input.addEventListener("input", () => {
        byId("characterCount").textContent = `${input.value.length} / 2000`;
    });

    priorityButtons.forEach((button) => button.addEventListener("click", () => selectPriority(button.dataset.priority)));

    function composeDescription() {
        const labels = {
            problem: "Business problem", outcome: "Expected outcome", users: "Users and stakeholders", systems: "Systems and data",
            constraints: "Constraints and security", deadline: "Timing and dependencies", clarification_privacy: "Data privacy clarification",
            clarification_integration: "Integration clarification", final_context: "Additional context",
        };
        return state.queue.filter((question) => state.answers[question.key]).map((question) => `${labels[question.key] || question.label}:\n${state.answers[question.key]}`).join("\n\n");
    }

    function makeTitle(problem) {
        const firstSentence = problem.split(/[.!?\n]/, 1)[0].trim();
        const title = firstSentence.length > 180 ? `${firstSentence.slice(0, 177).trimEnd()}...` : firstSentence;
        return title.length >= 3 ? title : `Business requirement: ${title}`;
    }

    async function postJson(url, body) {
        const response = await fetch(url, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.detail || `Request failed (${response.status})`);
        return result;
    }

    async function runAssessment(requirementId) {
        return postJson(`/requirements/${requirementId}/assess`, { requested_by: state.requester, force_reassessment: false });
    }

    function completeView(requirement, assessment) {
        messages.replaceChildren();
        addMessage("assistant", `Your requirement has been saved as ${requirement.requirement_id}. Current status: ${requirement.status}.`);
        const blueprint = requirement.workforce_blueprint;
        if (blueprint) {
            const roleNames = blueprint.roles.map((role) => role.role_name);
            const technologyNames = blueprint.requirement.technology_changes || [];
            addMessage("assistant", `Workforce blueprint prepared for review: ${roleNames.length} proposed roles across ${blueprint.teams.length} teams${roleNames.length ? ` (${roleNames.join(", ")})` : ""}.${technologyNames.length ? ` Technology upskilling suggestions: ${technologyNames.join(", ")}.` : ""} This is a deterministic planning recommendation only; no agent records, assignments, certifications, activations, or retirements were created.`);
            const lifecyclePlan = blueprint.agent_lifecycle_package;
            if (lifecyclePlan) {
                addMessage("assistant", `Agent lifecycle simulation: ${lifecyclePlan.agent_profiles.length} in-scope profiles and ${lifecyclePlan.agent_catalog.length} catalog roles. Certification paths and lifecycle gates are proposals; assignment readiness is ${lifecyclePlan.assignment_readiness.status}. Authority: ${lifecyclePlan.authority}. No agent records or certifications were created, and no agents were activated or assigned.`);
            }
            const assignmentPlan = blueprint.assignment_recommendation_package;
            if (assignmentPlan) {
                addMessage("assistant", `Assignment planning: ${assignmentPlan.assignment_blueprint.work_items.length} work items mapped to role recommendations. Workforce Director status: ${assignmentPlan.assignment_readiness.status}; verified readiness score: unavailable without independently verified candidate evidence. Authority: ${assignmentPlan.authority}. No assignments, activation, or provisioning occurred.`);
            }
            const testPlan = blueprint.testing_execution_package;
            if (testPlan) {
                addMessage("assistant", `Testing simulation plan: ${testPlan.test_coverage_map.coverage_percent}% test-domain design coverage; observed pass rate and code coverage are unavailable because tests were not run. Release assessment: ${testPlan.release_assessment.status}. This is artifact-based planning only; no tests, CI jobs, or environments were executed or created.`);
            }
            const buildPlan = blueprint.build_execution_package;
            if (buildPlan) {
                addMessage("assistant", `Build/release planning: ${buildPlan.artifact_manifest.artifacts.length} source artifacts mapped; dependency compatibility ${buildPlan.dependency_analysis.compatibility_report.status}; compilation ${buildPlan.compilation_assessment.execution_status}; build readiness ${buildPlan.build_readiness_assessment.status}. No compilation, container build, package publication, CI/CD, infrastructure, or deployment was performed.`);
            }
            const deploymentPlan = blueprint.deployment_execution_package;
            if (deploymentPlan) {
                addMessage("assistant", `Deployment planning: ${deploymentPlan.release_plan.waves.length} proposed waves; readiness ${deploymentPlan.readiness_report.status}; environment readiness ${deploymentPlan.infrastructure_readiness_report.identity_readiness.status}. No environment or infrastructure was created, no cloud API was called, and no deployment or runtime activity occurred.`);
            }
            const hostingPlan = blueprint.hosting_execution_package;
            if (hostingPlan) {
                addMessage("assistant", `Hosting plan: ${hostingPlan.application_hosting.recommended_option || "service choice unconfirmed"}; readiness ${hostingPlan.hosting_readiness_report.status}. Environment, network, identity, data, monitoring, and recovery plans are proposals only. No Azure API calls or infrastructure actions occurred.`);
            }
            const operationsPlan = blueprint.operations_execution_package;
            if (operationsPlan) {
                addMessage("assistant", `Operations/SRE planning: ${operationsPlan.runbook_catalog.length} proposed runbooks; readiness ${operationsPlan.operations_readiness_report.status}; measured capacity and cost remain unavailable. Monitoring, alerts, tickets, integrations, and runtime activities were not created.`);
            }
            const approvalPlan = blueprint.approval_sandbox_package;
            if (approvalPlan) {
                addMessage("assistant", `Supervised approval sandbox: ${approvalPlan.approval_recommendation_engine.recommendations && Object.keys(approvalPlan.approval_recommendation_engine.recommendations).length} recommendations and ${approvalPlan.review_queue.length} simulated review items. Confidence is uncalibrated; approval accuracy is unavailable without decisions. Human reviewers retain all authority. No approval, workflow transition, audit event, override, or decision record was created.`);
            }
            const projectPlan = blueprint.project_delivery_package;
            if (projectPlan) {
                addMessage("assistant", `Project delivery plan prepared: ${projectPlan.epic_catalog.length} proposed epics, ${projectPlan.feature_catalog.length} features, ${projectPlan.user_story_catalog.length} user stories, and ${projectPlan.task_catalog.length} task outlines across ${projectPlan.sprint_plan.sprint_count_estimate} estimated sprints. ${projectPlan.sprint_plan.capacity_basis} No project, epic, feature, story, task, sprint, or assignment records were created.`);
            }
            const deliveryPlan = blueprint.delivery_execution_package;
            if (deliveryPlan) {
                addMessage("assistant", `Delivery simulation: critical-path estimate ${deliveryPlan.delivery_blueprint.critical_path_sprint_estimate} sprints; ${deliveryPlan.risk_register.risk_count} planning risks; readiness ${deliveryPlan.project_health.readiness_score}% (${deliveryPlan.project_health.readiness_status}); capacity and velocity are assumption-based, and all role recommendations remain unassigned. No execution, project changes, or deployment occurred.`);
            }
            const packageArtifacts = blueprint.technical_delivery_package?.artifacts;
            if (packageArtifacts) {
                const executive = packageArtifacts.executive_assessment;
                const architecture = packageArtifacts.architecture_blueprint;
                const database = packageArtifacts.database_blueprint;
                const api = packageArtifacts.api_catalog;
                const ui = packageArtifacts.ui_blueprint;
                const security = packageArtifacts.security_blueprint;
                const testing = packageArtifacts.testing_blueprint;
                const deployment = packageArtifacts.deployment_blueprint;
                const workforce = packageArtifacts.workforce_plan;
                addMessage("assistant", `Technical delivery package (${blueprint.technical_delivery_package.status})\n\nCEO: ${executive.business_domain} · ${executive.solution_type} · ${executive.complexity} complexity · ${executive.priority} priority\nArchitecture: ${architecture.architecture_style}\nDatabase: ${database.entities.length} proposed entities · ${database.relationships.length} proposed relationships\nBackend/API: ${architecture.backend_design.service_boundaries.length} service boundaries · ${api.endpoints.length} proposed endpoints\nFrontend: ${ui.screens.length} proposed screens\nSecurity: ${security.authentication_design}\nTesting: ${testing.unit_tests.length} unit, ${testing.integration_tests.length} integration, ${testing.uat_scenarios.length} UAT, ${testing.security_tests.length} security, ${testing.performance_tests.length} performance scenarios\nDeployment: ${deployment.deployment_status}\nWorkforce: ${workforce.required_agents} proposed role assignments\n\nDesign proposals only. No code, schema, API, infrastructure, deployment, runtime, approval, or agent assignment was created.`);
            }
        }
        if (assessment) {
            const result = assessment.assessment;
            addMessage("assistant", `The current rule-based AI CEO assessment is complete.\n\n${result.executive_summary}\n\nClassification: ${result.classification}\nComplexity: ${result.complexity} · Risk: ${result.risk_level}\nHuman approval required: ${result.human_approval_required ? "Yes" : "No"}\n\nThis assessment is advisory. It does not authorize budget or delivery.`);
        }
        if (state.priority === "High" || state.priority === "Critical") {
            byId("promptHint").textContent = assessment ? "Assessment has completed. Follow the approval workflow before delivery." : "Requirement saved. The automatic assessment did not complete; your request is still saved.";
        } else {
            byId("promptHint").textContent = "Requirement saved. An authorized reviewer can assess it through the requirement workflow.";
        }
        const draft = document.querySelector(".draft-label");
        draft.classList.add("saved");
        draft.innerHTML = "<i></i>Submitted";
        input.disabled = true;
        sendButton.disabled = true;
        submitButton.disabled = true;
        submitButton.querySelector("span:first-child").textContent = "Requirement submitted";
        byId("restartButton").disabled = true;
        if (!assessment && (state.priority === "High" || state.priority === "Critical")) {
            const retry = document.createElement("button");
            retry.type = "button";
            retry.className = "submit-button";
            retry.style.marginTop = "8px";
            retry.textContent = "Retry CEO assessment";
            retry.addEventListener("click", async () => {
                retry.disabled = true;
                retry.textContent = "Assessment running…";
                try {
                    const result = await runAssessment(requirement.requirement_id);
                    addMessage("assistant", `The rule-based AI CEO assessment is complete. ${result.assessment.executive_summary}`);
                    retry.remove();
                } catch (error) {
                    retry.disabled = false;
                    retry.textContent = "Retry CEO assessment";
                    showToast(`Assessment retry failed: ${error.message}`, true);
                }
            });
            submitButton.after(retry);
        }
    }

    submitButton.addEventListener("click", async () => {
        if (submitButton.disabled || state.savedId) return;
        submitButton.disabled = true;
        submitButton.querySelector("span:first-child").textContent = "Submitting…";
        const body = {
            title: makeTitle(state.answers.problem),
            description: composeDescription(),
            requested_by: state.requester,
            priority: state.priority,
        };
        try {
            const requirement = await postJson("/requirements", body);
            state.savedId = requirement.requirement_id;
            document.querySelector(".draft-label").innerHTML = "<i></i>Saved";
            let assessment = null;
            if (state.priority === "High" || state.priority === "Critical") {
                byId("promptHint").textContent = "Requirement saved. Running the current rule-based CEO assessment…";
                try {
                    assessment = await runAssessment(requirement.requirement_id);
                } catch (error) {
                    showToast(`Saved successfully, but assessment failed: ${error.message}`, true);
                }
            }
            completeView(requirement, assessment);
            showToast(assessment ? "Requirement saved and assessment completed." : "Requirement saved.");
        } catch (error) {
            submitButton.disabled = false;
            submitButton.querySelector("span:first-child").textContent = "Submit requirement";
            showToast(`Could not save requirement: ${error.message}`, true);
        }
    });

    byId("restartButton").addEventListener("click", () => window.location.reload());
    state.requester = requesterName();
    selectPriority("Medium");
    addMessage("assistant", `Hello${state.requester !== "Business User" ? `, ${state.requester}` : ""}. I’m the AI CEO intake assistant. I’ll ask a few focused questions, summarize your answers, then let you review before saving. What business problem or opportunity should we address?`);
    byId("promptHint").textContent = "Discovery topic 1: Business problem. You can answer “not sure” and we’ll record it as an open question.";
    byId("summaryRequester").textContent = state.requester;
    input.focus();
})();
