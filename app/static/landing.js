(() => {
    const menuButton = document.getElementById("menuToggle");
    const navigation = document.getElementById("siteNav");
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (menuButton && navigation) {
        menuButton.addEventListener("click", () => {
            const isOpen = navigation.classList.toggle("open");
            menuButton.setAttribute("aria-expanded", String(isOpen));
            menuButton.setAttribute("aria-label", isOpen ? "Close navigation" : "Open navigation");
        });
        navigation.querySelectorAll("a").forEach((link) => {
            link.addEventListener("click", () => {
                navigation.classList.remove("open");
                menuButton.setAttribute("aria-expanded", "false");
                menuButton.setAttribute("aria-label", "Open navigation");
            });
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && menuButton.getAttribute("aria-expanded") === "true") {
                navigation.classList.remove("open");
                menuButton.setAttribute("aria-expanded", "false");
                menuButton.setAttribute("aria-label", "Open navigation");
                menuButton.focus();
            }
        });
        document.addEventListener("pointerdown", (event) => {
            if (menuButton.getAttribute("aria-expanded") === "true" && !menuButton.contains(event.target) && !navigation.contains(event.target)) {
                navigation.classList.remove("open");
                menuButton.setAttribute("aria-expanded", "false");
                menuButton.setAttribute("aria-label", "Open navigation");
            }
        });
    }

    if (!prefersReducedMotion && "IntersectionObserver" in window) {
        document.documentElement.classList.add("has-motion");
        const observer = new IntersectionObserver((entries, currentObserver) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                entry.target.classList.add("is-visible");
                currentObserver.unobserve(entry.target);
            });
        }, { threshold: 0.12, rootMargin: "0px 0px -30px 0px" });
        document.querySelectorAll(".os-reveal").forEach((element) => observer.observe(element));
    } else {
        document.querySelectorAll(".os-reveal").forEach((element) => element.classList.add("is-visible"));
    }
})();