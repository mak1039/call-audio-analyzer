# Overtone

Emotional tone and background-noise analysis for production call audio.

See [docs/PROJECT.md](docs/PROJECT.md) for the objective, output contract, constraints, and
build order.

## Status

**M2, M3 and M4 complete — hosted, authenticated dashboard, containerised and ready to deploy.**

The full batch pipeline works end to end, now behind a Flask dashboard: log in, upload a ZIP,
watch progress converge, download CSV and JSON results. Predictions still come from
`StubAnalyzer`, which returns a fixed `neutral` result with `confidence: 0.0`. Swapping in the
real analyzer is a one-line change in
[src/overtone/composition/container.py](src/overtone/composition/container.py) and touches nothing
else — that is what the `AudioAnalyzer` port is for.

Batches persist to Postgres when `DATABASE_URL` is set (production) and fall back to an in-memory
repository otherwise (local smoke testing without a database). The app is packaged as a Docker
image (see [Docker](#docker) below) with a `render.yaml` blueprint for a free Render web service
plus free Postgres.

**Live URL:** not yet deployed — the project owner pushes and deploys this branch from the Render
blueprint; this line will be updated with the Render URL once that happens. Credentials
(`OVERTONE_USERNAME` / `OVERTONE_PASSWORD`) are set as `sync: false` secrets in the Render
dashboard, never committed, and are shared with evaluators out of band.

Next: M5 (real analysis), M6 (validation and memo).

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Usage

```bash
uv run overtone analyze <batch.zip> --out <dir> [--format csv|json|both]
```

The archive must contain audio files and exactly one CSV manifest. A wrapper directory is
flattened automatically, so both of these work:

```
evaluation_batch.zip           evaluation_batch.zip
  call_001.ogg                   evaluation_batch/
  call_002.mp3                     call_001.ogg
  labels.csv                       labels.csv
```

The manifest needs a `name` column holding the exact audio filename. `result_json` is optional and
holds the expected label when the batch is labelled; it is never fed to the analyzer.

```csv
name,result_json
call_001.ogg,"{""emotional_tone"":""upset"",...}"
call_002.ogg,
```

Output is written to `<dir>/results.csv` and `<dir>/results.json`, preserving original filenames.

### Batch validation

Mismatches are reported before processing and never abort the batch:

- a manifest row with no matching file fails **that item only**, with the reason in the output
- a file with no manifest row is reported as unmatched and skipped
- a file the analyzer chokes on fails alone; the rest of the batch continues

A structurally broken batch — unreadable archive, no manifest, more than one manifest — exits
non-zero with a message and no traceback.

## Web dashboard

### Local development

Run Postgres locally with the provided compose file, point the app at it, and run the Flask dev
server with reload. **The moment `DATABASE_URL` is set, `AppConfig.from_env()` refuses to start
unless `SECRET_KEY`, `OVERTONE_USERNAME`, and `OVERTONE_PASSWORD` are also set to non-default
values** (see [Environment variables](#environment-variables)) — so all four must be exported
together:

```bash
docker compose up -d                          # postgres:16-alpine on localhost:5432
export DATABASE_URL=postgresql://overtone:overtone@localhost:5432/overtone
export SECRET_KEY=local-dev-secret
export OVERTONE_USERNAME=devuser
export OVERTONE_PASSWORD=devpassword
flask --app overtone.web.wsgi run --debug
```

Note that `admin` / `admin` are themselves the compiled-in defaults (`DEFAULT_USERNAME` /
`DEFAULT_PASSWORD` in `src/overtone/composition/config.py`), so re-exporting
`OVERTONE_USERNAME=admin` / `OVERTONE_PASSWORD=admin` alongside `DATABASE_URL` still trips the
guard — pick values that actually differ from the defaults, as above.

Without `DATABASE_URL` set at all, the app falls back to an in-memory batch repository and the
`admin` / `admin` dev-default credentials apply automatically — fine for poking at routes without
Postgres, but the in-memory state does not survive a restart and (see
[Known limitations](#known-limitations)) is not safe to combine with multiple worker processes.
The two modes are mutually exclusive: either leave `DATABASE_URL` unset and get the defaults for
free, or set it and supply all three secrets yourself — there is no combination where
`DATABASE_URL` is set and the defaults still work.

### Docker

Build and run the image exactly as it will run on Render:

```bash
docker build -t overtone .
docker run --rm -e PORT=8000 -e SECRET_KEY=local -e OVERTONE_USERNAME=admin \
  -e OVERTONE_PASSWORD=admin -p 8000:8000 overtone
```

This was verified locally: `docker build` completes (only the 13 runtime dependencies are
installed — `pytest`, `ruff`, `black`, and `mypy` are excluded by `--no-dev`), gunicorn starts with
two workers, `GET /healthz` returns `ok`, `/login` and its stylesheet/script under `/static/`
serve correctly (confirming `pyproject.toml`'s `force-include` ships `web/templates` and
`web/static` inside the installed wheel), and a login + upload of
`data/provided_calls_batch.zip` completes with all three `.ogg` files processed and downloadable
as CSV and JSON.

The image was also run against the compose Postgres (`DATABASE_URL` pointed at
`host.docker.internal:5432`, with `SECRET_KEY`/`OVERTONE_USERNAME`/`OVERTONE_PASSWORD` all set to
non-default values) to confirm the production-shaped path works end to end, not just the
in-memory fallback.

The container needs no persistent volume: uploaded audio is extracted to
`OVERTONE_WORKSPACE_ROOT` and deleted once the batch finishes — or immediately, if the batch is
rejected before processing starts.

### Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `PORT` | yes (Render sets it) | Port gunicorn binds to. |
| `DATABASE_URL` | production | Postgres connection string. Unset → in-memory repository. |
| `SECRET_KEY` | see below | Flask session signing key. |
| `OVERTONE_USERNAME` | see below | Dashboard login username. |
| `OVERTONE_PASSWORD` | see below | Dashboard login password. Must be high-entropy — see below. |
| `OVERTONE_MAX_UPLOAD_MB` | no (default `500`) | Upload size cap. |
| `OVERTONE_WORKSPACE_ROOT` | no (default `/tmp/overtone`) | Scratch directory for extracted audio. |

**The app refuses to start if `DATABASE_URL` is set while `SECRET_KEY`, `OVERTONE_USERNAME`, or
`OVERTONE_PASSWORD` are still at their development defaults** (`dev-secret-not-for-production`,
`admin`, `admin`). `AppConfig.from_env()` raises `InsecureConfigurationError` in that case, which
crashes every gunicorn worker on boot — verified locally: the container never becomes healthy and
the logs show the exception repeating per worker. This is deliberate: it is impossible to point a
real database at the dashboard while leaving the default credentials in place. `render.yaml` sets
`SECRET_KEY` via `generateValue: true` and leaves `OVERTONE_USERNAME` / `OVERTONE_PASSWORD` as
`sync: false`, so they must be set by hand in the Render dashboard before the service can boot.

**`OVERTONE_PASSWORD` must be a generated high-entropy value** — for example
`python -c "import secrets; print(secrets.token_urlsafe(24))"` — not a memorable phrase, and not
reused from anywhere else. The startup guard only rejects the literal default `admin`; it cannot
judge strength, and it is the only thing standing between the internet and the dashboard. There is
no rate limiting or lockout on `/login` (see [Known limitations](#known-limitations)), so a weak
password can be guessed at whatever rate the free instance will serve. `SECRET_KEY` should be
generated the same way; `render.yaml` already does that for you via `generateValue: true`.

### Known limitations

- **Cold starts.** The Render free web service instance sleeps after 15 minutes of inactivity.
  The first request after a sleep pays a cold-start penalty of roughly 50 seconds while the
  instance spins back up.
- **Free Postgres expiry.** Render's free Postgres plan expires 30 days after its creation date.
  Record the creation date once the blueprint is deployed and confirm it falls after the
  evaluation window; a new database (and a fresh `DATABASE_URL`) will be needed after that.
- **Ephemeral audio.** Batch workspaces live under `OVERTONE_WORKSPACE_ROOT` on local, non-persistent
  disk. Audio never outlives processing — it is deleted as soon as a batch finishes, and at once
  if the batch is rejected before processing starts — and a redeploy or restart mid-batch loses
  that batch's audio, leaving it stuck `running` until the process is replaced. Batch metadata and results survive in Postgres; the source audio does not.
- **512 MB RAM on the free instance.** Sufficient for M2's stub predictions. It will not hold
  SenseVoice plus YAMNet under PyTorch — M5 must move to quantised ONNX Runtime models or a paid
  instance.
- **No login rate limiting or lockout.** `/login` accepts unlimited attempts at whatever rate
  the instance will serve, and Render's free tier puts nothing in front of it. The only defence is
  the strength of `OVERTONE_PASSWORD` (see [Environment variables](#environment-variables)).
  Per-IP throttling is the next step if this moves beyond a trial; in-app throttling was left out
  deliberately because it needs state shared across gunicorn workers, which means another
  dependency for a trial deployment.
- **Multiple gunicorn workers require `DATABASE_URL`.** The in-memory batch repository is
  per-process; running with two gunicorn workers and no database means roughly half of status
  polls and downloads for a given batch will 404, depending on which worker handles the request.
  Production always sets `DATABASE_URL` (see `render.yaml`), so this only affects ad hoc local
  testing without Postgres.

## Data handling

Production call audio is confidential.

- Audio is extracted to a per-batch workspace that is deleted on every exit path: when the batch
  finishes, when processing dies part-way, and when the batch is rejected before processing even
  starts (unreadable archive, no manifest, more than one manifest). Only the analysis results
  outlive the audio; the CLI additionally puts the whole workspace inside a temporary directory.
- `.gitignore` excludes every audio extension plus `project-resource-files/` and `data/*.zip`.
- Nothing leaves the machine: the M1 pipeline makes no network calls.

Put the provided calls in `data/samples/` (gitignored); `data/samples/labels.csv` holds their
labels and is committed.

## Development

```bash
uv run pytest                 # 147 passed, 9 skipped (skips are Postgres tests, gated on DATABASE_URL)
uv run ruff check .
uv run black --check .
uv run mypy                   # strict on domain/ and application/
```

## Architecture

Clean Architecture; dependencies point inward only.

```
domain/          entities, enums, validation — stdlib only
application/     use cases and ports (ABCs)
infrastructure/  adapters — every heavy dependency lives here
cli/             argument parsing, output formatting
web/             Flask app factory, blueprints, templates, static assets
composition/     the container; the only module that knows all layers
```

The domain refuses to construct an invalid `AnalysisResult`: `confidence` must be in `[0.0, 1.0]`,
and the three `background_noise_*` fields must agree with each other. Any analyzer, present or
future, inherits that guarantee.
