const exportButton = document.getElementById("exportButton");

if (exportButton) {
    exportButton.addEventListener("click", () => {
        const rows = [
            ["Metric", "Sample value", "Reporting period"],
            ["Total users", "248", "October 2026"],
            ["Active projects", "18", "October 2026"],
            ["Pending approvals", "6", "October 2026"],
            ["Open high risks", "3", "October 2026"],
            ["Workforce utilization", "78%", "October 2026"],
        ];
        const csv = rows
            .map((row) => row.map((value) => `"${value.replaceAll('"', '""')}"`).join(","))
            .join("\r\n");
        const file = new Blob([csv], { type: "text/csv;charset=utf-8" });
        const url = URL.createObjectURL(file);
        const link = document.createElement("a");
        link.href = url;
        link.download = "ai-workforce-command-center-sample.csv";
        link.click();
        URL.revokeObjectURL(url);
    });
}

const navItems = [...document.querySelectorAll(".nav-item")];
const sections = navItems
    .map((item) => document.querySelector(item.getAttribute("href")))
    .filter(Boolean);

if ("IntersectionObserver" in window && sections.length) {
    const observer = new IntersectionObserver((entries) => {
        const visibleSection = entries
            .filter((entry) => entry.isIntersecting)
            .sort((first, second) => second.intersectionRatio - first.intersectionRatio)[0];
        if (!visibleSection) return;
        navItems.forEach((item) => {
            const isActive = item.getAttribute("href") === `#${visibleSection.target.id}`;
            item.classList.toggle("is-active", isActive);
            if (isActive) item.setAttribute("aria-current", "location");
            else item.removeAttribute("aria-current");
        });
    }, { rootMargin: "-15% 0px -70% 0px", threshold: [0, 0.15, 0.4] });

    sections.forEach((section) => observer.observe(section));
}
