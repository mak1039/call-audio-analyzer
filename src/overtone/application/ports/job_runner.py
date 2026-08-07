from abc import ABC, abstractmethod
from collections.abc import Callable


class JobRunner(ABC):
    """Runs work outside the request thread. Keeps threading out of the use cases."""

    @abstractmethod
    def submit(self, work: Callable[[], None]) -> None: ...

    @abstractmethod
    def shutdown(self) -> None:
        """Wait for in-flight work to finish."""
