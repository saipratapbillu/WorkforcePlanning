function renderPasswordToggle(button, showing) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "18");
    svg.setAttribute("height", "18");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.8");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    const paths = showing
        ? ["M3 3l18 18", "M10.6 10.6a2 2 0 0 0 2.8 2.8", "M9.9 5.2A10.7 10.7 0 0 1 12 5c6.4 0 10 7 10 7a14.8 14.8 0 0 1-3.2 4.2", "M6.6 6.6A15.4 15.4 0 0 0 2 12s3.6 7 10 7a10.7 10.7 0 0 0 4.1-.8"]
        : ["M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z", "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"];
    for (const data of paths) {
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", data);
        svg.append(path);
    }
    button.replaceChildren(svg);
    button.setAttribute("aria-label", `${showing ? "Hide" : "Show"} password`);
    button.setAttribute("aria-pressed", String(showing));
    button.title = `${showing ? "Hide" : "Show"} password`;
}

document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    const input = document.getElementById(button.dataset.passwordToggle);
    if (input) renderPasswordToggle(button, input.type !== "password");
});

document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-password-toggle]");
    if (!button) return;
    const input = document.getElementById(button.dataset.passwordToggle);
    if (!input) return;
    const showing = input.type === "password";
    input.type = showing ? "text" : "password";
    renderPasswordToggle(button, showing);
});