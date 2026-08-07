import pytest

from overtone.domain.exceptions import ManifestError
from overtone.infrastructure.manifest.csv_manifest_parser import CsvManifestParser


@pytest.fixture
def parser() -> CsvManifestParser:
    return CsvManifestParser()


def test_parses_rows_in_file_order(parser: CsvManifestParser):
    content = b"name,result_json\nb.ogg,\na.ogg,\n"

    rows = parser.parse(content)

    assert [row.name for row in rows] == ["b.ogg", "a.ogg"]


def test_parses_result_json_into_expected_result(parser: CsvManifestParser):
    content = b'name,result_json\na.ogg,"{""emotional_tone"":""upset""}"\n'

    rows = parser.parse(content)

    assert rows[0].expected_result == {"emotional_tone": "upset"}
    assert rows[0].label_error is None


def test_absent_result_json_column_yields_no_expected_result(parser: CsvManifestParser):
    rows = parser.parse(b"name\na.ogg\n")

    assert rows[0].expected_result is None


def test_empty_result_json_yields_no_expected_result(parser: CsvManifestParser):
    rows = parser.parse(b"name,result_json\na.ogg,\n")

    assert rows[0].expected_result is None


def test_malformed_result_json_keeps_the_row_and_records_the_error(parser: CsvManifestParser):
    content = b'name,result_json\na.ogg,"{not json"\nb.ogg,"{""emotional_tone"":""upset""}"\n'

    rows = parser.parse(content)

    assert [row.name for row in rows] == ["a.ogg", "b.ogg"]
    assert rows[0].expected_result is None
    assert rows[0].label_error is not None
    assert rows[1].expected_result == {"emotional_tone": "upset"}


def test_non_object_result_json_is_recorded_as_an_error(parser: CsvManifestParser):
    rows = parser.parse(b'name,result_json\na.ogg,"[1, 2]"\n')

    assert rows[0].expected_result is None
    assert rows[0].label_error is not None


def test_tolerates_utf8_bom_written_by_spreadsheet_tools(parser: CsvManifestParser):
    rows = parser.parse(b"\xef\xbb\xbfname,result_json\na.ogg,\n")

    assert [row.name for row in rows] == ["a.ogg"]


def test_trims_surrounding_whitespace_from_names(parser: CsvManifestParser):
    rows = parser.parse(b"name,result_json\n  a.ogg  ,\n")

    assert rows[0].name == "a.ogg"


def test_skips_rows_with_a_blank_name(parser: CsvManifestParser):
    rows = parser.parse(b"name,result_json\na.ogg,\n,\n")

    assert [row.name for row in rows] == ["a.ogg"]


def test_rejects_a_manifest_without_a_name_column(parser: CsvManifestParser):
    with pytest.raises(ManifestError):
        parser.parse(b"filename,result_json\na.ogg,\n")


def test_rejects_an_empty_manifest(parser: CsvManifestParser):
    with pytest.raises(ManifestError):
        parser.parse(b"")


def test_rejects_a_manifest_with_a_header_but_no_rows(parser: CsvManifestParser):
    with pytest.raises(ManifestError):
        parser.parse(b"name,result_json\n")
