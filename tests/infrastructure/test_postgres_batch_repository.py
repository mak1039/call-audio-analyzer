import os
from collections.abc import Iterator

import pytest

from overtone.infrastructure.persistence.postgres_batch_repository import (
    PostgresBatchRepository,
)
from tests.infrastructure.repository_contract import BatchRepositoryContract, a_batch

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

    def test_create_schema_can_be_run_again_over_an_existing_schema(
        self, repository: PostgresBatchRepository
    ) -> None:
        """Every worker runs it on boot, so the second and third runs must be no-ops.

        The advisory lock inside create_schema is what makes running it *concurrently*
        safe too; that race is not reproducible as a non-flaky test.
        """
        repository.create_schema()
        repository.create_schema()

        batch = a_batch()
        repository.save(batch)
        assert repository.get(batch.batch_id) == batch
