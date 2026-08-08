import logging

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


def test_thread_pool_runner_logs_failures_with_traceback(caplog) -> None:
    caplog.set_level(logging.ERROR)
    runner = ThreadPoolJobRunner(max_workers=1)

    def explode() -> None:
        raise RuntimeError("test failure")

    runner.submit(explode)
    runner.shutdown()

    records = [
        r for r in caplog.records if r.name == "overtone.infrastructure.jobs.thread_pool_job_runner"
    ]
    assert len(records) == 1
    assert records[0].levelname == "ERROR"
    assert "background job failed" in records[0].message
    assert records[0].exc_info is not None
