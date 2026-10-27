(() => {
    const state = { items: [], selectedId: null, role: "USER" };
    const $ = (id) => document.getElementById(id);
    const queue = $("approvalQueue");
    const detail = $("approvalDetail");
    const filter = $("queueFilter");
    const alertBox = $("approvalAlert");

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = String(text);
        return node;
    }
    function formatDate(value) {
        if (!value) return "";
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? "" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
    }
    function showAlert(message) {
        alertBox.textContent = message || "";
        alertBox.hidden = !message;
    }
    function renderQueue() {
        const filtered = state.items.filter((item) => filter.value === "all" || item.status === "Pending");
        queue.replaceChildren();
        const pendingCount = state.items.filter((item) => item.status === "Pending").length;
        $("pendingCount").textContent = String(pendingCount);
        if (!filtered.length) {
            queue.append(el("p", "queue-empty", state.items.length ? "No pending approvals in this view." : "No approvals are currently assigned to you."));
            return;
        }
        filtered.forEach((item) => {
            const button = el("button", `approval-card${state.selectedId === item.approval_id ? " selected" : ""}`);
            button.type = "button";
            const icon = el("span", "approval-card-icon", item.stage === "CEO_REVIEW" ? "CEO" : "✓");
            const copy = el("span", "approval-card-copy");
            copy.append(el("strong", "", item.requirement_title || "Business requirement"), el("small", "", `${item.requirement_priority || "Priority not set"} · ${item.stage || "Review"} · ${formatDate(item.created_at_utc)}`));
            button.append(icon, copy, el("span", `approval-state ${String(item.status).toLowerCase()}`, item.status));
            button.addEventListener("click", () => selectApproval(item.approval_id));
            queue.append(button);
        });
    }
    function selectApproval(id) {
        state.selectedId = id;
        renderQueue();
        const approval = state.items.find((item) => item.approval_id === id);
        detail.replaceChildren();
        if (!approval) return;

        const header = el("header", "approval-detail-header");
        const titleBlock = el("div");
        titleBlock.append(el("h2", "", approval.requirement_title || "Business requirement"));
        titleBlock.append(el("p", "", `Approval ${approval.approval_id} · ${approval.stage} · submitted ${formatDate(approval.created_at_utc)}`));
        header.append(titleBlock, el("span", "decision-badge", approval.status));
        detail.append(header);

        const context = el("section", "request-context");
        context.append(el("strong", "", "REQUEST SUMMARY"));
        context.append(el("p", "", `Priority: ${approval.requirement_priority || "Not set"}\nRequest status: ${approval.requirement_status || "Not set"}\nApproval stage: ${approval.stage}\nAssigned approver: ${approval.assigned_to_user_id}`));
        detail.append(context);

        if (approval.status !== "Pending" || !approval.can_decide) {
            const closed = el("div", "decision-notice", `This approval is ${approval.status.toLowerCase()}. Its decision is recorded and cannot be changed here.`);
            if (!approval.can_decide && approval.status === "Pending") {
                closed.textContent = "You can view this approval, but only its assigned approver or Owner/Super Admin can record a decision.";
            }
            detail.append(closed);
            if (approval.comments) {
                const reason = el("section", "request-context");
                reason.append(el("strong", "", "RECORDED DECISION REASON"), el("p", "", approval.comments));
                detail.append(reason);
            }
            return;
        }

        const label = el("label", "reason-label", "Decision reason (required)");
        label.htmlFor = "decisionReason";
        const textarea = document.createElement("textarea");
        textarea.id = "decisionReason";
        textarea.className = "decision-reason";
        textarea.maxLength = 2000;
        textarea.minLength = 5;
        textarea.placeholder = "Explain the decision, conditions, or information needed…";
        detail.append(label, textarea, el("p", "decision-help", "The reason becomes part of the permanent approval audit record."));

        const actions = el("div", "decision-actions");
        [
            ["approve", "Approve", "approve-action"],
            ["request_information", "Request information", "info-action"],
            ["reject", "Reject", "reject-action"],
        ].forEach(([action, labelText, className]) => {
            const button = el("button", className, labelText);
            button.type = "button";
            button.addEventListener("click", () => submitDecision(approval, action, textarea, button, actions));
            actions.append(button);
        });
        detail.append(actions, el("p", "decision-notice", "Approving only advances the workflow after all approvals in this stage are approved. Rejection or an information request stops delivery."));
    }

    async function submitDecision(approval, action, textarea, activeButton, actions) {
        const reason = textarea.value.trim();
        if (reason.length < 5) {
            textarea.setCustomValidity("Enter a reason of at least 5 characters.");
            textarea.reportValidity();
            return;
        }
        textarea.setCustomValidity("");
        actions.querySelectorAll("button").forEach((button) => { button.disabled = true; });
        activeButton.textContent = "Recording…";
        showAlert("");
        try {
            const response = await fetch(`/approvals/${encodeURIComponent(approval.approval_id)}/decision`, {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action, reason }),
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.detail || `Decision failed (${response.status}).`);
            showAlert(action === "approve" ? "Approval recorded. The workflow will continue when all required approvals pass." : "Decision recorded. Downstream workflow is on hold.");
            await loadApprovals();
            selectApproval(result.approval_id);
        } catch (error) {
            showAlert(error.message);
            actions.querySelectorAll("button").forEach((button) => { button.disabled = false; });
            activeButton.textContent = action === "approve" ? "Approve" : action === "reject" ? "Reject" : "Request information";
        }
    }

    async function loadApprovals() {
        queue.replaceChildren(el("p", "queue-empty", "Loading approval queue…"));
        showAlert("");
        try {
            const [profileResponse, approvalsResponse] = await Promise.all([
                fetch("/auth/me", { credentials: "same-origin" }),
                fetch("/approvals", { credentials: "same-origin" }),
            ]);
            const profile = await profileResponse.json().catch(() => ({}));
            const data = await approvalsResponse.json().catch(() => ({}));
            if (!profileResponse.ok || !approvalsResponse.ok) throw new Error(data.detail || "Your role cannot access the approval queue.");
            state.role = profile.role || "USER";
            $("roleLabel").textContent = state.role.replaceAll("_", " ");
            state.items = Array.isArray(data) ? data : [];
            renderQueue();
            if (state.selectedId && state.items.some((item) => item.approval_id === state.selectedId)) selectApproval(state.selectedId);
            else {
                state.selectedId = null;
                detail.replaceChildren();
                const empty = el("div", "detail-empty");
                empty.append(el("span", "", "✓"), el("h2", "", state.items.length ? "Select an approval" : "No approval items"), el("p", "", state.items.length ? "Choose an item to review the request and record a reasoned decision." : "Pending approvals assigned to you will appear here."));
                detail.append(empty);
            }
        } catch (error) {
            state.items = [];
            renderQueue();
            detail.replaceChildren(el("div", "detail-empty", error.message));
            showAlert(error.message);
        }
    }

    filter.addEventListener("change", renderQueue);
    $("refreshApprovals").addEventListener("click", loadApprovals);
    loadApprovals();
})();
