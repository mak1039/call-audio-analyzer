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
