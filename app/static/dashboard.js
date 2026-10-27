let currentUser = null;

function showDashboardError(message) {
    const element = document.getElementById("dashboardError");
    element.textContent = message;
    element.hidden = !message;
}

function userFacingApiError(status) {
    if (status === 401 || status === 403) return "You do not have access to this feature.";
    return "The requested information is unavailable right now.";
}

async function fetchJson(url, options = {}) {
    let response;
    try {
        response = await fetch(url, { credentials: "same-origin", ...options });
    } catch {
        throw new Error("Unable to connect to the service. Check your connection and try again.");
    }
    if (!response.ok) throw new Error(userFacingApiError(response.status));
    return response.json();
}

async function loadProfile() {
    try {
        const user = await fetchJson("/auth/me");
        currentUser = user;
        document.getElementById("userName").textContent = user.display_name || "Workspace user";
        document.getElementById("userAvatar").textContent = (user.display_name || "U")
            .split(/\s+/).slice(0, 2).map((part) => part.charAt(0).toUpperCase()).join("");
        document.getElementById("roleBadge").textContent = user.role || "USER";
        document.querySelectorAll("[data-allowed-roles]").forEach((link) => {
            const allowedRoles = link.dataset.allowedRoles.split(",");
            link.hidden = !allowedRoles.includes(user.role);
        });
        const projectsLink = document.getElementById("projectsNavigation");
        if (projectsLink.hidden) {
            projectsLink.hidden = false;
            projectsLink.href = "#myProjects";
            projectsLink.textContent = "▧ My projects";
        }
        return user;
    } catch (error) {
        showDashboardError(error.message);
        return null;
    }
}

function renderRecordList(elementId, records, labelFor, emptyMessage) {
    const list = document.getElementById(elementId);
    list.replaceChildren();
    if (!records?.length) {
        const empty = document.createElement("p");
        empty.className = "personal-data-empty";
        empty.textContent = emptyMessage;
        list.append(empty);
        return;
    }
    records.slice(0, 8).forEach((record) => {
        const row = document.createElement("div");
        row.className = "personal-data-row";
        const title = document.createElement("strong");
        title.textContent = labelFor(record);
        const status = document.createElement("span");
        status.textContent = record.Status || record.status || "Available";
        row.append(title, status);
        list.append(row);
    });
}

async function loadDashboard(user) {
    try {
        const dashboardUrl = user.role === "USER" ? "/dashboard/api/me" : "/dashboard/api";
        const data = await fetchJson(dashboardUrl);
        document.getElementById("requirementsCount").textContent = data.requirements ?? 0;
        document.getElementById("assessmentsCount").textContent = data.assessments ?? 0;
        document.getElementById("projectsCount").textContent = data.projects ?? 0;
        document.getElementById("approvalsCount").textContent = data.approvals ?? 0;
        renderRecordList("myRequirementsList", data.my_requirements,
            (item) => item.Title, "No requirements created by this account yet.");
        renderRecordList("myProjectsList", data.my_projects,
            (item) => item.ProjectName, "No projects are linked to this account yet.");
        renderRecordList("myTasksList", data.my_tasks,
            (item) => item.Description, "No tasks are linked to this account yet.");
        renderRecordList("myApprovalsList", data.my_approvals,
            (item) => item.RequirementTitle, "No approvals are assigned to or linked to this account.");
        renderNotifications(data.my_notifications || []);
        showDashboardError("");
    } catch (error) {
        showDashboardError(error.message);
        ["myRequirementsList", "myProjectsList", "myTasksList", "myApprovalsList"].forEach((id) => {
            document.getElementById(id).replaceChildren();
        });
        renderNotifications([]);
    }
}

function renderNotifications(notifications) {
    const list = document.getElementById("notificationList");
    const unreadCount = notifications.filter((item) => !item.IsRead).length;
    document.getElementById("unreadCount").textContent = `${unreadCount} unread`;
    list.replaceChildren();
    if (!notifications.length) {
        const empty = document.createElement("p");
        empty.className = "notification-empty";
        empty.textContent = "No notifications for this account yet.";
        list.append(empty);
        return;
    }
    notifications.slice(0, 8).forEach((item) => {
        const row = document.createElement("article");
        row.className = `notification-row${item.IsRead ? "" : " unread"}`;
        const mark = document.createElement("span");
        mark.className = "notification-mark";
        mark.textContent = item.NotificationType === "APPROVAL_REQUIRED" ? "✓" : "•";
        const copy = document.createElement("div");
        copy.className = "notification-copy";
        const title = document.createElement("strong");
        title.textContent = item.Title;
        const body = document.createElement("p");
        body.textContent = item.Body;
        copy.append(title, body);
        const date = document.createElement("time");
        date.textContent = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(item.CreatedAtUtc));
        row.append(mark, copy, date);
        if (!item.IsRead) {
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = "Mark read";
            button.addEventListener("click", async () => {
                try {
                    await fetchJson(`/notifications/${encodeURIComponent(item.NotificationID)}/read`, { method: "POST" });
                    if (currentUser) await loadDashboard(currentUser);
                } catch (error) {
                    showDashboardError(error.message);
                }
            });
            row.append(button);
        }
        list.append(row);
    });
}

function logout() {
    fetch("/auth/logout", { method: "POST", credentials: "same-origin" })
        .finally(() => { window.location = "/login"; });
}

loadProfile().then((user) => {
    if (user) return loadDashboard(user);
});