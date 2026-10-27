(() => {
    document.querySelectorAll("[data-mobile-menu]").forEach((button) => {
        const navId = button.getAttribute("aria-controls");
        const navigation = navId ? document.getElementById(navId) : null;
        if (!navigation) return;

        const close = () => {
            button.setAttribute("aria-expanded", "false");
            navigation.classList.remove("is-open");
        };
        const open = () => {
            button.setAttribute("aria-expanded", "true");
            navigation.classList.add("is-open");
        };

        button.addEventListener("click", () => {
            if (button.getAttribute("aria-expanded") === "true") close();
            else open();
        });
        navigation.querySelectorAll("a").forEach((link) => link.addEventListener("click", close));
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && button.getAttribute("aria-expanded") === "true") {
                close();
                button.focus();
            }
        });
        document.addEventListener("pointerdown", (event) => {
            if (button.getAttribute("aria-expanded") === "true" && !button.contains(event.target) && !navigation.contains(event.target)) close();
        });
    });
})();
