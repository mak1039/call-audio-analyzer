import zipfile
from pathlib import Path

import pytest

from overtone.domain.exceptions import CorruptArchiveError
from overtone.infrastructure.archive.zip_archive_extractor import ZipArchiveExtractor


def build_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return path


@pytest.fixture
def extractor() -> ZipArchiveExtractor:
    return ZipArchiveExtractor()


@pytest.fixture
def destination(tmp_path: Path) -> Path:
    target = tmp_path / "workspace"
    target.mkdir()
    return target


def test_extracts_entries_and_returns_their_paths(
    extractor: ZipArchiveExtractor, tmp_path: Path, destination: Path
):
    archive = build_zip(tmp_path / "b.zip", {"a.ogg": b"aaa", "labels.csv": b"name\n"})

    extracted = extractor.extract(archive, destination)

    assert sorted(path.name for path in extracted) == ["a.ogg", "labels.csv"]
    assert (destination / "a.ogg").read_bytes() == b"aaa"


def test_flattens_a_wrapper_directory_to_the_destination_root(
    extractor: ZipArchiveExtractor, tmp_path: Path, destination: Path
):
    archive = build_zip(tmp_path / "b.zip", {"evaluation_batch/a.ogg": b"aaa"})

    extracted = extractor.extract(archive, destination)

    assert [path.name for path in extracted] == ["a.ogg"]
    assert (destination / "a.ogg").exists()


def test_ignores_macos_resource_fork_entries(
    extractor: ZipArchiveExtractor, tmp_path: Path, destination: Path
):
    archive = build_zip(tmp_path / "b.zip", {"a.ogg": b"aaa", "__MACOSX/._a.ogg": b"junk"})

    extracted = extractor.extract(archive, destination)

    assert [path.name for path in extracted] == ["a.ogg"]


def test_rejects_entries_escaping_the_destination(
    extractor: ZipArchiveExtractor, tmp_path: Path, destination: Path
):
    archive = build_zip(tmp_path / "b.zip", {"../escaped.ogg": b"aaa"})

    with pytest.raises(CorruptArchiveError):
        extractor.extract(archive, destination)

    assert not (destination.parent / "escaped.ogg").exists()


def test_rejects_absolute_entry_paths(
    extractor: ZipArchiveExtractor, tmp_path: Path, destination: Path
):
    archive = build_zip(tmp_path / "b.zip", {"/etc/passwd": b"aaa"})

    with pytest.raises(CorruptArchiveError):
        extractor.extract(archive, destination)


def test_rejects_duplicate_names_after_flattening(
    extractor: ZipArchiveExtractor, tmp_path: Path, destination: Path
):
    archive = build_zip(tmp_path / "b.zip", {"one/a.ogg": b"aaa", "two/a.ogg": b"bbb"})

    with pytest.raises(CorruptArchiveError):
        extractor.extract(archive, destination)


def test_rejects_an_archive_exceeding_the_entry_cap(tmp_path: Path, destination: Path):
    archive = build_zip(tmp_path / "b.zip", {"a.ogg": b"a", "b.ogg": b"b", "c.ogg": b"c"})

    with pytest.raises(CorruptArchiveError):
        ZipArchiveExtractor(max_entries=2).extract(archive, destination)


def test_rejects_an_archive_exceeding_the_uncompressed_size_cap(tmp_path: Path, destination: Path):
    archive = build_zip(tmp_path / "b.zip", {"a.ogg": b"x" * 500})

    with pytest.raises(CorruptArchiveError):
        ZipArchiveExtractor(max_uncompressed_bytes=100).extract(archive, destination)


def test_rejects_a_file_that_is_not_a_zip(
    extractor: ZipArchiveExtractor, tmp_path: Path, destination: Path
):
    not_a_zip = tmp_path / "b.zip"
    not_a_zip.write_bytes(b"definitely not a zip archive")

    with pytest.raises(CorruptArchiveError):
        extractor.extract(not_a_zip, destination)


def test_rejects_a_missing_archive(
    extractor: ZipArchiveExtractor, tmp_path: Path, destination: Path
):
    with pytest.raises(CorruptArchiveError):
        extractor.extract(tmp_path / "absent.zip", destination)
