# M2 — Hosted Dashboard, Postgres, Auth, Deploy

Design spec. Written 2026-08-07. Supersedes the M2/M3/M4 split in
[PROJECT.md](../../PROJECT.md) §7, which this milestone merges.

## Context

M1 delivered the full batch pipeline with no audio intelligence: domain contract,
`AudioAnalyzer` port, `StubAnalyzer`, ZIP extraction, manifest validation, per-item error
isolation, CSV/JSON export, and a CLI. 90 tests pass; ruff, black, and `mypy --strict` on
`domain/` and `application/` are clean.

The brief's Definition of Success is "a hosted, testable system — not merely a local demo",
weighted 10% on the dashboard alone. M2 turns the M1 pipeline into that system: a logged-in web
app the evaluator can upload a batch to, watch process, review, and download from — deployed to a
public URL.

Predictions stay stubbed throughout. Replacing `StubAnalyzer` is M5 and is a one-line change in
the composition root.

## Decisions

| Decision | Choice | Reasoning |
|---|---|---|
| Background work | In-process `ThreadPoolExecutor` | No Redis service to fund or keep alive. Batch state lives in Postgres, so any process can serve status polls regardless of which one runs the job. |
| Persistence | Postgres via psycopg3, raw SQL | One aggregate, one table. An ORM would duplicate the domain model for no gain. `schema.sql` applied at startup; no migration tool until there is a second table. |
| Auth | Moved from M4 into M2 | ~30 lines. Building it now means the deploy is never a publicly writable upload endpoint for confidential audio. |
| Front end | Jinja + vanilla JS polling | No build step, nothing extra to break in the image. A batch upload screen does not need a framework. |
| Deploy | Folded in from M3 | PROJECT.md's own argument: deployment breaks the same way on day one as day four, and day one costs an hour instead of the submission. |
| Hosting tier | Render free | Accepted with the limitations documented below. |

### Free-tier consequences, accepted deliberately

- **The web service sleeps after 15 minutes idle**, cold-starting in roughly 50 seconds. Free
  instances get 750 hours/month, so a keep-alive pinger would exhaust the quota and is not a fix.
  Mitigation is honesty: a `/healthz` endpoint, and a line in the README and submission note
  telling the evaluator the first request may take about a minute.
- **Free Postgres expires 30 days after creation.** Record the creation date in the README and
  note the expiry sits after the evaluation period.
- **512 MB RAM.** Ample for M2, which serves stub predictions. It is *not* enough for M5's
  original plan of SenseVoice plus YAMNet under PyTorch. This is a real constraint that M5 must
  design around — quantised ONNX Runtime models, or a tier upgrade at that point. Flagged here so
  it is not discovered late; it does not block M2.

## Domain changes

Two additions, both small and both needed by the web layer:

- `Batch.created_at: datetime` — so the evaluator can find a batch again after losing the URL.
  Stored, and used to order the recent-batches list. It is passed *into* `Batch.create` rather
  than read from the clock inside it: the domain stays pure and ordering tests stay deterministic.
  `SubmitBatch` obtains it from a `Clock` port (`Clock.now() -> datetime`, UTC), with a
  `SystemClock` adapter and a fixed-time fake in tests.
- `BatchStatus.FAILED` — for a job that dies outright (OOM, unhandled adapter error). Distinct
  from a completed batch containing failed items, which is the normal, already-handled case.
  Without it a crashed batch shows "running" forever.

Everything else in `domain/` is untouched.

## New ports

- `JobRunner.submit(work: Callable[[], None]) -> None` — keeps threading out of the use cases and
  makes route tests deterministic via a synchronous fake.
- `Clock.now() -> datetime` — UTC, injected so `created_at` is deterministic under test.
- `BatchRepository.list_recent(limit: int) -> tuple[Batch, ...]` — added to the existing port.

## New adapters

- `PostgresBatchRepository` — psycopg3, one `batches` table. Columns: `batch_id` (PK), `status`,
  `created_at`, `unmatched_files` (JSONB), `items` (JSONB). Items serialise as JSON rather than a
  child table because they are only ever read and written as a whole batch, never queried
  individually.
