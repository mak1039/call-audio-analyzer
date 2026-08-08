import pytest

from overtone.infrastructure.persistence.in_memory_batch_repository import (
    InMemoryBatchRepository,
)
from tests.infrastructure.repository_contract import BatchRepositoryContract


class TestInMemoryBatchRepository(BatchRepositoryContract):
    @pytest.fixture
    def repository(self) -> InMemoryBatchRepository:
        return InMemoryBatchRepository()
