(function () {
  const progress = document.getElementById("progress");
  if (!progress) return;
  const url = progress.dataset.statusUrl;

  async function tick() {
    try {
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) return;
      const status = await response.json();
      progress.textContent =
        `${status.succeeded + status.failed} of ${status.total} processed` +
        ` — ${status.status}`;
      if (status.finished) {
        window.location.reload();
        return;
      }
    } catch (error) {
      // transient network failure; try again on the next tick
    }
    window.setTimeout(tick, 1000);
  }

  window.setTimeout(tick, 1000);
})();
