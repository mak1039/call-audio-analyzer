import json

import pytest

from overtone.domain.analysis_result import AnalysisResult
from overtone.domain.enums import (
    AudioQuality,
    EmotionalIntensity,
    EmotionalTone,
    NoiseSeverity,
)
from overtone.domain.exceptions import InvalidAnalysisResultError

SPEC_FIELD_ORDER = [
    "emotional_tone",
    "emotional_intensity",
    "background_noise_present",
    "background_noise_type",
    "background_noise_severity",
    "audio_quality",
    "speaker_overlap_present",
    "long_silence_present",
    "confidence",
]


def noisy_result(**overrides: object) -> AnalysisResult:
    defaults = {
        "emotional_tone": EmotionalTone.FRUSTRATED,
        "emotional_intensity": EmotionalIntensity.MEDIUM,
        "background_noise_present": True,
        "background_noise_type": "office chatter",
        "background_noise_severity": NoiseSeverity.LOW,
        "audio_quality": AudioQuality.CLEAR,
        "speaker_overlap_present": False,
        "long_silence_present": False,
        "confidence": 0.82,
    }
    return AnalysisResult(**{**defaults, **overrides})  # type: ignore[arg-type]


def quiet_result(**overrides: object) -> AnalysisResult:
    quiet = {
        "background_noise_present": False,
        "background_noise_type": "",
        "background_noise_severity": NoiseSeverity.NONE,
    }
    return noisy_result(**{**quiet, **overrides})


def test_to_dict_emits_spec_field_order():
    assert list(noisy_result().to_dict()) == SPEC_FIELD_ORDER


def test_to_dict_emits_primitive_json_serializable_values():
    payload = noisy_result().to_dict()

    assert json.loads(json.dumps(payload)) == {
        "emotional_tone": "frustrated",
        "emotional_intensity": "medium",
        "background_noise_present": True,
        "background_noise_type": "office chatter",
        "background_noise_severity": "low",
        "audio_quality": "clear",
        "speaker_overlap_present": False,
        "long_silence_present": False,
        "confidence": 0.82,
    }


def test_is_frozen():
    with pytest.raises(Exception):  # noqa: B017
        noisy_result().emotional_tone = EmotionalTone.NEUTRAL  # type: ignore[misc]


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_rejects_confidence_outside_unit_interval(confidence: float):
    with pytest.raises(InvalidAnalysisResultError):
        noisy_result(confidence=confidence)


@pytest.mark.parametrize("confidence", [0.0, 1.0])
def test_accepts_confidence_at_unit_interval_bounds(confidence: float):
    assert noisy_result(confidence=confidence).confidence == confidence


def test_rejects_noise_type_when_no_noise_present():
    with pytest.raises(InvalidAnalysisResultError):
        quiet_result(background_noise_type="office chatter")


def test_rejects_noise_severity_when_no_noise_present():
    with pytest.raises(InvalidAnalysisResultError):
        quiet_result(background_noise_severity=NoiseSeverity.LOW)


def test_rejects_empty_noise_type_when_noise_present():
    with pytest.raises(InvalidAnalysisResultError):
        noisy_result(background_noise_type="")


def test_rejects_severity_none_when_noise_present():
    with pytest.raises(InvalidAnalysisResultError):
        noisy_result(background_noise_severity=NoiseSeverity.NONE)


def test_accepts_consistent_quiet_result():
    result = quiet_result()

    assert result.background_noise_present is False
    assert result.background_noise_type == ""
    assert result.background_noise_severity is NoiseSeverity.NONE


def test_from_dict_round_trips_a_result():
    original = noisy_result()

    assert AnalysisResult.from_dict(original.to_dict()) == original


def test_from_dict_rejects_a_payload_that_breaks_the_contract():
    payload = noisy_result().to_dict()
    payload["confidence"] = 5.0

    with pytest.raises(InvalidAnalysisResultError):
        AnalysisResult.from_dict(payload)
