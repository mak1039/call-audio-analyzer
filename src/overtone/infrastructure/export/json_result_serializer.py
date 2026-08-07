import json

from overtone.application.ports.result_serializer import ResultSerializer
from overtone.domain.batch import Batch, BatchItem


class JsonResultSerializer(ResultSerializer):
    """Structured rendering that keeps each prediction in the exact output schema."""

    @property
    def file_extension(self) -> str:
        return "json"

    def serialize(self, batch: Batch) -> str:
        payload = {
            "batch_id": str(batch.batch_id),
            "status": batch.status.value,
            "unmatched_files": list(batch.unmatched_files),
            "results": [self._entry(item) for item in batch.items],
        }
        return json.dumps(payload, indent=2)

    def _entry(self, item: BatchItem) -> dict[str, object]:
        return {
            "name": item.filename,
            "status": item.status.value,
            "error": item.error_message,
            "result": item.result.to_dict() if item.result else None,
        }
