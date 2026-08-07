CREATE TABLE IF NOT EXISTS batches (
    batch_id        TEXT PRIMARY KEY,
    status          TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    unmatched_files JSONB NOT NULL,
    items           JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS batches_created_at_idx ON batches (created_at DESC);
