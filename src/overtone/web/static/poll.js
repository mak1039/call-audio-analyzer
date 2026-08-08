(function () {
  const progress = document.getElementById("progress");
  if (!progress) return;

  const url = progress.dataset.statusUrl;
  const INTERVAL_MS = 1000;
  const MAX_ATTEMPTS = 300; // five minutes, then stop holding the instance awake

  let attempts = 0;

  function stop(message) {
    progress.textContent = message;
  }

  function render(status) {
    progress.textContent =
      `${status.succeeded + status.failed} of ${status.total} processed` +
      ` — ${status.status}`;
  }

  async function tick() {
    attempts += 1;
    try {
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (response.redirected) {
        stop("Your session has expired. Reload the page to sign in again.");
        return;
      }
      if (!response.ok) {
        stop(`Could not read progress (HTTP ${response.status}). Reload the page to retry.`);
        return;
      }
      const status = await response.json();
      render(status);
      if (status.finished) {
        window.location.reload();
        return;
      }
    } catch (error) {
      // transient network failure; try again on the next tick
    }
    if (attempts >= MAX_ATTEMPTS) {
      stop("Stopped checking for updates. Reload the page to see the latest progress.");
      return;
    }
    window.setTimeout(tick, INTERVAL_MS);
  }

  window.setTimeout(tick, INTERVAL_MS);
})();
