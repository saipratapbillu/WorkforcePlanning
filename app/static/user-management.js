(() => {
    const status = document.getElementById("status");
    const table = document.getElementById("userTable");
    let catalogs = { roles: [], skills: [], companies: [], departments: [], positions: [], managers: [] };

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

    function showStatus(message, failed = false) {
        status.textContent = message;
        status.classList.toggle("error", failed);
    }

    function cell(row, value) {
        const td = document.createElement("td");
        td.textContent = value === null || value === undefined ? "—" : String(value);
        row.append(td);
        return td;
    }

    function actionButton(parent, text, action, secondary = false) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = text;
        if (secondary) button.className = "secondary";
        button.addEventListener("click", action);
        parent.append(button);
    }

    async function runAction(action) {
        try {
            await action();
            await loadUsers();
            showStatus("User action completed.");
        } catch (error) {
            showStatus(error.message, true);
        }
    }

    function ask(label, current = "") {
        return window.prompt(label, current);
    }

    function setOptions(elementId, values, labelFor, placeholder) {
        const select = document.getElementById(elementId);
        const previous = select.value;
        select.replaceChildren();
        const empty = document.createElement("option");
        empty.value = "";
        empty.textContent = placeholder;
        select.append(empty);
        for (const value of values) {
            const option = document.createElement("option");
            option.value = value.id;
            option.textContent = labelFor(value);
            select.append(option);
        }
        if (values.some((value) => value.id === previous)) select.value = previous;
    }

    async function loadCatalogs() {
        catalogs = await request("/admin/users/catalogs");
        setOptions("roleId", catalogs.roles, (item) => `${item.name} · ${item.code} · ${item.id}`, "Choose an active role");
        setOptions("managerId", catalogs.managers, (item) => `${item.name} · ${item.email}`, "No manager");
        setOptions("companyId", catalogs.companies, (item) => `${item.name} · ${item.id}`, "No organization assignment");
        setOptions("departmentId", [], (item) => item.name, "Select a company first");
        setOptions("positionId", [], (item) => item.name, "Select a department first");
    }

    async function loadUsers() {
        const params = new URLSearchParams({ limit: "100", offset: "0" });
        const query = document.getElementById("search").value.trim();
        const active = document.getElementById("activeFilter").value;
        if (query) params.set("q", query);
        if (active) params.set("active", active);
        const result = await request(`/admin/users?${params}`);
        table.replaceChildren();
        const grid = document.createElement("table");
        const head = document.createElement("thead");
        const header = document.createElement("tr");
        for (const name of ["Email", "Name", "Role", "Department", "Organization IDs", "Manager ID", "Status", "Actions"]) {
            const th = document.createElement("th");
            th.textContent = name;
            header.append(th);
        }
        head.append(header);
        const body = document.createElement("tbody");
        for (const user of result.items) {
            const row = document.createElement("tr");
            cell(row, user.email);
            cell(row, user.display_name);
            cell(row, `${user.role_code || "—"} (${user.role_id})`);
            cell(row, user.department);
            cell(row, `Company: ${user.company_id || "—"}\nDepartment: ${user.department_id || "—"}\nPosition: ${user.position_id || "—"}`);
            cell(row, user.manager_user_id);
            cell(row, user.is_active ? "Active" : "Disabled");
            const actions = document.createElement("td");
            actions.className = "actions";
            actionButton(actions, "Edit", async () => {
                const email = ask("Email", user.email);
                if (email === null) return;
                const displayName = ask("Display name", user.display_name);
                if (displayName === null) return;
                const department = ask("Department label (blank clears)", user.department || "");
                if (department === null) return;
                const manager = ask("Manager UUID (blank clears)", user.manager_user_id || "");
                if (manager === null) return;
                const patch = {
                    email,
                    display_name: displayName,
                    department: department || null,
                    manager_user_id: manager || null,
                };
                await runAction(() => request(`/admin/users/${user.user_id}`, { method: "PATCH", body: JSON.stringify(patch) }));
            });
            actionButton(actions, "Role", async () => {
                const roleId = ask("New role UUID", user.role_id);
                if (!roleId) return;
                await runAction(() => request(`/admin/users/${user.user_id}/role`, {
                    method: "PUT", body: JSON.stringify({ role_id: roleId }),
                }));
            }, true);
            actionButton(actions, "Organization", async () => {
                const company = ask("Company UUID", user.company_id || "");
                if (!company) return;
                const department = ask("Department UUID", user.department_id || "");
                if (!department) return;
                const position = ask("Position UUID", user.position_id || "");
                if (!position) return;
                await runAction(() => request(`/admin/users/${user.user_id}/organization`, {
                    method: "PUT",
                    body: JSON.stringify({ company_id: company, department_id: department, position_id: position }),
                }));
            }, true);
            actionButton(actions, "Skills", async () => {
                const current = await request(`/admin/users/${user.user_id}/skills`);
                const availableSkills = catalogs.skills.map((skill) => `${skill.name} (${skill.id})`).join("\n");
                const text = ask(
                    `Available skills:\n${availableSkills}\n\nEnter skills JSON array: [{skill_id, proficiency, status, evidence}]`,
                    JSON.stringify(current.skills.map((skill) => ({
                        skill_id: skill.skill_id,
                        proficiency: skill.proficiency,
                        status: skill.status,
                        evidence: skill.evidence,
                    })), null, 2),
                );
                if (text === null) return;
                const skills = JSON.parse(text);
                await runAction(() => request(`/admin/users/${user.user_id}/skills`, {
                    method: "PUT", body: JSON.stringify({ skills }),
                }));
            }, true);
            actionButton(actions, "Reset password", async () => {
                const dialog = document.getElementById("passwordResetDialog");
                document.getElementById("passwordResetTarget").textContent = user.email;
                document.getElementById("resetPasswordValue").value = "";
                dialog.dataset.userId = user.user_id;
                dialog.showModal();
            }, true);
            if (user.is_active) {
                actionButton(actions, "Disable", async () => {
                    if (!window.confirm(`Disable ${user.email}?`)) return;
                    await runAction(() => request(`/admin/users/${user.user_id}/disable`, { method: "POST" }));
                });
                actionButton(actions, "Delete", async () => {
                    if (!window.confirm(`Soft-delete ${user.email}?`)) return;
                    await runAction(() => request(`/admin/users/${user.user_id}`, { method: "DELETE" }));
                }, true);
            } else {
                actionButton(actions, "Enable", async () => {
                    await runAction(() => request(`/admin/users/${user.user_id}/enable`, { method: "POST" }));
                });
            }
            row.append(actions);
            body.append(row);
        }
        grid.append(head, body);
        table.append(grid);
        if (!result.items.length) {
            const empty = document.createElement("p");
            empty.textContent = "No users matched the selected filters.";
            table.append(empty);
        }
    }

    document.getElementById("createForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const optionalValue = (id) => document.getElementById(id).value || null;
        const companyId = optionalValue("companyId");
        const departmentId = optionalValue("departmentId");
        const positionId = optionalValue("positionId");
        if ((companyId || departmentId || positionId) && !(companyId && departmentId && positionId)) {
            return showStatus("Choose a valid company, department, and position together, or leave all three unassigned.", true);
        }
        const body = {
            email: document.getElementById("email").value,
            password: document.getElementById("password").value,
            display_name: document.getElementById("displayName").value,
            role_id: document.getElementById("roleId").value,
            department: optionalValue("department"),
            manager_user_id: optionalValue("managerId"),
            company_id: companyId,
            department_id: departmentId,
            position_id: positionId,
        };
        try {
            await request("/admin/users", { method: "POST", body: JSON.stringify(body) });
            event.currentTarget.reset();
            showStatus("User created.");
            await loadUsers();
        } catch (error) { showStatus(error.message, true); }
    });

    const passwordResetDialog = document.getElementById("passwordResetDialog");
    document.getElementById("cancelPasswordReset").addEventListener("click", () => passwordResetDialog.close());
    document.getElementById("passwordResetForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const password = document.getElementById("resetPasswordValue").value;
        try {
            await request(`/admin/users/${passwordResetDialog.dataset.userId}/reset-password`, {
                method: "POST", body: JSON.stringify({ password }),
            });
            passwordResetDialog.close();
            await loadUsers();
            showStatus("Password reset successfully.");
        } catch (error) {
            showStatus(error.message, true);
        }
    });

    document.getElementById("refreshButton").addEventListener("click", () => {
        loadUsers().then(() => showStatus("User list refreshed.")).catch((error) => showStatus(error.message, true));
    });
    document.getElementById("search").addEventListener("input", () => {
        loadUsers().catch((error) => showStatus(error.message, true));
    });
    document.getElementById("activeFilter").addEventListener("change", () => {
        loadUsers().catch((error) => showStatus(error.message, true));
    });

    document.getElementById("companyId").addEventListener("change", (event) => {
        const departments = catalogs.departments.filter((item) => item.company_id === event.target.value);
        setOptions("departmentId", departments, (item) => `${item.name} · ${item.id}`, "Choose a department");
        setOptions("positionId", [], (item) => item.name, "Select a department first");
    });
    document.getElementById("departmentId").addEventListener("change", (event) => {
        const positions = catalogs.positions.filter((item) => item.department_id === event.target.value);
        setOptions("positionId", positions, (item) => `${item.name} · ${item.grade || "—"} · ${item.id}`, "Choose a position");
    });

    Promise.all([loadCatalogs(), loadUsers()])
        .then(() => showStatus("Users and administration catalogs loaded."))
        .catch((error) => showStatus(error.message, true));
})();
