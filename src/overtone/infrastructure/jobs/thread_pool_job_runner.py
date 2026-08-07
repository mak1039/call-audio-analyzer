import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from overtone.application.ports.job_runner import JobRunner

logger = logging.getLogger(__name__)


class ThreadPoolJobRunner(JobRunner):
    """Bounded in-process executor owned by the composition root.

    Batch state lives in Postgres, so a job running in one process is visible to status
    polls served by any other.
    """

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, work: Callable[[], None]) -> None:
        self._executor.submit(self._guarded(work))

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)

    def _guarded(self, work: Callable[[], None]) -> Callable[[], None]:
        def run() -> None:
            try:
                work()
            except Exception:
                logger.exception("background job failed")

        return run
