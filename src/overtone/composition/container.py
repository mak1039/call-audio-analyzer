from dataclasses import dataclass

from overtone.application.ports.batch_repository import BatchRepository
from overtone.application.ports.job_runner import JobRunner
from overtone.application.ports.result_serializer import ResultSerializer
from overtone.application.use_cases.process_batch import ProcessBatch
from overtone.application.use_cases.submit_batch import SubmitBatch
from overtone.composition.config import AppConfig
from overtone.infrastructure.analysis.stub_analyzer import StubAnalyzer
from overtone.infrastructure.archive.zip_archive_extractor import ZipArchiveExtractor
from overtone.infrastructure.export.csv_result_serializer import CsvResultSerializer
from overtone.infrastructure.export.json_result_serializer import JsonResultSerializer
from overtone.infrastructure.jobs.thread_pool_job_runner import ThreadPoolJobRunner
from overtone.infrastructure.manifest.csv_manifest_parser import CsvManifestParser
from overtone.infrastructure.persistence.in_memory_batch_repository import (
    InMemoryBatchRepository,
)
from overtone.infrastructure.persistence.postgres_batch_repository import (
    PostgresBatchRepository,
)
from overtone.infrastructure.storage.local_file_storage import LocalFileStorage
from overtone.infrastructure.time.system_clock import SystemClock


@dataclass(frozen=True)
class Container:
    submit_batch: SubmitBatch
    process_batch: ProcessBatch
    batches: BatchRepository
    serializers: dict[str, ResultSerializer]
    job_runner: JobRunner

    def shutdown(self) -> None:
        """Stop accepting/finish in-flight work, then release held resources.

        Order matters: the job runner may still be using the repository, so it must
        finish before the repository's connections are closed.
        """
        self.job_runner.shutdown()
        self.batches.close()


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
