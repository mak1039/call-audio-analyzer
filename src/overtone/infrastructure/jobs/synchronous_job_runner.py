from collections.abc import Callable

from overtone.application.ports.job_runner import JobRunner


class SynchronousJobRunner(JobRunner):
    """Runs work inline. Used by tests so batch processing is deterministic."""

    def submit(self, work: Callable[[], None]) -> None:
        work()

    def shutdown(self) -> None:
        return None
