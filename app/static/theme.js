(() => {
  const STORAGE_KEY = "docker-scheduler-ui.theme";
  const root = document.documentElement;
  const media = window.matchMedia("(prefers-color-scheme: dark)");

  function normalize(value) {
    return value === "dark" || value === "light" ? value : "system";
  }

  function apply(value) {
    const theme = normalize(value);
    if (theme === "system") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", theme);
    }

    document.querySelectorAll("[data-theme-choice]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.themeChoice === theme));
    });
  }

  function current() {
    try {
      return normalize(localStorage.getItem(STORAGE_KEY));
    } catch {
      return "system";
    }
  }

  apply(current());

  document.addEventListener("DOMContentLoaded", () => {
    apply(current());
    document.querySelectorAll("[data-theme-choice]").forEach((button) => {
      button.addEventListener("click", () => {
        const next = normalize(button.dataset.themeChoice);
        try {
          localStorage.setItem(STORAGE_KEY, next);
        } catch {
          // Local storage can be unavailable in hardened/private contexts.
        }
        apply(next);
      });
    });
  });

  media.addEventListener?.("change", () => {
    if (current() === "system") {
      apply("system");
    }
  });
})();
