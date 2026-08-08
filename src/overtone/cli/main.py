import argparse
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from overtone.application.ports.result_serializer import ResultSerializer
from overtone.composition.config import AppConfig
from overtone.composition.container import Container, build_container
from overtone.domain.batch import Batch
from overtone.domain.exceptions import DomainError
from overtone.infrastructure.jobs.synchronous_job_runner import SynchronousJobRunner

FORMAT_CHOICES = ("csv", "json", "both")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return _analyze(args)
    except DomainError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _analyze(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory(prefix="overtone-") as workspace:
        container = _container_for(Path(workspace))
        try:
            batch = _run_batch(container, args.archive)
        finally:
            container.shutdown()
    _write_results(batch, args.out, _selected_formats(args.format), container.serializers)
    _report_summary(batch)
    return 0


def _container_for(workspace: Path) -> Container:
    """The CLI runs one batch and exits; a thread pool would be threads spawned for nothing."""
    return build_container(AppConfig(workspace_root=workspace), job_runner=SynchronousJobRunner())


def _run_batch(container: Container, archive: Path) -> Batch:
    batch_id = container.submit_batch.execute(archive)
    _report_validation(container.batches.get(batch_id))
    container.process_batch.execute(batch_id)
    return container.batches.get(batch_id)


def _report_validation(batch: Batch) -> None:
    for item in batch.items:
        if item.error_message:
            print(f"  ! {item.filename}: {item.error_message}")
    for name in batch.unmatched_files:
        print(f"  ! {name}: in the archive but not listed in the manifest, skipping")
    print(f"validated {batch.total} manifest row(s)")


def _write_results(
    batch: Batch,
    out_dir: Path,
    formats: tuple[str, ...],
    serializers: dict[str, ResultSerializer],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in formats:
        serializer = serializers[name]
        target = out_dir / f"results.{serializer.file_extension}"
        target.write_text(serializer.serialize(batch), encoding="utf-8")
        print(f"wrote {target}")


def _report_summary(batch: Batch) -> None:
    print(
        f"processed {batch.total} file(s): "
        f"{batch.succeeded_count} succeeded, {batch.failed_count} failed"
    )


def _selected_formats(requested: str) -> tuple[str, ...]:
    if requested == "both":
        return ("csv", "json")
    return (requested,)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="overtone")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="analyse an evaluation batch archive")
    analyze.add_argument("archive", type=Path, help="ZIP containing audio files and a CSV manifest")
    analyze.add_argument("--out", type=Path, required=True, help="directory for the result files")
    analyze.add_argument("--format", choices=FORMAT_CHOICES, default="both")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
