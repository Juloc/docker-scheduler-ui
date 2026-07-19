(() => {
  const STORAGE_KEY = "docker-scheduler-ui.infrastructure-projects";
  const searchInput = document.getElementById("container-search");
  const filterButtons = Array.from(document.querySelectorAll("[data-status-filter]"));
  const projectFilter = document.getElementById("compose-project-filter");
  const groupToggle = document.getElementById("group-by-project");
  const hideInfrastructure = document.getElementById("hide-infrastructure");
  const projectChecks = Array.from(document.querySelectorAll("#infrastructure-projects input[type='checkbox']"));
  const body = document.getElementById("containers-body");
  const visibleCount = document.getElementById("visible-container-count");
  const rows = Array.from(document.querySelectorAll("[data-container-row]"));
  let activeFilter = "all";

  function loadInfrastructureProjects() {
    try {
      const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      return new Set(Array.isArray(value) ? value : []);
    } catch {
      return new Set();
    }
  }

  let infrastructureProjects = loadInfrastructureProjects();
  projectChecks.forEach((checkbox) => {
    checkbox.checked = infrastructureProjects.has(checkbox.value);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) infrastructureProjects.add(checkbox.value);
      else infrastructureProjects.delete(checkbox.value);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(infrastructureProjects).sort()));
      applyFilters();
    });
  });

  function rowMatchesStatus(row) {
    const status = row.dataset.status || "";
    const health = row.dataset.health || "";
    if (activeFilter === "all") return true;
    if (activeFilter === "stopped") return ["exited", "created", "dead"].includes(status);
    if (activeFilter === "unhealthy") return health === "unhealthy";
    return status === activeFilter;
  }

  function clearGroupHeaders() {
    body?.querySelectorAll(".compose-group-row").forEach((item) => item.remove());
  }

  function addGroupHeaders() {
    if (!body || !groupToggle?.checked) return;
    const visibleRows = rows.filter((row) => !row.hidden);
    let lastProject = null;
    visibleRows
      .sort((a, b) => (a.dataset.project || "").localeCompare(b.dataset.project || "") || (a.dataset.search || "").localeCompare(b.dataset.search || ""))
      .forEach((row) => {
        const detail = document.querySelector(`[data-detail-for="${row.dataset.containerRow}"]`);
        const project = row.dataset.project || "__standalone__";
        if (project !== lastProject) {
          const header = document.createElement("tr");
          header.className = "compose-group-row";
          header.innerHTML = `<td colspan="6"><strong>${project === "__standalone__" ? "Standalone" : project}</strong></td>`;
          body.appendChild(header);
          lastProject = project;
        }
        body.appendChild(row);
        if (detail) body.appendChild(detail);
      });
  }

  function applyFilters() {
    const query = (searchInput?.value || "").trim().toLowerCase();
    const project = projectFilter?.value || "";
    let shown = 0;
    clearGroupHeaders();

    rows.forEach((row) => {
      const detailRow = document.querySelector(`[data-detail-for="${row.dataset.containerRow}"]`);
      const rowProject = row.dataset.project || "__standalone__";
      const matchesSearch = !query || (row.dataset.search || "").toLowerCase().includes(query);
      const matchesProject = !project || project === rowProject;
      const infrastructureHidden = Boolean(hideInfrastructure?.checked && infrastructureProjects.has(rowProject));
      const visible = matchesSearch && matchesProject && rowMatchesStatus(row) && !infrastructureHidden;
      row.hidden = !visible;
      if (detailRow) detailRow.hidden = !visible;
      if (visible) shown += 1;
    });

    if (visibleCount) visibleCount.textContent = String(shown);
    addGroupHeaders();
  }

  searchInput?.addEventListener("input", applyFilters);
  projectFilter?.addEventListener("change", applyFilters);
  groupToggle?.addEventListener("change", applyFilters);
  hideInfrastructure?.addEventListener("change", applyFilters);

  filterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.statusFilter || "all";
      filterButtons.forEach((item) => item.classList.toggle("active", item === button));
      applyFilters();
    });
  });

  async function loadLogPreview(containerId, force) {
    const output = document.querySelector(`[data-log-output="${containerId}"]`);
    if (!output || (!force && output.dataset.loaded === "true")) return;
    output.textContent = "Loading log preview...";
    try {
      const response = await fetch(`/containers/${containerId}/logs/preview`, { headers: { Accept: "text/plain" } });
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
      if (details.open && details.dataset.containerId) loadLogPreview(details.dataset.containerId, false);
    });
  });
  document.querySelectorAll(".refresh-log-preview").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.containerId) loadLogPreview(button.dataset.containerId, true);
    });
  });

  applyFilters();
})();