- `ThreadPoolJobRunner` — bounded executor owned by the composition root, shut down cleanly on app
  teardown.
- `SynchronousJobRunner` — test fake; runs the callable inline.

## Web layer

```
web/
  app.py                create_app(config)
  blueprints/
    auth.py             GET/POST /login, POST /logout
    batches.py          GET /, POST /batches, GET /batches/<id>,
                        GET /batches/<id>/status.json, GET /batches/<id>/download.<fmt>
  auth/session_guard.py login_required decorator
  templates/            base, login, upload, batch_detail
  static/               one small poll.js, one stylesheet
```

Routes parse input, call one use case, and map the result — ten lines each. Any logic that grows
in a route belongs in a use case.

### Data flow

1. `POST /batches` with the uploaded ZIP runs `SubmitBatch` **synchronously**. Validation is fast
   and its failures belong on the upload page, not on a status endpoint.
2. On success the route hands `ProcessBatch.execute(batch_id)` to the `JobRunner` and redirects to
   `/batches/<id>`.
3. That page polls `/batches/<id>/status.json` once a second, rendering progress from
   `total` / `succeeded_count` / `failed_count`.
4. On completion the page swaps in the results table and enables the download links, which reuse
   the M1 serializers unchanged.

### Auth

One username and password from environment variables, compared with `hmac.compare_digest`, held
in a signed session cookie. `login_required` guards every batch route. No user model, no
registration, no password reset — there is exactly one account and it is issued to the evaluator.

## Error handling

- **Structural batch failures** (unreadable ZIP, no manifest, more than one manifest) re-render
  the upload page with the reason and HTTP 400.
- **Per-item failures** already isolate correctly from M1; they surface as a flagged row carrying
  its own message.
- **Oversized uploads** are capped by `MAX_CONTENT_LENGTH` with a 413 handler that explains the
  limit rather than showing a stack trace.
- **A crashed job** marks the batch `FAILED` in a `finally`, so the page stops spinning and says
  what happened.
- **Audio is deleted in a `finally`** once processing ends, whether it succeeded or not. The
  container must not retain customer audio.

## Concurrency

`ProcessBatch` saves the whole batch after each item. One job owns one batch and is the only
writer for it, so last-write-wins is correct here and no row locking is needed. Gunicorn runs a
small number of workers; the job executes in whichever process accepted the upload, and status
polls served by any process read the same Postgres row.

The uploaded audio lives on that container's local disk, so a job and its files are always
co-located. This is why the workspace is not shared storage and does not need to be.

## Testing

- **Repository contract suite** run against both `InMemoryBatchRepository` and
  `PostgresBatchRepository`, so the two cannot drift. Postgres tests skip when `DATABASE_URL` is
  unset, keeping the suite runnable without Docker.
- **Route tests** use the Flask test client with the in-memory repository and `SynchronousJobRunner`
  — deterministic, no sleeping, no threads.
- **Auth tests** assert every batch route redirects when unauthenticated.
- **One integration test** uploads a real ZIP through the test client and downloads the CSV.
- All 90 existing tests keep passing.

## Deployment

- `docker-compose.yml` — Postgres 16 for local development.
- `Dockerfile` — python:3.12-slim, uv for dependency install, gunicorn as the server.
- `render.yaml` — free web service plus free managed Postgres, with `DATABASE_URL` wired from the
  database and `SECRET_KEY` generated.
- Environment: `DATABASE_URL`, `SECRET_KEY`, `OVERTONE_USERNAME`, `OVERTONE_PASSWORD`,
  `OVERTONE_WORKSPACE_ROOT`, `OVERTONE_MAX_UPLOAD_MB`.
- `/healthz` returns 200 without touching the database, so a sleeping instance can be woken
  cheaply.

## Out of scope

Real audio analysis (M5), the synthetic validation set and all writeups (M6), multi-user accounts,
batch deletion, and resumable uploads.

## Definition of done

The evaluator opens the public URL, logs in with issued credentials, uploads a ZIP of audio plus a
CSV manifest, watches progress, sees missing and unmatched files reported distinctly, reviews
per-file predictions including failures with reasons, and downloads CSV and JSON preserving
original filenames — without touching a command line.
