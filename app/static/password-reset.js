document.getElementById("passwordResetForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    const message = document.getElementById("authMessage");
    button.disabled = true;
    message.textContent = "";
    message.classList.remove("error", "success");
    try {
        const response = await fetch("/auth/password-reset", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            cache: "no-store",
            body: JSON.stringify({
                current_password: document.getElementById("currentPassword").value,
                new_password: document.getElementById("newPassword").value,
            }),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.detail || "Password update failed.");
        message.classList.add("success");
        message.textContent = result.message || "Password updated. Sign in again to continue.";
        window.setTimeout(() => { window.location = "/login"; }, 800);
    } catch (error) {
        message.classList.add("error");
        message.textContent = error.message || "Unable to update the password.";
    } finally {
        button.disabled = false;
    }
});