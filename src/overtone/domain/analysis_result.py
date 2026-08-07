from dataclasses import dataclass

from overtone.domain.enums import (
    AudioQuality,
    EmotionalIntensity,
    EmotionalTone,
    NoiseSeverity,
)
from overtone.domain.exceptions import InvalidAnalysisResultError


@dataclass(frozen=True)
class AnalysisResult:
    """One prediction for one audio clip. Cannot be constructed in an invalid state."""

    emotional_tone: EmotionalTone
    emotional_intensity: EmotionalIntensity
    background_noise_present: bool
    background_noise_type: str
    background_noise_severity: NoiseSeverity
    audio_quality: AudioQuality
    speaker_overlap_present: bool
    long_silence_present: bool
    confidence: float

    def __post_init__(self) -> None:
        self._validate_confidence()
        self._validate_noise_consistency()

    def to_dict(self) -> dict[str, object]:
        return {
            "emotional_tone": self.emotional_tone.value,
            "emotional_intensity": self.emotional_intensity.value,
            "background_noise_present": self.background_noise_present,
            "background_noise_type": self.background_noise_type,
            "background_noise_severity": self.background_noise_severity.value,
            "audio_quality": self.audio_quality.value,
            "speaker_overlap_present": self.speaker_overlap_present,
            "long_silence_present": self.long_silence_present,
            "confidence": self.confidence,
        }

    def _validate_confidence(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise InvalidAnalysisResultError(
                f"confidence must be in [0.0, 1.0], got {self.confidence}"
            )

    def _validate_noise_consistency(self) -> None:
        if self.background_noise_present:
            self._require_noise_described()
            return
        self._require_noise_absent()

    def _require_noise_described(self) -> None:
        if not self.background_noise_type:
            raise InvalidAnalysisResultError(
                "background_noise_type is required when noise is present"
            )
        if self.background_noise_severity is NoiseSeverity.NONE:
            raise InvalidAnalysisResultError(
                "background_noise_severity cannot be none when noise present"
            )

    def _require_noise_absent(self) -> None:
        if self.background_noise_type:
            raise InvalidAnalysisResultError(
                "background_noise_type must be empty when no noise present"
            )
        if self.background_noise_severity is not NoiseSeverity.NONE:
            raise InvalidAnalysisResultError(
                "background_noise_severity must be none when no noise present"
            )
