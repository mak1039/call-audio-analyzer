# Overtone

Emotional tone and background-noise analysis for production call audio.

---

## 1. Objective

Build a hosted system that analyses call recordings and returns a structured
assessment of the customer's emotional state and the technical condition of the
audio. Evaluated on a hidden test set of unseen production calls.

Three things are being judged, roughly in this order:

1. **Accuracy** on unseen audio (45%)
2. **Engineering quality** — cost model, reproducibility, batch handling,
   deployment, documentation (55% combined)
3. **Judgement** — whether the approach is defensible and the limitations are
   understood

There is no training phase. Only three labelled calls are provided, which is far
too few to train or fine-tune anything. Every viable solution composes
pre-trained models and deterministic signal processing, then validates honestly.

---

## 2. Output contract

One JSON object per audio clip. This schema is fixed — treat it as an external
contract that must not drift.

| Field | Type | Values |
|---|---|---|
| `emotional_tone` | enum | `neutral` \| `satisfied` \| `frustrated` \| `upset` \| `distressed` |
| `emotional_intensity` | enum | `low` \| `medium` \| `high` |
| `background_noise_present` | bool | |
| `background_noise_type` | string | free text; `""` when absent |
| `background_noise_severity` | enum | `none` \| `low` \| `medium` \| `high` |
| `audio_quality` | enum | `clear` \| `slightly_impaired` \| `severely_impaired` |
| `speaker_overlap_present` | bool | |
| `long_silence_present` | bool | |
| `confidence` | float | `0.0` – `1.0` |

**Critical constraint from the spec:** tone, noise, and technical quality are
scored *separately*. Do not infer frustration from loudness. Do not infer
background noise from poor audio quality. The hidden set almost certainly
contains decorrelating cases — loud but calm, distorted but quiet, noisy but
clear. Independent detection paths per field, not one model guessing all nine.

---

## 3. Hard constraints

| Constraint | Value | Design consequence |
|---|---|---|
| Inference cost | ≤ $0.003 per audio minute | Rules out hosted ASR at $0.006/min. Favours local models. |
| Confidentiality | Production audio must not go to unapproved services | Local inference is the safe default; any external API must be disclosed with retention policy. |
| Reproducibility | Must run on new audio from documented setup | Pin versions, containerise, no manual steps. |
| Generalisation | Hidden test set | No tuning against the three provided calls beyond sanity checks. |
| Deadline | Friday 19:00 ET | Ship a working narrow system over a broken ambitious one. |

---

## 4. Approach

### Field routing

Each output field is produced by the cheapest component that can do it well.

| Field | Component |
|---|---|
| `emotional_tone`, `emotional_intensity` | SenseVoiceSmall SER tags + transcript sentiment cross-check |
| `background_noise_*` | YAMNet / PANNs event classification + SNR estimate |
| `audio_quality` | DSP — clipping ratio, spectral flatness, bandwidth, dropout gaps |
| `long_silence_present` | VAD → speech spans → gap threshold |
| `speaker_overlap_present` | Diarisation, or channel energy overlap if stereo |
| `confidence` | Agreement between independent signals, calibrated |

### Two approaches to compare

The spec explicitly requires comparing at least two materially different
methods. Implement both behind the same port:

- **A — Local acoustic pipeline:** SenseVoice + YAMNet + DSP rules
- **B — Multimodal LLM:** single audio-native model call returning the schema

Report both on the same validation set. Pick one for production, justify why.

### Validation set

Three labelled calls cannot produce a confusion matrix. Build a synthetic
evaluation set:

- Emotional speech from RAVDESS / CREMA-D / MELD
- Noise from ESC-50 / DEMAND / MUSAN
- Mixed at controlled SNRs, downsampled to telephony conditions (8 kHz, µ-law)

This gives known ground truth for every field, enables per-class metrics, and
lets thresholds be tuned without touching the three real calls. Use the real
calls only as a final sanity check, and say so explicitly — that is the leakage
story.

---

## 5. Architecture

Clean Architecture. Dependencies point inward only. The domain knows nothing
about Flask, PyTorch, or the filesystem.

```
domain/          ← no dependencies at all
application/     ← depends on domain
infrastructure/  ← depends on application (implements its ports)
web/             ← depends on application
composition/     ← wires everything; the only place that knows all layers
```

### Layer responsibilities

