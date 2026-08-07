# M2 Hosted Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the M1 batch pipeline into a hosted, password-protected web dashboard on Render that an evaluator can upload a ZIP to, watch process, review, and download results from — without a command line.

**Architecture:** Flask app factory over the existing Clean Architecture. `domain/` and the existing use cases stay intact; M2 adds three ports (`Clock`, `JobRunner`, `list_recent`), a Postgres adapter for batch state, an in-process thread-pool job runner, and a thin `web/` layer of Jinja templates plus one polling endpoint. Predictions remain `StubAnalyzer` — M5 replaces it with a one-line change in the composition root.

**Tech Stack:** Python 3.12, Flask, gunicorn, psycopg 3 (raw SQL, no ORM), Jinja2, vanilla JS, Postgres 16, Docker, Render.

## Global Constraints

- **Do not run `git commit` or `git push`.** Leave all changes in the working tree; the user reviews and commits. Every task ends with a verification step instead of a commit.
- Hard ceiling **20 lines per function**, target 5–10. One level of abstraction per function.
- Maximum three positional parameters; beyond that pass a value object.
- No boolean parameters that switch behaviour.
- Guard clauses over nested conditionals; maximum two levels of indentation.
- Type hints on every public function. `mypy --strict` must stay clean on `domain/` and `application/`.
- Domain objects are `@dataclass(frozen=True)`. Enums for every constrained field, never bare strings.
- Domain exceptions only, from `overtone.domain.exceptions`. Never bare `except:`.
- Routes are ten lines maximum: parse input, call one use case, map the result.
- Line length 100. `ruff check .`, `black --check .`, `mypy`, and `pytest` must all pass at the end of every task.
- All 90 existing tests must keep passing.
- Production call audio is confidential: never commit audio, never log filenames' contents, delete the workspace after processing.
- Run commands with `python -m uv run ...` (uv is installed but not on PATH).

---

### Task 1: Domain additions — `created_at`, `FAILED`, `from_dict`

**Files:**
- Modify: `src/overtone/domain/enums.py`
- Modify: `src/overtone/domain/batch.py`
- Modify: `src/overtone/domain/analysis_result.py`
- Modify: `tests/domain/test_batch.py`, `tests/domain/test_analysis_result.py`
- Modify (call sites): `tests/infrastructure/test_adapters.py`, `tests/application/test_process_batch.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `BatchStatus.FAILED` (value `"failed"`)
  - `Batch.created_at: datetime` and `Batch.create(batch_id: BatchId, items: tuple[BatchItem, ...], created_at: datetime, unmatched_files: tuple[str, ...] = ()) -> Batch`
  - `Batch.failed() -> Batch`
  - `AnalysisResult.from_dict(payload: dict[str, object]) -> AnalysisResult`

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/test_batch.py`:

```python
from datetime import UTC, datetime

from overtone.domain.enums import BatchStatus

CREATED_AT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


def test_batch_records_when_it_was_created():
    batch = Batch.create(new_batch_id(), (BatchItem.pending("a.ogg"),), CREATED_AT)

    assert batch.created_at == CREATED_AT


def test_failed_marks_a_batch_whose_job_died():
    batch = Batch.create(new_batch_id(), (BatchItem.pending("a.ogg"),), CREATED_AT)

    assert batch.started().failed().status is BatchStatus.FAILED
```

Append to `tests/domain/test_analysis_result.py`:

```python
def test_from_dict_round_trips_a_result():
    original = noisy_result()

    assert AnalysisResult.from_dict(original.to_dict()) == original


def test_from_dict_rejects_a_payload_that_breaks_the_contract():
    payload = noisy_result().to_dict()
    payload["confidence"] = 5.0

    with pytest.raises(InvalidAnalysisResultError):
        AnalysisResult.from_dict(payload)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m uv run pytest tests/domain -v`
Expected: FAIL — `Batch.create()` takes 3 positional args but 4 were given; `Batch` has no attribute `created_at`; `BatchStatus` has no attribute `FAILED`; `AnalysisResult` has no attribute `from_dict`.

- [ ] **Step 3: Add the `FAILED` status**

In `src/overtone/domain/enums.py`, add to `BatchStatus`:

```python
    FAILED = "failed"
```

- [ ] **Step 4: Add `created_at` and `failed()` to `Batch`**

In `src/overtone/domain/batch.py`, add `from datetime import datetime` at the top. Add the field to `Batch` after `status`:

```python
    created_at: datetime
```

Replace `Batch.create` with:

```python
    @classmethod
    def create(
        cls,
        batch_id: BatchId,
        items: tuple[BatchItem, ...],
        created_at: datetime,
        unmatched_files: tuple[str, ...] = (),
    ) -> "Batch":
        return cls(
            batch_id=batch_id,
            items=items,
            status=BatchStatus.PENDING,
            created_at=created_at,
            unmatched_files=unmatched_files,
        )
```

Add alongside `completed()`:

```python
    def failed(self) -> "Batch":
        return replace(self, status=BatchStatus.FAILED)
```

Note: `created_at` must be declared before `unmatched_files` in the dataclass body so the defaulted field stays last.

- [ ] **Step 5: Add `from_dict` to `AnalysisResult`**

In `src/overtone/domain/analysis_result.py`, add this method after `to_dict`. It re-runs `__post_init__` validation automatically, so a malformed payload raises `InvalidAnalysisResultError`:

```python
    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "AnalysisResult":
        return cls(
            emotional_tone=EmotionalTone(payload["emotional_tone"]),
            emotional_intensity=EmotionalIntensity(payload["emotional_intensity"]),
            background_noise_present=bool(payload["background_noise_present"]),
            background_noise_type=str(payload["background_noise_type"]),
            background_noise_severity=NoiseSeverity(payload["background_noise_severity"]),
            audio_quality=AudioQuality(payload["audio_quality"]),
            speaker_overlap_present=bool(payload["speaker_overlap_present"]),
            long_silence_present=bool(payload["long_silence_present"]),
            confidence=float(payload["confidence"]),  # type: ignore[arg-type]
        )
```

- [ ] **Step 6: Update the existing `Batch.create` call sites**

Three test files construct batches. Add a `CREATED_AT` constant to each and pass it:

- `tests/domain/test_batch.py` — in `batch_of`: `return Batch.create(new_batch_id(), items, CREATED_AT, unmatched_files=unmatched)`
- `tests/infrastructure/test_adapters.py` — both `Batch.create(new_batch_id(), (BatchItem.pending("a.ogg"),))` calls become `Batch.create(new_batch_id(), (BatchItem.pending("a.ogg"),), CREATED_AT)`, with `CREATED_AT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)` defined at module level.
- `tests/application/test_process_batch.py` — in `seed`: `repository.save(Batch.create(batch_id, items, CREATED_AT))`, same constant.

- [ ] **Step 7: Run the full suite**

Run: `python -m uv run pytest`
Expected: PASS. `tests/application/test_submit_batch.py` will still fail to import or error — that is Task 2's job; if it fails here, note it and continue.

- [ ] **Step 8: Verify quality gates**

Run: `python -m uv run ruff check . ; python -m uv run black --check . ; python -m uv run mypy`
Expected: all clean.

---

### Task 2: `Clock` port and `SubmitBatch` timestamping

**Files:**
- Create: `src/overtone/application/ports/clock.py`
- Create: `src/overtone/infrastructure/time/__init__.py`, `src/overtone/infrastructure/time/system_clock.py`
- Modify: `src/overtone/application/use_cases/submit_batch.py`
- Modify: `tests/application/test_submit_batch.py`

