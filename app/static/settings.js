(() => {
  const form = document.querySelector("[data-autosave]");
  const status = document.querySelector("#autosave-status");
  if (!form || !status) return;

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
})();