**`domain/`** — Entities, value objects, enums, domain exceptions. Pure Python,
no imports outside the standard library. `AnalysisResult`, `EmotionalTone`,
`AudioClip`, `Batch`, `BatchItem`. Frozen dataclasses. Validation lives here:
an `AnalysisResult` that violates the schema must not be constructible.

**`application/`** — Use cases and ports. One use case per file, one public
method each (`execute`). Ports are ABCs describing what the application needs
without saying how.

```
application/
  use_cases/
    submit_batch.py         SubmitBatch.execute(archive) -> BatchId
    process_batch.py        ProcessBatch.execute(batch_id) -> None
    get_batch_status.py
    export_results.py
  ports/
    audio_analyzer.py       AudioAnalyzer.analyze(clip) -> AnalysisResult
    tone_analyzer.py
    noise_analyzer.py
    quality_analyzer.py
    silence_detector.py
    overlap_detector.py
    batch_repository.py
    file_storage.py
    manifest_parser.py
```

**`infrastructure/`** — Adapters implementing ports. This is where every heavy
dependency lives, quarantined.

```
infrastructure/
  analysis/
    stub_analyzer.py            fixed values — used from day one
    composite_analyzer.py       orchestrates the per-field analyzers
    sensevoice_tone_analyzer.py
    yamnet_noise_analyzer.py
    dsp_quality_analyzer.py
    vad_silence_detector.py
    llm_analyzer.py             approach B, whole schema in one call
  persistence/
    sqlite_batch_repository.py
  storage/
    local_file_storage.py
  audio/
    loader.py                   decode, resample, normalise
```

**`web/`** — Flask blueprints, DTOs, auth, templates. Routes contain no logic.

```
web/
  blueprints/
    auth.py
    batches.py
  dto/
    batch_response.py
  auth/
    session_guard.py
  templates/
```

**`composition/`** — The container. Chooses which adapter satisfies which port.
Swapping `StubAnalyzer` for `CompositeAnalyzer` is a one-line change here and
nowhere else.

### Why this shape matters here

The `AudioAnalyzer` port is the seam that makes the whole project tractable.
Everything downstream — batch processing, the dashboard, CSV export, error
handling — depends only on that interface. You can build and deploy the entire
system against `StubAnalyzer` before understanding a single thing about audio,
then fill in the real implementation without touching anything else.

It also gives the two-approach comparison for free: approach A and approach B
are two classes implementing one port, runnable against the same harness.

### Flask specifics

- Blueprints per feature area, registered in the app factory.
- App factory pattern (`create_app(config)`) — no module-level globals.
- Flask has no built-in background worker. Batch processing must not run in the
  request thread. Use RQ + Redis, or a bounded `ThreadPoolExecutor` owned by the
  composition root for a trial-scale system. Decide once, document it.
- Heavy models load **once at startup**, not per request. Load them in the
  composition root and inject.

---

## 6. Coding standards

### Function size and shape

- **Hard ceiling: 20 lines per function.** Target 5–10.
- One level of abstraction per function. A function either orchestrates named
  steps or does one concrete thing — never both.
- If a function needs a comment to explain a section, that section is a function.
- Guard clauses over nested conditionals. Maximum two levels of indentation.
- No boolean parameters that switch behaviour — that is two functions.
- Maximum three positional parameters; beyond that, pass a value object.

```python
# no
def process(self, path, validate=True, export=False, retries=3):
    ...50 lines...

# yes
def execute(self, batch_id: BatchId) -> None:
    batch = self._repository.get(batch_id)
    self._mark_running(batch)
    for item in batch.items:
        self._process_item(item)
    self._mark_complete(batch)
```

### Naming

- Names state intent, not implementation. `detect_long_silence`, not `check_vad`.
- Booleans read as predicates: `is_`, `has_`, `contains_`.
- No abbreviations except universally understood ones (`db`, `id`, `url`).
- Adapters are named for their technology: `SenseVoiceToneAnalyzer`. Ports are
  named for their role: `ToneAnalyzer`.

### Types and data

- Type hints on every public function. `mypy --strict` on `domain/` and
  `application/` at minimum.
- Domain objects are `@dataclass(frozen=True)`. No mutable shared state.
- Enums for every constrained field — never bare strings for `emotional_tone`.
- No dicts as informal structs across layer boundaries.

### Configuration

Every threshold lives in one typed config module, never inline.

```python
@dataclass(frozen=True)
class DetectionThresholds:
    long_silence_seconds: float = 3.0
    clipping_ratio_impaired: float = 0.01
    noise_snr_db_medium: float = 15.0
```