**Interfaces:**
- Consumes: `Batch.create(..., created_at, ...)` from Task 1.
- Produces:
  - `Clock` ABC with `now() -> datetime`
  - `SystemClock` returning `datetime.now(UTC)`
  - `SubmitBatch(extractor, parser, storage, repository, clock)` — `clock` is a new required keyword argument.

- [ ] **Step 1: Write the failing test**

Add to `tests/application/test_submit_batch.py`:

```python
from datetime import UTC, datetime

from overtone.application.ports.clock import Clock

CREATED_AT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


class FixedClock(Clock):
    def now(self) -> datetime:
        return CREATED_AT


def test_batch_is_stamped_with_the_submission_time(
    submit: SubmitBatch, repository: InMemoryBatchRepository, tmp_path: Path
):
    archive = build_zip(tmp_path, {"labels.csv": MANIFEST, "call_001.ogg": b"a", "call_002.ogg": b"b"})

    batch = repository.get(submit.execute(archive))

    assert batch.created_at == CREATED_AT
```

Update the existing `submit` fixture to inject the clock:

```python
@pytest.fixture
def submit(repository: InMemoryBatchRepository, storage: LocalFileStorage) -> SubmitBatch:
    return SubmitBatch(
        extractor=ZipArchiveExtractor(),
        parser=CsvManifestParser(),
        storage=storage,
        repository=repository,
        clock=FixedClock(),
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m uv run pytest tests/application/test_submit_batch.py -v`
Expected: FAIL — `No module named 'overtone.application.ports.clock'`.

- [ ] **Step 3: Create the port**

`src/overtone/application/ports/clock.py`:

```python
from abc import ABC, abstractmethod
from datetime import datetime


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime:
        """Current time, timezone-aware and in UTC."""
```

- [ ] **Step 4: Create the adapter**

`src/overtone/infrastructure/time/__init__.py` — empty.

`src/overtone/infrastructure/time/system_clock.py`:

```python
from datetime import UTC, datetime

from overtone.application.ports.clock import Clock


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)
```

- [ ] **Step 5: Inject the clock into `SubmitBatch`**

In `src/overtone/application/use_cases/submit_batch.py`, import `Clock`, add `clock: Clock` as the final constructor parameter, store it as `self._clock`, and pass the timestamp in `execute`:

```python
        batch = Batch.create(
            batch_id,
            items=tuple(self._to_item(row, audio_names) for row in rows),
            created_at=self._clock.now(),
            unmatched_files=self._unmatched(audio_names, rows),
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m uv run pytest`
Expected: PASS, 94+ tests.

- [ ] **Step 7: Verify quality gates**

Run: `python -m uv run ruff check . ; python -m uv run black --check . ; python -m uv run mypy`
Expected: all clean.

---

### Task 3: Repository contract suite and `list_recent`

**Files:**
- Create: `tests/infrastructure/repository_contract.py`
- Create: `tests/infrastructure/test_in_memory_batch_repository.py`
- Modify: `src/overtone/application/ports/batch_repository.py`
- Modify: `src/overtone/infrastructure/persistence/in_memory_batch_repository.py`
- Modify: `tests/infrastructure/test_adapters.py` (remove the three repository tests moved into the contract suite)

**Interfaces:**
- Consumes: `Batch`, `BatchItem`, `new_batch_id` from Task 1.
- Produces:
  - `BatchRepository.list_recent(limit: int) -> tuple[Batch, ...]` — newest first, capped at `limit`.
  - `BatchRepositoryContract` — a mixin test class exposing an abstract `repository` fixture, reused verbatim by the Postgres adapter in Task 4.

- [ ] **Step 1: Write the failing contract suite**

`tests/infrastructure/repository_contract.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest

from overtone.application.ports.batch_repository import BatchRepository
from overtone.domain.batch import Batch, BatchItem, new_batch_id
from overtone.domain.enums import BatchStatus
from overtone.domain.exceptions import BatchNotFoundError

BASE_TIME = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


def a_batch(minutes: int = 0, unmatched: tuple[str, ...] = ()) -> Batch:
    items = (BatchItem.pending("call_001.ogg"),)
    return Batch.create(
        new_batch_id(), items, BASE_TIME + timedelta(minutes=minutes), unmatched_files=unmatched
    )


class BatchRepositoryContract:
    """Behaviour every BatchRepository must exhibit. Subclass and supply `repository`."""

    def test_returns_the_saved_batch(self, repository: BatchRepository):
        batch = a_batch()

        repository.save(batch)

        assert repository.get(batch.batch_id) == batch

    def test_keeps_only_the_latest_save(self, repository: BatchRepository):
        batch = a_batch()
        repository.save(batch)

        repository.save(batch.started())

        assert repository.get(batch.batch_id).status is BatchStatus.RUNNING

    def test_round_trips_unmatched_files(self, repository: BatchRepository):
        batch = a_batch(unmatched=("stray.ogg",))

        repository.save(batch)

        assert repository.get(batch.batch_id).unmatched_files == ("stray.ogg",)

    def test_round_trips_a_completed_item_with_its_result(self, repository: BatchRepository):
        batch = a_batch()
        batch = batch.replacing(batch.items[0].succeeded(SAMPLE_RESULT))

        repository.save(batch)

        assert repository.get(batch.batch_id).items[0].result == SAMPLE_RESULT

    def test_round_trips_a_failed_item_with_its_reason(self, repository: BatchRepository):
        batch = a_batch()
        batch = batch.replacing(batch.items[0].failed("decoder blew up"))

        repository.save(batch)

        assert repository.get(batch.batch_id).items[0].error_message == "decoder blew up"

    def test_raises_for_an_unknown_batch(self, repository: BatchRepository):
        with pytest.raises(BatchNotFoundError):
            repository.get(new_batch_id())

    def test_lists_recent_batches_newest_first(self, repository: BatchRepository):
        older, newer = a_batch(minutes=0), a_batch(minutes=5)
        repository.save(older)
        repository.save(newer)

        listed = repository.list_recent(10)

        assert [batch.batch_id for batch in listed[:2]] == [newer.batch_id, older.batch_id]

    def test_list_recent_honours_the_limit(self, repository: BatchRepository):
        for minute in range(3):
            repository.save(a_batch(minutes=minute))

        assert len(repository.list_recent(2)) == 2
```

`SAMPLE_RESULT` is referenced by two of those tests. Define it at module level, after `BASE_TIME`, with its imports folded into the import block at the top of the file:

```python
from overtone.domain.analysis_result import AnalysisResult
from overtone.domain.enums import (
    AudioQuality,
    EmotionalIntensity,
    EmotionalTone,
    NoiseSeverity,
)

SAMPLE_RESULT = AnalysisResult(
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
```

`tests/infrastructure/test_in_memory_batch_repository.py`:

```python
import pytest

from overtone.infrastructure.persistence.in_memory_batch_repository import (
    InMemoryBatchRepository,
)
from tests.infrastructure.repository_contract import BatchRepositoryContract


class TestInMemoryBatchRepository(BatchRepositoryContract):
    @pytest.fixture
    def repository(self) -> InMemoryBatchRepository:
        return InMemoryBatchRepository()
```

For `from tests.infrastructure...` to import, add empty `__init__.py` files to `tests/`, `tests/domain/`, `tests/application/`, `tests/infrastructure/`, and `tests/integration/`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m uv run pytest tests/infrastructure/test_in_memory_batch_repository.py -v`
Expected: FAIL — `InMemoryBatchRepository` has no attribute `list_recent`.

- [ ] **Step 3: Add `list_recent` to the port**

In `src/overtone/application/ports/batch_repository.py`:

```python
    @abstractmethod
    def list_recent(self, limit: int) -> tuple[Batch, ...]:
        """Return up to `limit` batches, newest first."""
