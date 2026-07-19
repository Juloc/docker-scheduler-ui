(() => {
  const tbody = document.querySelector("#group-container-rows");
  if (!tbody) return;

  let dragged = null;

  function selectedRows() {
    return [...tbody.querySelectorAll("[data-group-row]")].filter((row) => row.querySelector('input[name="containers"]')?.checked);
  }

  function renumber() {
    selectedRows().forEach((row, index) => {
      const input = row.querySelector(".group-order-input");
      if (input) input.value = String(index + 1);
    });
  }

  tbody.addEventListener("dragstart", (event) => {
    const row = event.target.closest("[data-group-row]");
    if (!row || !row.querySelector('input[name="containers"]')?.checked) return;
    dragged = row;
    row.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
  });

  tbody.addEventListener("dragover", (event) => {
    if (!dragged) return;
    const target = event.target.closest("[data-group-row]");
    if (!target || target === dragged) return;
    event.preventDefault();
    const rect = target.getBoundingClientRect();
    const before = event.clientY < rect.top + rect.height / 2;
    tbody.insertBefore(dragged, before ? target : target.nextSibling);
  });

  tbody.addEventListener("dragend", () => {
    dragged?.classList.remove("dragging");
    dragged = null;
    renumber();
  });

  tbody.addEventListener("change", (event) => {
    if (event.target.matches('input[name="containers"]')) renumber();
  });
})();
