(function () {
  const searchInput = document.getElementById("container-search");
  const filterButtons = Array.from(document.querySelectorAll("[data-status-filter]"));
  const rows = Array.from(document.querySelectorAll("[data-container-row]"));
  const visibleCount = document.getElementById("visible-container-count");
  let activeFilter = "all";

  function rowMatchesStatus(row) {
    const status = row.dataset.status || "";
    const health = row.dataset.health || "";

    if (activeFilter === "all") {
      return true;
    }
    if (activeFilter === "stopped") {
      return ["exited", "created", "dead"].includes(status);
    }
    if (activeFilter === "unhealthy") {
      return health === "unhealthy";
    }
    return status === activeFilter;
  }

  function applyFilters() {
    const query = (searchInput && searchInput.value ? searchInput.value : "").trim().toLowerCase();
    let shown = 0;

    rows.forEach((row) => {
      const detailRow = document.querySelector(`[data-detail-for="${row.dataset.containerRow}"]`);
      const matchesSearch = !query || (row.dataset.search || "").toLowerCase().includes(query);
      const visible = matchesSearch && rowMatchesStatus(row);

      row.hidden = !visible;
      if (detailRow) {
        detailRow.hidden = !visible;
      }
      if (visible) {
        shown += 1;
      }
    });

    if (visibleCount) {
      visibleCount.textContent = String(shown);
    }
  }

  if (searchInput) {
    searchInput.addEventListener("input", applyFilters);
  }

  filterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.statusFilter || "all";
      filterButtons.forEach((item) => item.classList.toggle("active", item === button));
      applyFilters();
    });
  });

  async function loadLogPreview(containerId, force) {
    const output = document.querySelector(`[data-log-output="${containerId}"]`);
    if (!output) {
      return;
    }
    if (!force && output.dataset.loaded === "true") {
      return;
    }

    output.textContent = "Loading log preview...";
    output.dataset.loaded = "false";

    try {
      const response = await fetch(`/containers/${containerId}/logs/preview`, {
        headers: { Accept: "text/plain" },
      });
      const text = await response.text();
      output.textContent = text || "No logs available.";
      output.dataset.loaded = response.ok ? "true" : "false";
      output.classList.toggle("has-error", !response.ok);
    } catch (error) {
      output.textContent = `Failed to load log preview: ${error}`;
      output.dataset.loaded = "false";
      output.classList.add("has-error");
    }
  }

  document.querySelectorAll(".container-details").forEach((details) => {
    details.addEventListener("toggle", () => {
      if (details.open && details.dataset.containerId) {
        loadLogPreview(details.dataset.containerId, false);
      }
    });
  });

  document.querySelectorAll(".refresh-log-preview").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.containerId) {
        loadLogPreview(button.dataset.containerId, true);
      }
    });
  });
})();