```

- [ ] **Step 4: Implement it in the in-memory adapter**

In `src/overtone/infrastructure/persistence/in_memory_batch_repository.py`:

```python
    def list_recent(self, limit: int) -> tuple[Batch, ...]:
        newest_first = sorted(
            self._batches.values(), key=lambda batch: batch.created_at, reverse=True
        )
        return tuple(newest_first[:limit])
```

- [ ] **Step 5: Remove the superseded tests**

Delete `test_repository_returns_the_saved_batch`, `test_repository_keeps_only_the_latest_save`, and `test_repository_raises_for_an_unknown_batch` from `tests/infrastructure/test_adapters.py`, along with any imports they alone used. The contract suite covers them.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m uv run pytest`
Expected: PASS.

- [ ] **Step 7: Verify quality gates**

Run: `python -m uv run ruff check . ; python -m uv run black --check . ; python -m uv run mypy`
Expected: all clean.

---

### Task 4: Postgres repository, schema, and local Postgres

**Files:**
- Create: `src/overtone/infrastructure/persistence/schema.sql`
- Create: `src/overtone/infrastructure/persistence/postgres_batch_repository.py`
- Create: `tests/infrastructure/test_postgres_batch_repository.py`
- Create: `docker-compose.yml`
- Modify: `pyproject.toml` (add `psycopg[binary]>=3.2`)

**Interfaces:**
- Consumes: `BatchRepositoryContract` from Task 3, `AnalysisResult.from_dict` from Task 1.
- Produces: `PostgresBatchRepository(database_url: str)` with `create_schema() -> None`, satisfying `BatchRepository`.

- [ ] **Step 1: Add the dependency and local Postgres**

In `pyproject.toml`, set `dependencies = ["psycopg[binary]>=3.2"]`.

`docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: overtone
      POSTGRES_PASSWORD: overtone
      POSTGRES_DB: overtone
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U overtone"]
      interval: 5s
      timeout: 5s
      retries: 10
```

Run: `python -m uv sync` then `docker compose up -d`
Expected: Postgres healthy on 5432. If Docker Desktop is not running, start it first.

- [ ] **Step 2: Write the failing test**

`tests/infrastructure/test_postgres_batch_repository.py`:

```python
import os

import pytest

from overtone.infrastructure.persistence.postgres_batch_repository import (
    PostgresBatchRepository,
)
from tests.infrastructure.repository_contract import BatchRepositoryContract

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    DATABASE_URL is None, reason="DATABASE_URL not set; skipping Postgres contract tests"
)


class TestPostgresBatchRepository(BatchRepositoryContract):
    @pytest.fixture
    def repository(self) -> PostgresBatchRepository:
        assert DATABASE_URL is not None
        repository = PostgresBatchRepository(DATABASE_URL)
        repository.create_schema()
        repository.delete_all()
        return repository
```

- [ ] **Step 3: Run test to verify it fails**

Run: `$env:DATABASE_URL="postgresql://overtone:overtone@localhost:5432/overtone"; python -m uv run pytest tests/infrastructure/test_postgres_batch_repository.py -v`
Expected: FAIL — `No module named 'overtone.infrastructure.persistence.postgres_batch_repository'`.

- [ ] **Step 4: Write the schema**

`src/overtone/infrastructure/persistence/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS batches (
    batch_id        TEXT PRIMARY KEY,
    status          TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    unmatched_files JSONB NOT NULL,
    items           JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS batches_created_at_idx ON batches (created_at DESC);
```

- [ ] **Step 5: Write the repository**

`src/overtone/infrastructure/persistence/postgres_batch_repository.py`. Items are stored as a JSONB document rather than a child table because a batch is only ever read and written whole:

```python
import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

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

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def create_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(SCHEMA.read_text(encoding="utf-8"))

    def delete_all(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM batches")

    def save(self, batch: Batch) -> None:
        with self._connect() as connection:
            connection.execute(UPSERT, self._to_row(batch))

    def get(self, batch_id: BatchId) -> Batch:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {COLUMNS} FROM batches WHERE batch_id = %s", (batch_id,)
            ).fetchone()
        if row is None:
            raise BatchNotFoundError(f"no batch with id {batch_id}")
        return self._to_batch(row)

    def list_recent(self, limit: int) -> tuple[Batch, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {COLUMNS} FROM batches ORDER BY created_at DESC LIMIT %s", (limit,)
            ).fetchall()
        return tuple(self._to_batch(row) for row in rows)

    def _connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self._database_url)

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
```

Remove the unused `json` import if ruff flags it.

- [ ] **Step 6: Run the contract suite against Postgres**

Run: `$env:DATABASE_URL="postgresql://overtone:overtone@localhost:5432/overtone"; python -m uv run pytest tests/infrastructure/test_postgres_batch_repository.py -v`
Expected: PASS — all eight contract tests, identical to the in-memory adapter.

- [ ] **Step 7: Confirm the suite still skips cleanly without Postgres**

Run: `python -m uv run pytest` (with `DATABASE_URL` unset — open a fresh terminal or `Remove-Item Env:DATABASE_URL`)
Expected: PASS with 8 skipped.

- [ ] **Step 8: Verify quality gates**

Run: `python -m uv run ruff check . ; python -m uv run black --check . ; python -m uv run mypy`
Expected: all clean.

---

### Task 5: `JobRunner` port and adapters

**Files:**
- Create: `src/overtone/application/ports/job_runner.py`
- Create: `src/overtone/infrastructure/jobs/__init__.py`, `src/overtone/infrastructure/jobs/thread_pool_job_runner.py`, `src/overtone/infrastructure/jobs/synchronous_job_runner.py`
- Create: `tests/infrastructure/test_job_runners.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `JobRunner` ABC with `submit(work: Callable[[], None]) -> None` and `shutdown() -> None`
  - `ThreadPoolJobRunner(max_workers: int = 2)`
  - `SynchronousJobRunner()` — runs inline; used by every route test.

- [ ] **Step 1: Write the failing tests**

`tests/infrastructure/test_job_runners.py`:

```python
from overtone.infrastructure.jobs.synchronous_job_runner import SynchronousJobRunner
from overtone.infrastructure.jobs.thread_pool_job_runner import ThreadPoolJobRunner


def test_synchronous_runner_runs_the_work_immediately():
    calls: list[str] = []

    SynchronousJobRunner().submit(lambda: calls.append("ran"))

    assert calls == ["ran"]


def test_synchronous_runner_lets_failures_surface():
    def explode() -> None:
        raise RuntimeError("boom")

    try:
        SynchronousJobRunner().submit(explode)
    except RuntimeError as error:
        assert str(error) == "boom"
    else:
        raise AssertionError("expected the failure to propagate")


def test_thread_pool_runner_runs_the_work():
    calls: list[str] = []
    runner = ThreadPoolJobRunner(max_workers=1)

    runner.submit(lambda: calls.append("ran"))
    runner.shutdown()

    assert calls == ["ran"]


