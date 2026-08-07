from dataclasses import dataclass

from overtone.application.ports.batch_repository import BatchRepository
from overtone.application.ports.result_serializer import ResultSerializer
from overtone.application.use_cases.process_batch import ProcessBatch
from overtone.application.use_cases.submit_batch import SubmitBatch
from overtone.composition.config import AppConfig
from overtone.infrastructure.analysis.stub_analyzer import StubAnalyzer
from overtone.infrastructure.archive.zip_archive_extractor import ZipArchiveExtractor
from overtone.infrastructure.export.csv_result_serializer import CsvResultSerializer
from overtone.infrastructure.export.json_result_serializer import JsonResultSerializer
from overtone.infrastructure.manifest.csv_manifest_parser import CsvManifestParser
from overtone.infrastructure.persistence.in_memory_batch_repository import (
    InMemoryBatchRepository,
)
from overtone.infrastructure.storage.local_file_storage import LocalFileStorage
from overtone.infrastructure.time.system_clock import SystemClock


@dataclass(frozen=True)
class Container:
    submit_batch: SubmitBatch
    process_batch: ProcessBatch
    batches: BatchRepository
    serializers: dict[str, ResultSerializer]


def build_container(config: AppConfig) -> Container:
    """The one place that knows every layer.

    Replacing StubAnalyzer with the real pipeline is a single-line change here and
    nowhere else — that is the whole point of the AudioAnalyzer port.
    """
    analyzer = StubAnalyzer()
    storage = LocalFileStorage(config.workspace_root)
    repository = InMemoryBatchRepository()
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
    )
