(() => {
  const form = document.querySelector("[data-autosave]");
  const status = document.querySelector("#autosave-status");

  if (form && status) {
    let timer;
    let controller;

    function setStatus(text, state = "") {
      status.textContent = text;
      status.dataset.state = state;
    }

    async function save() {
      controller?.abort();
      controller = new AbortController();
      setStatus("Saving…", "saving");
      try {
        const response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          credentials: "same-origin",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        setStatus("Saved", "saved");
      } catch (error) {
        if (error.name === "AbortError") return;
        setStatus("Save failed", "error");
      }
    }

    form.addEventListener("input", () => {
      clearTimeout(timer);
      setStatus("Unsaved", "pending");
      timer = setTimeout(save, 450);
    });
    form.addEventListener("change", () => {
      clearTimeout(timer);
      timer = setTimeout(save, 150);
    });
  }

  const about = document.querySelector("[data-installed-version]");
  const latest = document.querySelector("#latest-release");
  const notes = document.querySelector("#release-notes");
  if (!about || !latest) return;

  const installed = about.dataset.installedVersion || "0.0.0";

  function versionParts(value) {
    return String(value).replace(/^v/i, "").split(".").map((part) => Number.parseInt(part, 10) || 0);
  }

  function compareVersions(left, right) {
    const a = versionParts(left);
    const b = versionParts(right);
    for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
      const diff = (a[i] || 0) - (b[i] || 0);
      if (diff !== 0) return diff;
    }
    return 0;
  }

  fetch("https://api.github.com/repos/Juloc/docker-scheduler-ui/releases/latest", {
    headers: { Accept: "application/vnd.github+json" },
  })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((release) => {
      const tag = release.tag_name || "Unknown";
      const newer = compareVersions(tag, installed) > 0;
      latest.textContent = newer ? `${tag} · update available` : `${tag} · up to date`;
      if (notes && release.body) {
        notes.hidden = false;
        notes.textContent = release.body.length > 1200 ? `${release.body.slice(0, 1200)}…` : release.body;
      }
    })
    .catch(() => {
      latest.textContent = "Unavailable";
    });
})();