def test_thread_pool_runner_keeps_serving_after_a_job_fails():
    calls: list[str] = []
    runner = ThreadPoolJobRunner(max_workers=1)

    runner.submit(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    runner.submit(lambda: calls.append("ran"))
    runner.shutdown()

    assert calls == ["ran"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m uv run pytest tests/infrastructure/test_job_runners.py -v`
Expected: FAIL — `No module named 'overtone.infrastructure.jobs'`.

- [ ] **Step 3: Create the port**

`src/overtone/application/ports/job_runner.py`:

```python
from abc import ABC, abstractmethod
from collections.abc import Callable


class JobRunner(ABC):
    """Runs work outside the request thread. Keeps threading out of the use cases."""

    @abstractmethod
    def submit(self, work: Callable[[], None]) -> None: ...

    @abstractmethod
    def shutdown(self) -> None:
        """Wait for in-flight work to finish."""
```

- [ ] **Step 4: Create the adapters**

`src/overtone/infrastructure/jobs/__init__.py` — empty.

`src/overtone/infrastructure/jobs/synchronous_job_runner.py`:

```python
from collections.abc import Callable

from overtone.application.ports.job_runner import JobRunner


class SynchronousJobRunner(JobRunner):
    """Runs work inline. Used by tests so batch processing is deterministic."""

    def submit(self, work: Callable[[], None]) -> None:
        work()

    def shutdown(self) -> None:
        return None
```

`src/overtone/infrastructure/jobs/thread_pool_job_runner.py`:

```python
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from overtone.application.ports.job_runner import JobRunner

logger = logging.getLogger(__name__)


class ThreadPoolJobRunner(JobRunner):
    """Bounded in-process executor owned by the composition root.

    Batch state lives in Postgres, so a job running in one process is visible to status
    polls served by any other.
    """

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, work: Callable[[], None]) -> None:
        self._executor.submit(self._guarded(work))

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)

    def _guarded(self, work: Callable[[], None]) -> Callable[[], None]:
        def run() -> None:
            try:
                work()
            except Exception:
                logger.exception("background job failed")

        return run
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m uv run pytest tests/infrastructure/test_job_runners.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 6: Verify quality gates**

Run: `python -m uv run ruff check . ; python -m uv run black --check . ; python -m uv run mypy`
Expected: all clean.

---

### Task 6: `ProcessBatch` marks crashes and deletes audio

**Files:**
- Modify: `src/overtone/application/ports/file_storage.py`
- Modify: `src/overtone/infrastructure/storage/local_file_storage.py`
- Modify: `src/overtone/application/use_cases/process_batch.py`
- Modify: `tests/application/test_process_batch.py`
- Modify: `tests/infrastructure/test_adapters.py`

**Interfaces:**
- Consumes: `Batch.failed()` from Task 1.
- Produces: `FileStorage.discard(batch_id: BatchId) -> None` — removes the batch workspace and everything in it, idempotently.

- [ ] **Step 1: Write the failing tests**

Add to `tests/infrastructure/test_adapters.py`:

```python
def test_discard_removes_the_batch_workspace(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)
    batch_id = new_batch_id()
    storage.path_for(batch_id, "call_001.ogg").write_bytes(b"audio")

    storage.discard(batch_id)

    assert not (tmp_path / batch_id).exists()


def test_discard_is_safe_to_call_twice(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)
    batch_id = new_batch_id()

    storage.discard(batch_id)
    storage.discard(batch_id)
```

Add to `tests/application/test_process_batch.py`:

```python
def test_audio_is_deleted_once_processing_finishes(
    repository: RecordingRepository, storage: LocalFileStorage
):
    batch_id = seed(repository, storage, BatchItem.pending("a.ogg"))

    run(repository, storage, FakeAnalyzer(), batch_id)

    assert not storage.path_for(batch_id, "a.ogg").exists()


def test_a_crash_outside_item_analysis_marks_the_batch_failed(
    repository: RecordingRepository, storage: LocalFileStorage
):
    batch_id = seed(repository, storage, BatchItem.pending("a.ogg"))
    repository.explode_on_completion = True

    with pytest.raises(RuntimeError):
        run(repository, storage, FakeAnalyzer(), batch_id)

    assert repository.get(batch_id).status is BatchStatus.FAILED
```

Extend `RecordingRepository` so it can simulate a mid-job crash:

```python
class RecordingRepository(InMemoryBatchRepository):
    def __init__(self) -> None:
        super().__init__()
        self.saves: list[Batch] = []
        self.explode_on_completion = False

    def save(self, batch: Batch) -> None:
        if self.explode_on_completion and batch.status is BatchStatus.COMPLETED:
            raise RuntimeError("database went away")
        super().save(batch)
        self.saves.append(batch)
```

Note: `test_progress_is_persisted_after_each_item` asserts `resolved_counts == [0, 1, 2, 2]`. Deleting audio does not add a save, so that expectation still holds.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m uv run pytest tests/application/test_process_batch.py tests/infrastructure/test_adapters.py -v`
Expected: FAIL — `LocalFileStorage` has no attribute `discard`; batch status is `completed`, not `failed`.

- [ ] **Step 3: Add `discard` to the port and adapter**

In `src/overtone/application/ports/file_storage.py`:

```python
    @abstractmethod
    def discard(self, batch_id: BatchId) -> None:
        """Delete this batch's workspace and its audio. Safe to call more than once."""
```

In `src/overtone/infrastructure/storage/local_file_storage.py`, add `import shutil` and:

```python
    def discard(self, batch_id: BatchId) -> None:
        shutil.rmtree(self._root / batch_id, ignore_errors=True)
```

- [ ] **Step 4: Make `ProcessBatch` clean up and record crashes**

Replace `execute` in `src/overtone/application/use_cases/process_batch.py`. Add `from overtone.domain.batch import Batch` to the imports:

```python
    def execute(self, batch_id: BatchId) -> None:
        batch = self._repository.get(batch_id).started()
        self._repository.save(batch)
        try:
            self._run(batch)
        except Exception:
            self._mark_failed(batch)
            raise
        finally:
            self._storage.discard(batch_id)

    def _run(self, batch: Batch) -> None:
        for item in batch.pending_items:
            batch = batch.replacing(self._analyze(batch.batch_id, item))
            self._repository.save(batch)
        self._repository.save(batch.completed())

    def _mark_failed(self, batch: Batch) -> None:
        try:
            self._repository.save(batch.failed())
        except Exception:  # noqa: BLE001 - already failing; do not mask the original error
            logger.exception("could not record batch failure")
```

Add at the top of the module:

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m uv run pytest`
Expected: PASS.

- [ ] **Step 6: Confirm the CLI still works end to end**

Run: `.\.venv\Scripts\overtone.exe analyze data\provided_calls_batch.zip --out out --format both`
Expected: `processed 3 file(s): 3 succeeded, 0 failed`.

- [ ] **Step 7: Verify quality gates**

Run: `python -m uv run ruff check . ; python -m uv run black --check . ; python -m uv run mypy`
Expected: all clean.

---

### Task 7: Config and composition for the web app

**Files:**
- Modify: `src/overtone/composition/config.py`
- Modify: `src/overtone/composition/container.py`
- Modify: `src/overtone/cli/main.py`
- Create: `tests/composition/__init__.py`, `tests/composition/test_config.py`

**Interfaces:**
- Consumes: `PostgresBatchRepository`, `ThreadPoolJobRunner`, `SystemClock` from Tasks 2, 4, 5.
- Produces:
  - `AppConfig(workspace_root, database_url=None, secret_key="dev", username="admin", password="admin", max_upload_bytes=524288000)`
  - `AppConfig.from_env() -> AppConfig`
  - `Container` gains `job_runner: JobRunner` and `batches: BatchRepository`
  - `build_container(config: AppConfig, job_runner: JobRunner | None = None) -> Container`

- [ ] **Step 1: Write the failing test**

`tests/composition/__init__.py` — empty.

`tests/composition/test_config.py`:

