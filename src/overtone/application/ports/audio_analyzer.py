from abc import ABC, abstractmethod

from overtone.domain.analysis_result import AnalysisResult
from overtone.domain.audio_clip import AudioClip


class AudioAnalyzer(ABC):
    """The seam the whole system hangs off.

    Everything downstream — batching, the dashboard, exports — depends only on this
    interface, so the stub, the local acoustic pipeline, and the multimodal model are
    interchangeable without touching anything else.
    """

    @abstractmethod
    def analyze(self, clip: AudioClip) -> AnalysisResult:
        """Return a prediction for one clip, or raise if the clip cannot be analysed."""
