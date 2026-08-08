import csv
import io
import json
from datetime import UTC, datetime

import pytest

from overtone.domain.analysis_result import AnalysisResult
from overtone.domain.batch import Batch, BatchItem, new_batch_id
from overtone.domain.enums import (
    AudioQuality,
    EmotionalIntensity,
    EmotionalTone,
    NoiseSeverity,
)
from overtone.infrastructure.export.csv_result_serializer import (
    CSV_COLUMNS,
    CsvResultSerializer,
)
from overtone.infrastructure.export.json_result_serializer import JsonResultSerializer

RESULT = AnalysisResult(
    emotional_tone=EmotionalTone.UPSET,
    emotional_intensity=EmotionalIntensity.HIGH,
    background_noise_present=True,
    background_noise_type="TV",
    background_noise_severity=NoiseSeverity.MEDIUM,
    audio_quality=AudioQuality.CLEAR,
    speaker_overlap_present=True,
    long_silence_present=False,
    confidence=0.82,
)

CREATED_AT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


@pytest.fixture
def batch() -> Batch:
    items = (
        BatchItem.pending("call_001.ogg").succeeded(RESULT),
        BatchItem.pending("call_002.ogg").failed("RuntimeError: decoder blew up"),
    )
    return Batch.create(
        new_batch_id(), items, CREATED_AT, unmatched_files=("stray.ogg",)
    ).completed()


def csv_rows(batch: Batch) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(CsvResultSerializer().serialize(batch))))


def test_csv_header_leads_with_name_then_the_schema_fields():
    assert CSV_COLUMNS[:4] == ["name", "status", "error", "emotional_tone"]
    assert CSV_COLUMNS[-1] == "confidence"


def test_csv_row_carries_the_prediction_for_a_successful_item(batch: Batch):
    row = csv_rows(batch)[0]

    assert row["name"] == "call_001.ogg"
    assert row["status"] == "succeeded"
    assert row["emotional_tone"] == "upset"
    assert row["background_noise_type"] == "TV"
    assert row["speaker_overlap_present"] == "true"
    assert row["confidence"] == "0.82"


def test_csv_row_for_a_failed_item_carries_the_reason_and_blank_predictions(batch: Batch):
    row = csv_rows(batch)[1]

    assert row["name"] == "call_002.ogg"
    assert row["status"] == "failed"
    assert row["error"] == "RuntimeError: decoder blew up"
    assert row["emotional_tone"] == ""
    assert row["confidence"] == ""


def test_csv_preserves_item_order_and_original_filenames(batch: Batch):
    assert [row["name"] for row in csv_rows(batch)] == ["call_001.ogg", "call_002.ogg"]


def test_json_reports_batch_level_status_and_unmatched_files(batch: Batch):
    payload = json.loads(JsonResultSerializer().serialize(batch))

    assert payload["status"] == "completed"
    assert payload["unmatched_files"] == ["stray.ogg"]
    assert payload["batch_id"] == batch.batch_id


def test_json_nests_the_exact_output_schema_under_each_result(batch: Batch):
    payload = json.loads(JsonResultSerializer().serialize(batch))

    assert payload["results"][0] == {
        "name": "call_001.ogg",
        "status": "succeeded",
        "error": None,
        "result": RESULT.to_dict(),
    }


def test_json_includes_failed_items_with_a_null_result(batch: Batch):
    payload = json.loads(JsonResultSerializer().serialize(batch))

    assert payload["results"][1] == {
        "name": "call_002.ogg",
        "status": "failed",
        "error": "RuntimeError: decoder blew up",
        "result": None,
    }


def test_serializers_declare_their_file_extension():
    assert CsvResultSerializer().file_extension == "csv"
    assert JsonResultSerializer().file_extension == "json"