```python
from pathlib import Path

import pytest

from overtone.composition.config import AppConfig


def test_from_env_reads_every_setting(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/overtone")
    monkeypatch.setenv("SECRET_KEY", "s3cret")
    monkeypatch.setenv("OVERTONE_USERNAME", "autoace")
    monkeypatch.setenv("OVERTONE_PASSWORD", "hunter2")
    monkeypatch.setenv("OVERTONE_WORKSPACE_ROOT", "/tmp/work")
    monkeypatch.setenv("OVERTONE_MAX_UPLOAD_MB", "50")

    config = AppConfig.from_env()

    assert config.database_url == "postgresql://localhost/overtone"
    assert config.secret_key == "s3cret"
    assert config.username == "autoace"
    assert config.password == "hunter2"
    assert config.workspace_root == Path("/tmp/work")
    assert config.max_upload_bytes == 50 * 1024 * 1024


def test_from_env_falls_back_to_development_defaults(monkeypatch: pytest.MonkeyPatch):
    for name in (
        "DATABASE_URL",
        "SECRET_KEY",
        "OVERTONE_USERNAME",
        "OVERTONE_PASSWORD",
        "OVERTONE_WORKSPACE_ROOT",
        "OVERTONE_MAX_UPLOAD_MB",
    ):
        monkeypatch.delenv(name, raising=False)

    config = AppConfig.from_env()

    assert config.database_url is None
    assert config.username == "admin"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m uv run pytest tests/composition/test_config.py -v`
Expected: FAIL — `AppConfig` has no attribute `from_env`.

- [ ] **Step 3: Expand `AppConfig`**

Replace `src/overtone/composition/config.py`:

```python
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_UPLOAD_MB = 500


@dataclass(frozen=True)
class AppConfig:
    """Everything the composition root needs to wire the system."""

    workspace_root: Path
    database_url: str | None = None
    secret_key: str = "dev-secret-not-for-production"
    username: str = "admin"
    password: str = "admin"
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_MB * 1024 * 1024

    @classmethod
    def from_env(cls) -> "AppConfig":
        megabytes = int(os.environ.get("OVERTONE_MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB))
        return cls(
            workspace_root=Path(os.environ.get("OVERTONE_WORKSPACE_ROOT", "/tmp/overtone")),
            database_url=os.environ.get("DATABASE_URL"),
            secret_key=os.environ.get("SECRET_KEY", "dev-secret-not-for-production"),
            username=os.environ.get("OVERTONE_USERNAME", "admin"),
            password=os.environ.get("OVERTONE_PASSWORD", "admin"),
            max_upload_bytes=megabytes * 1024 * 1024,
        )
```

- [ ] **Step 4: Wire the container**

In `src/overtone/composition/container.py`, add `job_runner: JobRunner` to `Container`, and replace `build_container`:

```python
def build_container(config: AppConfig, job_runner: JobRunner | None = None) -> Container:
    """The one place that knows every layer.

    Replacing StubAnalyzer with the real pipeline is a single-line change here and
    nowhere else — that is the whole point of the AudioAnalyzer port.
    """
    analyzer = StubAnalyzer()
    storage = LocalFileStorage(config.workspace_root)
    repository = _build_repository(config)
    return Container(
        submit_batch=SubmitBatch(
            extractor=ZipArchiveExtractor(),
            parser=CsvManifestParser(),
            storage=storage,
            repository=repository,
            clock=SystemClock(),
        ),
        process_batch=ProcessBatch(analyzer=analyzer, storage=storage, repository=repository),
        batches=repository,
        serializers={"csv": CsvResultSerializer(), "json": JsonResultSerializer()},
        job_runner=job_runner or ThreadPoolJobRunner(),
    )


def _build_repository(config: AppConfig) -> BatchRepository:
    if config.database_url is None:
        return InMemoryBatchRepository()
    repository = PostgresBatchRepository(config.database_url)
    repository.create_schema()
    return repository
```

Import `JobRunner`, `ThreadPoolJobRunner`, `SystemClock`, and `PostgresBatchRepository` accordingly.

- [ ] **Step 5: Keep the CLI working**

`src/overtone/cli/main.py` needs no change — it constructs `AppConfig(workspace_root=...)`, which leaves `database_url` as `None` and so keeps the in-memory repository.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m uv run pytest`
Expected: PASS.

- [ ] **Step 7: Verify quality gates**

Run: `python -m uv run ruff check . ; python -m uv run black --check . ; python -m uv run mypy`
Expected: all clean.

---

### Task 8: Flask app factory, health check, and auth

**Files:**
- Create: `src/overtone/web/__init__.py`, `src/overtone/web/app.py`
- Create: `src/overtone/web/auth/__init__.py`, `src/overtone/web/auth/session_guard.py`
- Create: `src/overtone/web/blueprints/__init__.py`, `src/overtone/web/blueprints/auth.py`
- Create: `src/overtone/web/templates/base.html`, `src/overtone/web/templates/login.html`
- Create: `tests/web/__init__.py`, `tests/web/conftest.py`, `tests/web/test_auth.py`
- Modify: `pyproject.toml` (add `flask>=3.1`, `gunicorn>=23.0`)

**Interfaces:**
- Consumes: `AppConfig`, `build_container` from Task 7; `SynchronousJobRunner` from Task 5.
- Produces:
  - `create_app(config: AppConfig, job_runner: JobRunner | None = None) -> Flask`
  - `login_required(view)` decorator, redirecting to `auth.login` when the session lacks `authenticated`
  - `app.extensions["overtone"]` holding the `Container`

- [ ] **Step 1: Add dependencies**

In `pyproject.toml`, set `dependencies = ["psycopg[binary]>=3.2", "flask>=3.1", "gunicorn>=23.0"]`. Note gunicorn is unused on Windows locally but is what runs in the container.

Run: `python -m uv sync`

- [ ] **Step 2: Write the failing tests**

`tests/web/__init__.py` — empty.

`tests/web/conftest.py`:

```python
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from overtone.composition.config import AppConfig
from overtone.infrastructure.jobs.synchronous_job_runner import SynchronousJobRunner
from overtone.web.app import create_app

USERNAME = "autoace"
PASSWORD = "hunter2"


@pytest.fixture
def app(tmp_path: Path) -> Flask:
    config = AppConfig(
        workspace_root=tmp_path / "workspace",
        secret_key="test-secret",
        username=USERNAME,
        password=PASSWORD,
    )
    return create_app(config, job_runner=SynchronousJobRunner())


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def logged_in(client: FlaskClient) -> FlaskClient:
    client.post("/login", data={"username": USERNAME, "password": PASSWORD})
    return client
```

`tests/web/test_auth.py`:

```python
from flask.testing import FlaskClient

from tests.web.conftest import PASSWORD, USERNAME


def test_healthz_is_public(client: FlaskClient):
    assert client.get("/healthz").status_code == 200


def test_the_dashboard_redirects_when_not_logged_in(client: FlaskClient):
    response = client.get("/")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_valid_credentials_grant_access(client: FlaskClient):
    response = client.post(
        "/login", data={"username": USERNAME, "password": PASSWORD}, follow_redirects=True
    )

    assert response.status_code == 200


def test_the_dashboard_is_reachable_once_logged_in(logged_in: FlaskClient):
    assert logged_in.get("/").status_code == 200


def test_wrong_password_is_rejected(client: FlaskClient):
    response = client.post("/login", data={"username": USERNAME, "password": "wrong"})

    assert response.status_code == 401


def test_unknown_username_is_rejected(client: FlaskClient):
    response = client.post("/login", data={"username": "nobody", "password": PASSWORD})

    assert response.status_code == 401


def test_logout_ends_the_session(logged_in: FlaskClient):
    logged_in.post("/logout")

    assert logged_in.get("/").status_code == 302


