import csv
import io

from overtone.application.ports.result_serializer import ResultSerializer
from overtone.domain.analysis_result import AnalysisResult
from overtone.domain.batch import Batch, BatchItem

SCHEMA_COLUMNS = [
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
CSV_COLUMNS = ["name", "status", "error", *SCHEMA_COLUMNS]


class CsvResultSerializer(ResultSerializer):
    """Flat one-row-per-file rendering, for spreadsheets and quick review."""

    @property
    def file_extension(self) -> str:
        return "csv"

    def serialize(self, batch: Batch) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(self._row(item) for item in batch.items)
        return buffer.getvalue()

    def _row(self, item: BatchItem) -> dict[str, str]:
        row = {
            "name": item.filename,
            "status": item.status.value,
            "error": item.error_message or "",
        }
        return row | self._prediction_cells(item.result)

    def _prediction_cells(self, result: AnalysisResult | None) -> dict[str, str]:
        if result is None:
            return dict.fromkeys(SCHEMA_COLUMNS, "")
        return {column: self._cell(value) for column, value in result.to_dict().items()}

    def _cell(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
