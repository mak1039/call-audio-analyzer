import os
from collections.abc import Iterator

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
    def repository(self) -> Iterator[PostgresBatchRepository]:
        assert DATABASE_URL is not None
        repository = PostgresBatchRepository(DATABASE_URL)
        repository.create_schema()
        repository.delete_all()
        yield repository
        repository.close()