def test_an_oversized_upload_gets_a_readable_message(app: Flask, logged_in: FlaskClient):
    app.config["MAX_CONTENT_LENGTH"] = 10

    response = logged_in.post(
        "/batches",
        data={"archive": (io.BytesIO(b"x" * 5000), "big.zip")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 413
    assert "too large" in response.data.decode().lower()
```

That test needs `import io` and `from flask import Flask` at the top of the file.

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m uv run pytest tests/web -v`
Expected: FAIL — `No module named 'overtone.web'`.

- [ ] **Step 4: Write the session guard**

`src/overtone/web/__init__.py` and `src/overtone/web/auth/__init__.py` — empty.

`src/overtone/web/auth/session_guard.py`:

```python
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from flask import redirect, session, url_for

SESSION_KEY = "authenticated"

View = TypeVar("View", bound=Callable[..., Any])


def login_required(view: View) -> View:
    @wraps(view)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        if not session.get(SESSION_KEY):
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return cast(View, guarded)
```

- [ ] **Step 5: Write the auth blueprint**

`src/overtone/web/blueprints/__init__.py` — empty.

`src/overtone/web/blueprints/auth.py`:

```python
import hmac

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from werkzeug.wrappers import Response

from overtone.web.auth.session_guard import SESSION_KEY

blueprint = Blueprint("auth", __name__)


@blueprint.get("/login")
def login_form() -> str:
    return render_template("login.html")


@blueprint.post("/login")
def login() -> Response | tuple[str, int]:
    if not _credentials_match(request.form.get("username", ""), request.form.get("password", "")):
        return render_template("login.html", error="Incorrect username or password."), 401
    session[SESSION_KEY] = True
    return redirect(url_for("batches.dashboard"))


@blueprint.post("/logout")
def logout() -> Response:
    session.clear()
    return redirect(url_for("auth.login"))


def _credentials_match(username: str, password: str) -> bool:
    config = current_app.config["OVERTONE_CONFIG"]
    return hmac.compare_digest(username, config.username) and hmac.compare_digest(
        password, config.password
    )
```

- [ ] **Step 6: Write the app factory**

`src/overtone/web/app.py`. `batches` blueprint arrives in Task 9 — register it now and create the module in that task, or temporarily comment the two `batches` lines and restore them in Task 9:

```python
from flask import Flask

from overtone.application.ports.job_runner import JobRunner
from overtone.composition.config import AppConfig
from overtone.composition.container import build_container
from overtone.web.blueprints import auth, batches


def create_app(config: AppConfig, job_runner: JobRunner | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.secret_key
    app.config["MAX_CONTENT_LENGTH"] = config.max_upload_bytes
    app.config["OVERTONE_CONFIG"] = config
    app.extensions["overtone"] = build_container(config, job_runner=job_runner)
    app.register_blueprint(auth.blueprint)
    app.register_blueprint(batches.blueprint)
    _register_health_check(app)
    return app


def _register_health_check(app: Flask) -> None:
    @app.get("/healthz")
    def healthz() -> tuple[str, int]:
        return "ok", 200
```

Add the oversized-upload handler to the same module, and call `_register_error_handlers(app)` from `create_app` just after `_register_health_check(app)`. It deliberately does not touch the database, so it still works when the request body was rejected before any use case ran:

```python
from werkzeug.exceptions import RequestEntityTooLarge


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(RequestEntityTooLarge)
    def too_large(error: RequestEntityTooLarge) -> tuple[str, int]:
        limit_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        message = f"That upload is too large. The limit is {limit_mb} MB."
        return render_template("dashboard.html", batches=(), error=message), 413
```

Import `render_template` from `flask` in `app.py`.

- [ ] **Step 7: Write the templates**

`src/overtone/web/templates/base.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Overtone{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
  <header>
    <h1><a href="{{ url_for('batches.dashboard') }}">Overtone</a></h1>
    {% if session.get('authenticated') %}
      <form method="post" action="{{ url_for('auth.logout') }}">
        <button type="submit">Log out</button>
      </form>
    {% endif %}
  </header>
  <main>{% block content %}{% endblock %}</main>
</body>
</html>
```

`src/overtone/web/templates/login.html`:

```html
{% extends "base.html" %}
{% block title %}Sign in — Overtone{% endblock %}
{% block content %}
<h2>Sign in</h2>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post" action="{{ url_for('auth.login') }}">
  <label>Username <input type="text" name="username" required autofocus></label>
  <label>Password <input type="password" name="password" required></label>
  <button type="submit">Sign in</button>
</form>
{% endblock %}
```

`src/overtone/web/static/style.css`:

```css
:root { --line: #d5d8dd; --error: #b3261e; --warn: #8a6100; --muted: #5f6570; }

* { box-sizing: border-box; }

body {
  margin: 0;
  font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  color: #1b1d21;
  background: #fbfbfc;
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--line);
  background: #fff;
}

header h1 { font-size: 1.1rem; margin: 0; }
header a { color: inherit; text-decoration: none; }

main { max-width: 70rem; margin: 0 auto; padding: 1.5rem; }

h2 { font-size: 1rem; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }

table { width: 100%; border-collapse: collapse; margin-top: .5rem; font-size: .9rem; }
th, td { text-align: left; padding: .5rem .6rem; border-bottom: 1px solid var(--line); }
th { color: var(--muted); font-weight: 600; }

tr.failed td { background: #fdf2f1; }

.error { color: var(--error); }
.warning { color: var(--warn); }
.hint { color: var(--muted); font-size: .875rem; }

form { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; }
label { display: flex; gap: .5rem; align-items: center; }

button {
  padding: .45rem .9rem;
  border: 1px solid var(--line);
  border-radius: .3rem;
  background: #1b1d21;
  color: #fff;
  cursor: pointer;
}

input[type="text"], input[type="password"] {
  padding: .4rem .5rem;
  border: 1px solid var(--line);
  border-radius: .3rem;
}
```

For Flask to find these, `Flask(__name__)` in `overtone/web/app.py` resolves `templates/` and `static/` relative to that package — the paths above are correct.

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m uv run pytest tests/web -v`
Expected: PASS, 7 tests. If `batches` does not exist yet, complete Task 9 and re-run.

- [ ] **Step 9: Verify quality gates**

Run: `python -m uv run ruff check . ; python -m uv run black --check . ; python -m uv run mypy`
Expected: all clean.

---

### Task 9: Batches blueprint — upload, detail, status, download

**Files:**
- Create: `src/overtone/web/blueprints/batches.py`
- Create: `src/overtone/web/templates/dashboard.html`, `src/overtone/web/templates/batch_detail.html`
- Create: `src/overtone/web/static/poll.js`
- Create: `tests/web/test_batches.py`
- Modify: `pyproject.toml` (include package data so templates ship in the wheel)

**Interfaces:**
- Consumes: `login_required` from Task 8; `Container` fields `submit_batch`, `process_batch`, `batches`, `serializers`, `job_runner`.
- Produces routes: `GET /` (`batches.dashboard`), `POST /batches` (`batches.upload`), `GET /batches/<batch_id>` (`batches.detail`), `GET /batches/<batch_id>/status.json` (`batches.status`), `GET /batches/<batch_id>/download/<fmt>` (`batches.download`).

- [ ] **Step 1: Write the failing tests**

`tests/web/test_batches.py`:

```python
import io
import json
import zipfile

from flask.testing import FlaskClient

MANIFEST = b"name,result_json\ncall_001.ogg,\ncall_002.ogg,\ncall_missing.ogg,\n"


def batch_archive() -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("labels.csv", MANIFEST)
        archive.writestr("call_001.ogg", b"OggS one")
        archive.writestr("call_002.ogg", b"OggS two")
        archive.writestr("stray.ogg", b"OggS stray")
    buffer.seek(0)
    return buffer


def upload(client: FlaskClient) -> str:
    response = client.post(
        "/batches",
        data={"archive": (batch_archive(), "evaluation_batch.zip")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    return response.headers["Location"]


def test_upload_redirects_to_the_batch_page(logged_in: FlaskClient):
    assert "/batches/" in upload(logged_in)


def test_status_reports_completion_and_counts(logged_in: FlaskClient):
    location = upload(logged_in)

    payload = json.loads(logged_in.get(f"{location}/status.json").data)

    assert payload["status"] == "completed"
    assert payload["total"] == 3
    assert payload["succeeded"] == 2
    assert payload["failed"] == 1


def test_status_reports_unmatched_files(logged_in: FlaskClient):
    location = upload(logged_in)

    payload = json.loads(logged_in.get(f"{location}/status.json").data)

    assert payload["unmatched_files"] == ["stray.ogg"]


def test_the_batch_page_shows_each_filename_and_the_failure_reason(logged_in: FlaskClient):
    location = upload(logged_in)

    body = logged_in.get(location).data.decode()

    assert "call_001.ogg" in body
    assert "call_missing.ogg" in body
    assert "absent from the batch" in body


def test_csv_download_preserves_original_filenames(logged_in: FlaskClient):
    location = upload(logged_in)

    body = logged_in.get(f"{location}/download/csv").data.decode()

    assert "call_001.ogg" in body
    assert body.startswith("name,status,error,emotional_tone")


def test_json_download_carries_the_output_schema(logged_in: FlaskClient):
    location = upload(logged_in)

    payload = json.loads(logged_in.get(f"{location}/download/json").data)

    assert payload["results"][0]["result"]["emotional_tone"] == "neutral"


def test_an_unknown_download_format_is_rejected(logged_in: FlaskClient):
    location = upload(logged_in)

    assert logged_in.get(f"{location}/download/xml").status_code == 404


def test_a_corrupt_archive_is_reported_on_the_upload_page(logged_in: FlaskClient):
    response = logged_in.post(
        "/batches",
        data={"archive": (io.BytesIO(b"not a zip"), "broken.zip")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "could not read archive" in response.data.decode()


def test_a_batch_with_no_manifest_is_reported(logged_in: FlaskClient):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("call_001.ogg", b"OggS")
    buffer.seek(0)

    response = logged_in.post(
        "/batches",
        data={"archive": (buffer, "no_manifest.zip")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "manifest" in response.data.decode().lower()


def test_uploading_without_a_file_is_reported(logged_in: FlaskClient):
    response = logged_in.post("/batches", data={}, content_type="multipart/form-data")

    assert response.status_code == 400


def test_the_dashboard_lists_a_submitted_batch(logged_in: FlaskClient):
    upload(logged_in)

    assert "batch" in logged_in.get("/").data.decode().lower()


def test_an_unknown_batch_returns_404(logged_in: FlaskClient):
    assert logged_in.get("/batches/does-not-exist").status_code == 404


def test_batch_routes_require_a_session(client: FlaskClient):
    assert client.get("/batches/anything").status_code == 302
    assert client.post("/batches").status_code == 302
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m uv run pytest tests/web/test_batches.py -v`
Expected: FAIL — `No module named 'overtone.web.blueprints.batches'`.

- [ ] **Step 3: Write the blueprint**

`src/overtone/web/blueprints/batches.py`. The upload is written to a temporary file because `ZipArchiveExtractor` takes a `Path`:

```python
import tempfile
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, abort, current_app, jsonify, redirect, render_template, request, url_for
from werkzeug.datastructures import FileStorage as UploadedFile

from overtone.composition.container import Container
from overtone.domain.batch import Batch, BatchId
from overtone.domain.exceptions import BatchNotFoundError, DomainError
from overtone.web.auth.session_guard import login_required

blueprint = Blueprint("batches", __name__)
RECENT_LIMIT = 20


@blueprint.get("/")
@login_required
def dashboard() -> str:
    return render_template("dashboard.html", batches=_container().batches.list_recent(RECENT_LIMIT))


@blueprint.post("/batches")
@login_required
def upload() -> Any:
    upload_file = request.files.get("archive")
    if upload_file is None or not upload_file.filename:
        return _upload_error("Choose a ZIP file containing your audio and a CSV manifest.")
    try:
        batch_id = _submit(upload_file)
    except DomainError as error:
        return _upload_error(str(error))
    _container().job_runner.submit(lambda: _container().process_batch.execute(batch_id))
    return redirect(url_for("batches.detail", batch_id=batch_id))


@blueprint.get("/batches/<batch_id>")
@login_required
def detail(batch_id: str) -> str:
    return render_template("batch_detail.html", batch=_find(batch_id))


@blueprint.get("/batches/<batch_id>/status.json")
@login_required
def status(batch_id: str) -> Response:
    return jsonify(_status_payload(_find(batch_id)))


@blueprint.get("/batches/<batch_id>/download/<fmt>")
@login_required
def download(batch_id: str, fmt: str) -> Response:
    serializer = _container().serializers.get(fmt)
    if serializer is None:
        abort(404)
    batch = _find(batch_id)
    return Response(
        serializer.serialize(batch),
        mimetype="text/csv" if fmt == "csv" else "application/json",
        headers={"Content-Disposition": f"attachment; filename=results.{fmt}"},
    )


def _submit(upload_file: UploadedFile) -> BatchId:
    with tempfile.TemporaryDirectory(prefix="overtone-upload-") as staging:
        archive = Path(staging) / "batch.zip"
        upload_file.save(archive)
        return _container().submit_batch.execute(archive)


def _status_payload(batch: Batch) -> dict[str, Any]:
    return {
        "status": batch.status.value,
        "total": batch.total,
        "succeeded": batch.succeeded_count,
        "failed": batch.failed_count,
        "unmatched_files": list(batch.unmatched_files),
        "finished": batch.status.value in {"completed", "failed"},
    }


def _upload_error(message: str) -> tuple[str, int]:
    batches = _container().batches.list_recent(RECENT_LIMIT)
    return render_template("dashboard.html", batches=batches, error=message), 400


def _find(batch_id: str) -> Batch:
    try:
        return _container().batches.get(BatchId(batch_id))
    except BatchNotFoundError:
        abort(404)


def _container() -> Container:
    container: Container = current_app.extensions["overtone"]
    return container
```

Note `_find` returns `Batch` but `abort` raises — mypy needs no `return` after `abort` because it is typed `NoReturn`.

- [ ] **Step 4: Write the templates**

`src/overtone/web/templates/dashboard.html`:

```html
{% extends "base.html" %}
{% block title %}Batches — Overtone{% endblock %}
{% block content %}
<h2>Upload an evaluation batch</h2>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post" action="{{ url_for('batches.upload') }}" enctype="multipart/form-data">
  <input type="file" name="archive" accept=".zip" required>
  <button type="submit">Upload and analyse</button>
</form>
<p class="hint">
  A ZIP containing your audio files and exactly one CSV manifest with a <code>name</code> column.
</p>

<h2>Recent batches</h2>
{% if batches %}
<table>
  <thead><tr><th>Batch</th><th>Submitted</th><th>Status</th><th>Files</th></tr></thead>
  <tbody>
  {% for batch in batches %}
    <tr>
      <td><a href="{{ url_for('batches.detail', batch_id=batch.batch_id) }}">{{ batch.batch_id[:8] }}</a></td>
      <td>{{ batch.created_at.strftime('%Y-%m-%d %H:%M UTC') }}</td>
      <td>{{ batch.status.value }}</td>
      <td>{{ batch.total }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}
<p>No batches yet.</p>
{% endif %}
{% endblock %}
```

`src/overtone/web/templates/batch_detail.html`:

```html
{% extends "base.html" %}
{% block title %}Batch {{ batch.batch_id[:8] }} — Overtone{% endblock %}
{% block content %}
<h2>Batch {{ batch.batch_id[:8] }}</h2>

<p id="progress" data-status-url="{{ url_for('batches.status', batch_id=batch.batch_id) }}">
  {{ batch.succeeded_count + batch.failed_count }} of {{ batch.total }} processed
</p>

{% if batch.unmatched_files %}
<p class="warning">
  Not listed in the manifest and skipped: {{ batch.unmatched_files|join(', ') }}
</p>
{% endif %}

<p>
  <a href="{{ url_for('batches.download', batch_id=batch.batch_id, fmt='csv') }}">Download CSV</a>
  &middot;
  <a href="{{ url_for('batches.download', batch_id=batch.batch_id, fmt='json') }}">Download JSON</a>
</p>

<table>
  <thead>
    <tr>
      <th>File</th><th>Status</th><th>Tone</th><th>Intensity</th>
      <th>Noise</th><th>Severity</th><th>Quality</th><th>Overlap</th>
      <th>Silence</th><th>Confidence</th>
    </tr>
  </thead>
  <tbody>
  {% for item in batch.items %}
    <tr class="{{ 'failed' if item.status.value == 'failed' else '' }}">
      <td>{{ item.filename }}</td>
      <td>{{ item.status.value }}</td>
      {% if item.result %}
        <td>{{ item.result.emotional_tone.value }}</td>
        <td>{{ item.result.emotional_intensity.value }}</td>
        <td>{{ item.result.background_noise_type or '—' }}</td>
        <td>{{ item.result.background_noise_severity.value }}</td>
        <td>{{ item.result.audio_quality.value }}</td>
        <td>{{ item.result.speaker_overlap_present }}</td>
        <td>{{ item.result.long_silence_present }}</td>
        <td>{{ '%.2f'|format(item.result.confidence) }}</td>
      {% else %}
        <td colspan="8" class="error">{{ item.error_message }}</td>
      {% endif %}
    </tr>
  {% endfor %}
  </tbody>
</table>
<script src="{{ url_for('static', filename='poll.js') }}" defer></script>
{% endblock %}
```

`src/overtone/web/static/poll.js`:

```javascript
(function () {
  const progress = document.getElementById("progress");
  if (!progress) return;
  const url = progress.dataset.statusUrl;

  async function tick() {
    try {
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) return;
      const status = await response.json();
      progress.textContent =
        `${status.succeeded + status.failed} of ${status.total} processed` +
        ` — ${status.status}`;
      if (status.finished) {
        window.location.reload();
        return;
      }
    } catch (error) {
      // transient network failure; try again on the next tick
    }
    window.setTimeout(tick, 1000);
  }

  window.setTimeout(tick, 1000);
})();
```

The page reloads once when the batch finishes so the results table renders server-side — no client-side templating to keep in sync with the Jinja version.

- [ ] **Step 5: Ship templates in the wheel**

In `pyproject.toml`, under `[tool.hatch.build.targets.wheel]`, add:

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/overtone/web/templates" = "overtone/web/templates"
"src/overtone/web/static" = "overtone/web/static"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m uv run pytest tests/web -v`
Expected: PASS, all auth and batch tests.

- [ ] **Step 7: Run the whole suite**

Run: `python -m uv run pytest`
Expected: PASS.

- [ ] **Step 8: Drive the app by hand**

Run: `python -m uv run flask --app "overtone.web.app:create_app(__import__('overtone.composition.config', fromlist=['AppConfig']).AppConfig.from_env())" run --debug`

If that invocation is awkward, add `src/overtone/web/wsgi.py`:

```python
from overtone.composition.config import AppConfig
from overtone.web.app import create_app

app = create_app(AppConfig.from_env())
```

then run: `python -m uv run flask --app overtone.web.wsgi run --debug`

Log in with `admin` / `admin`, upload `data\provided_calls_batch.zip`, confirm progress updates, three rows appear, and both downloads work.

- [ ] **Step 9: Verify quality gates**

Run: `python -m uv run ruff check . ; python -m uv run black --check . ; python -m uv run mypy`
Expected: all clean.

---

### Task 10: Docker image and Render deployment

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `render.yaml`
- Create: `src/overtone/web/wsgi.py` (if not already created in Task 9)
- Modify: `README.md`

**Interfaces:**
- Consumes: `create_app`, `AppConfig.from_env` from Tasks 7–8.
- Produces: a container serving the dashboard on `$PORT`, and a Render blueprint declaring a free web service plus free Postgres.

- [ ] **Step 1: Write the Dockerfile**

```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    OVERTONE_WORKSPACE_ROOT=/tmp/overtone

COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 overtone.web.wsgi:app
```

`.dockerignore`:

```
.git
.venv
data
out
project-resource-files
docs
tests
**/__pycache__
*.pyc
.pytest_cache
.mypy_cache
.ruff_cache
```

- [ ] **Step 2: Build and run the image locally**

Run:
```powershell
docker build -t overtone .
docker run --rm -e PORT=8000 -e SECRET_KEY=local -e OVERTONE_USERNAME=admin -e OVERTONE_PASSWORD=admin -p 8000:8000 overtone
```
Expected: gunicorn starts; `http://localhost:8000/healthz` returns `ok`; login and upload work. This is the step that catches missing templates in the wheel — if templates 404, revisit Task 9 Step 5.

- [ ] **Step 3: Write the Render blueprint**

`render.yaml`:

```yaml
databases:
  - name: overtone-db
    plan: free
    databaseName: overtone
    user: overtone

services:
  - type: web
    name: overtone
    runtime: docker
    plan: free
    healthCheckPath: /healthz
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: overtone-db
          property: connectionString
      - key: SECRET_KEY
        generateValue: true
      - key: OVERTONE_USERNAME
        sync: false
      - key: OVERTONE_PASSWORD
        sync: false
      - key: OVERTONE_MAX_UPLOAD_MB
        value: "500"
      - key: OVERTONE_WORKSPACE_ROOT
        value: /tmp/overtone
```

`OVERTONE_USERNAME` and `OVERTONE_PASSWORD` are `sync: false` so they are set in the Render dashboard and never committed.

- [ ] **Step 4: Deploy**

Push the branch to GitHub, create a Render Blueprint from the repository, set the two credential env vars, and deploy. Confirm the build succeeds and `/healthz` answers.

Note: the user performs the git push. Do not push on their behalf.

- [ ] **Step 5: Verify the deployment end to end**

From a browser: open the Render URL, log in, upload `data\provided_calls_batch.zip`, watch progress reach 3 of 3, download both CSV and JSON. Confirm the CSV holds the three original `.ogg` filenames.

- [ ] **Step 6: Update the README**

Add sections covering: the live URL and how credentials are issued; local development (`docker compose up -d`, `DATABASE_URL`, `flask --app overtone.web.wsgi run --debug`); the Docker build; and a **Known limitations** section stating plainly that the free instance sleeps after 15 minutes idle with a cold start of roughly 50 seconds, that free Postgres expires 30 days from its creation date (record that date), and that batch workspaces are ephemeral so audio never outlives processing.

- [ ] **Step 7: Final verification**

Run: `python -m uv run pytest ; python -m uv run ruff check . ; python -m uv run black --check . ; python -m uv run mypy`
Expected: all clean, no skips other than Postgres when `DATABASE_URL` is unset.

---

## Risks carried forward

- **512 MB RAM on the free instance.** Fine for M2's stub predictions. It will *not* hold SenseVoice plus YAMNet under PyTorch. M5 must either use quantised ONNX Runtime models or move to a paid instance. Decide at the start of M5, not the end.
- **Ephemeral disk.** Batches survive in Postgres, but a redeploy mid-batch loses that batch's audio and leaves it `running` until the job's process dies. Acceptable for evaluation; note it.
- **Free Postgres expiry.** Thirty days from creation. Record the date and confirm it falls after the evaluation window.
