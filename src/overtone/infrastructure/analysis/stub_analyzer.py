from overtone.application.ports.audio_analyzer import AudioAnalyzer
from overtone.domain.analysis_result import AnalysisResult
from overtone.domain.audio_clip import AudioClip
from overtone.domain.enums import (
    AudioQuality,
    EmotionalIntensity,
    EmotionalTone,
    NoiseSeverity,
)

NEUTRAL_RESULT = AnalysisResult(
    emotional_tone=EmotionalTone.NEUTRAL,
    emotional_intensity=EmotionalIntensity.LOW,
    background_noise_present=False,
    background_noise_type="",
    background_noise_severity=NoiseSeverity.NONE,
    audio_quality=AudioQuality.CLEAR,
    speaker_overlap_present=False,
    long_silence_present=False,
    confidence=0.0,
)


class StubAnalyzer(AudioAnalyzer):
    """Placeholder prediction so the pipeline can be built and deployed before the models exist.

    Confidence is 0.0 because a fixed answer carries no information — anything higher would
    misrepresent the system while the stub is wired in.
    """

    def analyze(self, clip: AudioClip) -> AnalysisResult:  # noqa: ARG002
        return NEUTRAL_RESULT
