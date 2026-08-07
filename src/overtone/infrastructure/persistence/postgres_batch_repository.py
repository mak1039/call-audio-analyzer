from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from overtone.application.ports.batch_repository import BatchRepository
from overtone.domain.analysis_result import AnalysisResult
from overtone.domain.batch import Batch, BatchId, BatchItem
from overtone.domain.enums import BatchStatus, ItemStatus
from overtone.domain.exceptions import BatchNotFoundError

SCHEMA = Path(__file__).with_name("schema.sql")
COLUMNS = "batch_id, status, created_at, unmatched_files, items"

UPSERT = f"""
    INSERT INTO batches ({COLUMNS}) VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (batch_id) DO UPDATE SET
        status = EXCLUDED.status,
        unmatched_files = EXCLUDED.unmatched_files,
        items = EXCLUDED.items
"""


class PostgresBatchRepository(BatchRepository):
    """Batch state in Postgres. One row per batch; items ride along as JSONB."""

    def __init__(self, database_url: str, min_size: int = 1, max_size: int = 5) -> None:
        self._pool = ConnectionPool(database_url, min_size=min_size, max_size=max_size, open=False)
        self._pool.open()

    def close(self) -> None:
        self._pool.close()

    def create_schema(self) -> None:
        with self._pool.connection() as connection:
            connection.execute(SCHEMA.read_text(encoding="utf-8"))

    def delete_all(self) -> None:
        """Test-only helper. Not wired into any composition root or route."""
        with self._pool.connection() as connection:
            connection.execute("DELETE FROM batches")

    def save(self, batch: Batch) -> None:
        with self._pool.connection() as connection:
            connection.execute(UPSERT, self._to_row(batch))

    def get(self, batch_id: BatchId) -> Batch:
        with self._pool.connection() as connection:
            row = connection.execute(
                f"SELECT {COLUMNS} FROM batches WHERE batch_id = %s", (batch_id,)
            ).fetchone()
        if row is None:
            raise BatchNotFoundError(f"no batch with id {batch_id}")
        return self._to_batch(row)

    def list_recent(self, limit: int) -> tuple[Batch, ...]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                f"SELECT {COLUMNS} FROM batches ORDER BY created_at DESC LIMIT %s", (limit,)
            ).fetchall()
        return tuple(self._to_batch(row) for row in rows)

    def _to_row(self, batch: Batch) -> tuple[Any, ...]:
        items = [self._item_payload(item) for item in batch.items]
        return (
            str(batch.batch_id),
            batch.status.value,
            batch.created_at,
            Jsonb(list(batch.unmatched_files)),
            Jsonb(items),
        )

    def _item_payload(self, item: BatchItem) -> dict[str, Any]:
        return {
            "filename": item.filename,
            "status": item.status.value,
            "result": item.result.to_dict() if item.result else None,
            "error_message": item.error_message,
        }

    def _to_batch(self, row: tuple[Any, ...]) -> Batch:
        batch_id, status, created_at, unmatched_files, items = row
        return Batch(
            batch_id=BatchId(batch_id),
            items=tuple(self._to_item(payload) for payload in items),
            status=BatchStatus(status),
            created_at=created_at,
            unmatched_files=tuple(unmatched_files),
        )

    def _to_item(self, payload: dict[str, Any]) -> BatchItem:
        result = payload["result"]
        return BatchItem(
            filename=payload["filename"],
            status=ItemStatus(payload["status"]),
            result=AnalysisResult.from_dict(result) if result else None,
            error_message=payload["error_message"],
        )
