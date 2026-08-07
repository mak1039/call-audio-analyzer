import csv
import io
import json
from collections.abc import Sequence

from overtone.application.ports.manifest_parser import ManifestParser, ManifestRow
from overtone.domain.exceptions import ManifestError

NAME_COLUMN = "name"
LABEL_COLUMN = "result_json"


class CsvManifestParser(ManifestParser):
    """Reads the `name` / `result_json` manifest defined by the evaluation spec."""

    def parse(self, content: bytes) -> tuple[ManifestRow, ...]:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        self._require_name_column(reader.fieldnames)
        rows = tuple(self._to_row(raw) for raw in reader if self._name_of(raw))
        if not rows:
            raise ManifestError("manifest contains no usable rows")
        return rows

    def _require_name_column(self, fieldnames: Sequence[str] | None) -> None:
        if not fieldnames:
            raise ManifestError("manifest is empty")
        if NAME_COLUMN not in [name.strip() for name in fieldnames]:
            raise ManifestError(f"manifest is missing a {NAME_COLUMN!r} column")

    def _to_row(self, raw: dict[str, str | None]) -> ManifestRow:
        label = (raw.get(LABEL_COLUMN) or "").strip()
        if not label:
            return ManifestRow(name=self._name_of(raw))
        return self._row_with_label(self._name_of(raw), label)

    def _row_with_label(self, name: str, label: str) -> ManifestRow:
        try:
            parsed = json.loads(label)
        except json.JSONDecodeError as error:
            return ManifestRow(name=name, label_error=f"result_json is not valid JSON: {error}")
        if not isinstance(parsed, dict):
            return ManifestRow(name=name, label_error="result_json is not a JSON object")
        return ManifestRow(name=name, expected_result=parsed)

    def _name_of(self, raw: dict[str, str | None]) -> str:
        return (raw.get(NAME_COLUMN) or "").strip()
