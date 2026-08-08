import csv
import io
import json
import zipfile
from pathlib import Path

import pytest

from overtone.cli.main import main

MANIFEST = b"name,result_json\ncall_001.ogg,\ncall_002.ogg,\ncall_missing.ogg,\n"


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    path = tmp_path / "evaluation_batch.zip"
    entries = {
        "evaluation_batch/labels.csv": MANIFEST,
        "evaluation_batch/call_001.ogg": b"OggS fake audio one",
        "evaluation_batch/call_002.ogg": b"OggS fake audio two",
        "evaluation_batch/stray.ogg": b"OggS not in the manifest",
    }
    with zipfile.ZipFile(path, "w") as opened:
        for name, payload in entries.items():
            opened.writestr(name, payload)
    return path


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    return tmp_path / "out"


def run(archive: Path, out_dir: Path, *extra: str) -> int:
    return main(["analyze", str(archive), "--out", str(out_dir), *extra])


def test_exits_zero_and_writes_both_result_files(archive: Path, out_dir: Path):
    assert run(archive, out_dir) == 0

    assert (out_dir / "results.csv").exists()
    assert (out_dir / "results.json").exists()


def test_csv_has_one_row_per_manifest_entry_with_original_filenames(archive: Path, out_dir: Path):
    run(archive, out_dir)

    rows = list(csv.DictReader(io.StringIO((out_dir / "results.csv").read_text())))

    assert [row["name"] for row in rows] == ["call_001.ogg", "call_002.ogg", "call_missing.ogg"]


def test_present_files_are_analysed_and_absent_ones_fail_alone(archive: Path, out_dir: Path):
    run(archive, out_dir)

    payload = json.loads((out_dir / "results.json").read_text())
    by_name = {entry["name"]: entry for entry in payload["results"]}

    assert by_name["call_001.ogg"]["status"] == "succeeded"
    assert by_name["call_001.ogg"]["result"]["emotional_tone"] == "neutral"
    assert by_name["call_missing.ogg"]["status"] == "failed"
    assert by_name["call_missing.ogg"]["result"] is None


def test_every_prediction_carries_the_full_output_schema(archive: Path, out_dir: Path):
    run(archive, out_dir)

    payload = json.loads((out_dir / "results.json").read_text())
    prediction = payload["results"][0]["result"]

    assert set(prediction) == {
        "emotional_tone",
        "emotional_intensity",
        "background_noise_present",
        "background_noise_type",
        "background_noise_severity",
        "audio_quality",
        "speaker_overlap_present",
        "long_silence_present",
        "confidence",
    }


def test_reports_missing_and_unmatched_files_to_the_operator(
    archive: Path, out_dir: Path, capsys: pytest.CaptureFixture[str]
):
    run(archive, out_dir)

    output = capsys.readouterr().out

    assert "call_missing.ogg" in output
    assert "stray.ogg" in output


def test_prints_a_summary_of_the_batch(
    archive: Path, out_dir: Path, capsys: pytest.CaptureFixture[str]
):
    run(archive, out_dir)

    output = capsys.readouterr().out

    assert "3" in output
    assert "succeeded" in output.lower()
    assert "failed" in output.lower()


def test_no_audio_is_left_behind_in_the_output_directory(archive: Path, out_dir: Path):
    run(archive, out_dir)

    assert [path.name for path in out_dir.rglob("*.ogg")] == []


def test_only_csv_is_written_when_csv_format_is_requested(archive: Path, out_dir: Path):
    run(archive, out_dir, "--format", "csv")

    assert (out_dir / "results.csv").exists()
    assert not (out_dir / "results.json").exists()


def test_a_corrupt_archive_fails_cleanly_without_a_traceback(
    tmp_path: Path, out_dir: Path, capsys: pytest.CaptureFixture[str]
):
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"not a zip at all")

    exit_code = main(["analyze", str(broken), "--out", str(out_dir)])

    assert exit_code != 0
    assert "Traceback" not in capsys.readouterr().err


def test_a_batch_without_a_manifest_fails_cleanly(
    tmp_path: Path, out_dir: Path, capsys: pytest.CaptureFixture[str]
):
    path = tmp_path / "no_manifest.zip"
    with zipfile.ZipFile(path, "w") as opened:
        opened.writestr("call_001.ogg", b"OggS")

    exit_code = main(["analyze", str(path), "--out", str(out_dir)])

    assert exit_code != 0
    assert "manifest" in capsys.readouterr().err.lower()