These will be tuned against the validation set. Scattering them through the code
makes that impossible and makes the memo unwriteable.

### Errors

- Domain exceptions in `domain/exceptions.py`, not `ValueError` everywhere.
- Catch narrowly. Never bare `except:`.
- **Per-item isolation is a requirement, not a nicety.** One malformed file must
  fail alone, record its reason, and let the batch continue.

### Routes

A Flask route parses input, calls one use case, maps the result. Ten lines
maximum. If a route grows logic, that logic belongs in a use case.

### Testing

- Unit tests for domain and use cases, using fake adapters — no audio needed.
- One integration test that runs a small ZIP through the real pipeline.
- Fixtures: a clean clip, a noisy clip, a silent clip, a corrupt file.

### Tooling

`ruff` + `black` + `mypy`, all enforced in CI. Pin every dependency.

---

## 7. Build order

Each milestone is independently shippable. If time runs out, stop at the last
complete one and document the rest as next steps.

**M1 — Contract and pipeline (no intelligence).**
Domain schema, `AudioAnalyzer` port, `StubAnalyzer`, CLI that takes a ZIP,
validates the manifest, iterates with per-item error isolation, writes CSV+JSON.
No web, no auth, no audio knowledge required.

**M2 — Flask app.**
App factory, blueprints, upload endpoint, background worker, batch status,
results table, downloads. Still on the stub.

**M3 — Deploy.**
Get a public URL serving stub predictions from a real ZIP upload. Do this
*early*: `ffmpeg` binaries, model weights, and image size are what break
deployments, and they break the same way on day one as on day four — but on day
one it costs an hour instead of the submission.

**M4 — Auth.**
Session guard, single credential. Thirty lines. Deliberately last, because it
only slows down development if added earlier.

**M5 — Real analysis.**
Mechanical fields first (silence, quality, overlap — deterministic, verifiable),
then noise, then tone. Replace the stub one field at a time.

**M6 — Validation and writeups.**
Synthetic eval set, confusion matrix, per-class metrics, calibration, then the
memo, cost model, latency table, and failure modes.

---

## 8. Deliverables checklist

- [ ] Hosted dashboard, working login, stays up through evaluation
- [ ] ZIP/folder upload with CSV manifest validation
- [ ] Unmatched and missing files reported before processing
- [ ] Batch progress and completion status
- [ ] Per-file failure isolation with visible reasons
- [ ] Results view + CSV and JSON download preserving original filenames
- [ ] Repository with setup, deployment, and execution instructions
- [ ] Predictions for the three provided calls
- [ ] Technical memo — approaches tested, final architecture, why
- [ ] Validation results — metric, per-class performance, confusion matrix
- [ ] Cost analysis — per audio minute, with assumptions stated
- [ ] Latency analysis — measured, per clip and per audio minute
- [ ] Failure modes, limitations, next steps
- [ ] Disclosure of any external paid API: model, pricing, retention, data flow

---

## 9. Open questions

Pending answers; document the assumption made for each if unanswered.

- Is a third-party inference API acceptable with zero retention, or must
  inference stay self-hosted? *(Assumption: self-hosted local models.)*
- Mono mixed or dual-channel audio? Which speaker is the customer?
  *(Assumption: mono; diarise and treat the non-agent speaker as customer.)*
- Does the cost ceiling cover marginal inference only, or amortised hosting?
  *(Assumption: marginal inference; hosting reported separately.)*
- Hidden set size, clip duration, codec, sample rate?
- Field weighting within the accuracy score?
- Label provenance — single annotator or consensus? Agreement figure?
- Is `confidence` scored for calibration or informational?

---

## 10. Known limitations to state upfront

Naming these in the memo is worth more than pretending they don't exist.

- Emotion labels are subjective; without inter-annotator agreement data the
  achievable ceiling is unknown.
- SenseVoice's event vocabulary covers human-interaction sounds (laughter,
  crying, music) and does not map cleanly onto the spec's noise categories
  (office chatter, road noise, keyboard, wind) — hence a separate AED model.
- Mapping SER outputs (`ANGRY`, `SAD`, `FEARFUL`) onto the required five-value
  tone enum is a judgement call, particularly the `frustrated` / `upset` split,
  which is an intensity boundary rather than a categorical one.
- Synthetic validation audio approximates but does not reproduce real telephony
  conditions and real customer affect.
- With three labelled calls, no claim of accuracy on the real distribution is
  statistically meaningful.
