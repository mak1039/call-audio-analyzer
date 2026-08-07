# Overtone

Emotional tone and background-noise analysis for production call audio.

See [docs/PROJECT.md](docs/PROJECT.md) for the objective, output contract, constraints, and
build order.

## Status

**M1 complete — contract and pipeline, no audio intelligence yet.**

The full batch pipeline works end to end: ZIP in, validated manifest, per-item error isolation,
CSV and JSON results out. Predictions currently come from `StubAnalyzer`, which returns a fixed
`neutral` result with `confidence: 0.0`. Swapping in the real analyzer is a one-line change in
[src/overtone/composition/container.py](src/overtone/composition/container.py) and touches nothing
else — that is what the `AudioAnalyzer` port is for.

Next: M2 (Flask dashboard), M3 (deploy), M4 (auth), M5 (real analysis), M6 (validation and memo).

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

## Data handling

Production call audio is confidential.

- Audio is extracted to a temporary workspace that is deleted before results are written.
- `.gitignore` excludes every audio extension plus `project-resource-files/` and `data/*.zip`.
- Nothing leaves the machine: the M1 pipeline makes no network calls.

Put the provided calls in `data/samples/` (gitignored); `data/samples/labels.csv` holds their
labels and is committed.

## Development

```bash
uv run pytest                 # 90 tests
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
composition/     the container; the only module that knows all layers
```

The domain refuses to construct an invalid `AnalysisResult`: `confidence` must be in `[0.0, 1.0]`,
and the three `background_noise_*` fields must agree with each other. Any analyzer, present or
future, inherits that guarantee.
