from overtone.composition.container import Container


class _RecordingJobRunner:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def submit(self, work: object) -> None:
        raise NotImplementedError

    def shutdown(self) -> None:
        self._calls.append("job_runner.shutdown")


class _RecordingBatchRepository:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def save(self, batch: object) -> None:
        raise NotImplementedError

    def get(self, batch_id: object) -> object:
        raise NotImplementedError

    def list_recent(self, limit: int) -> tuple[object, ...]:
        raise NotImplementedError

    def close(self) -> None:
        self._calls.append("batches.close")


def test_shutdown_stops_the_job_runner_before_closing_the_repository():
    calls: list[str] = []
    container = Container(
        submit_batch=object(),  # type: ignore[arg-type]
        process_batch=object(),  # type: ignore[arg-type]
        batches=_RecordingBatchRepository(calls),  # type: ignore[arg-type]
        serializers={},
        job_runner=_RecordingJobRunner(calls),  # type: ignore[arg-type]
    )

    container.shutdown()

    assert calls == ["job_runner.shutdown", "batches.close"]
