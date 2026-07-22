# Atlas Project Roadmap and Version Audit

Updated baseline: **Alpha 0.9.4.8**  
Latest full audit: **2026-07-22 — regression-triggered**

## Operating rules

- User-requested product behaviour has priority over test-count targets.
- Validation is risk-based rather than mechanically fixed:
  - low-risk documentation or isolated rules: about 40–100 targeted checks;
  - ordinary feature changes: about 80–180 checks;
  - scheduler, persistence, queue schema, cache, deployment and map-core changes: about 180–300 checks;
  - major/minor releases, scheduled full audits and migrations may use the complete matrix up to about 500 checks per relevant gate.
- Every release must review watchdog speed, polling, duplicate scheduling, path-scoped CI, repeated checks and total validation time. A change is required only when evidence shows a safe improvement.
- Every three completed patch releases require a full framework audit. The regression-triggered audit at Alpha 0.9.4.8 resets the next scheduled audit to Alpha 0.9.4.14.
- A task is complete only after implementation, automated validation and, where applicable, separate public-deployment and physical-device verification.
- Project-side AI improvements mean better evidence structures, confidence, conflict detection, prioritisation and recovery logic. They are not described as autonomous model training.

## Completed release line

### Alpha 0.9.4.3 — navigation geometry and interaction

- Bottom navigation centring and safe-area placement repaired.
- Left rail made fully visible instead of being embedded into the screen edge.
- Frosted navigation media and closed-panel inert behaviour added.
- Returning from filter, route or progress no longer blocks the left rail.

### Alpha 0.9.4.4 — navigation medium and scan recovery

- Left-rail liquid medium recovery repaired on iPad and other profiles.
- Known OpenCV media-open failure classified and safely retried.

### Alpha 0.9.4.5 — heartbeat self-healing and full audit

- Durable queue state made authoritative over stale runtime heartbeats.
- Duplicate monitor controller removed.
- Five-item then extended serial queue supervision added.
- Full framework audit completed.

### Alpha 0.9.4.6 — marker and icon redesign

- Settings icon simplified to a radial-eight SVG design.
- Map pin geometry rebuilt with a longer continuous teardrop tail.
- Marker selection changed to scale-only feedback: 1.28×, 190 ms, stable tip anchor, zero selection decoration layers.

### Alpha 0.9.4.7 — unified data and evidence centre

- Database status and evidence reconstruction combined under one settings shell.
- Production scan status and local evidence storage retain separate privacy boundaries.
- Eleven-item serial scan support and queue schema recovery retained.

## Alpha 0.9.4.8 — active work

### 3430 个点位奖励证据管线

- [x] Define four evidence states: official confirmed, multi-source confirmed, high-confidence inference and unresolved.
- [x] Define the reward record JSON schema.
- [x] Define standard Simplified Chinese terminology and translation rules.
- [x] Initialise a 3430-location coverage index without fabricating rewards.
- [x] Add a reward evidence contract matrix.
- [ ] Generate a stable mapping from every location ID to one reward record.
- [ ] Research and import the first reviewable official and multi-source reward batch.
- [ ] Add duplicate, source-locator, terminology and conflict reports for every batch.
- [ ] Display reward status, confidence and evidence summary in location details.
- [ ] Expand verified coverage gradually; unresolved locations must remain explicitly unresolved.

### Full-audit status

- [x] Add a dedicated Alpha 0.9.4.8 full-project audit executable.
- [x] Check release assets, duplicate owners, reward contracts and obsolete known controllers.
- [x] Protect locked reward records from automatic overwrite.
- [x] Run a regression-triggered full audit on 2026-07-22.
- [x] Record the audit report at `data/audits/full-audit-0948-regression-20260722.json`.
- [ ] Repair the critical scan-order regression before declaring the release stable.
- [ ] Regenerate scan-system health evidence for release 0.9.4.8 and the current bug dictionary.
- [ ] Review deletion candidates and delete only files proven to have no owner, references or compatibility role.
- [ ] Record public GitHub Pages verification and separate physical iPad/desktop verification.

## Critical regression found on 2026-07-22

Accepted behaviour requires the earliest unresolved item to own queue order: **P33 → P34 → P35**, with at most one active task.

Observed repository evidence shows:

- durable queue: P33 remains `failed` at attempt 3;
- runtime projection: P34 is `running`;
- `tools/run_scan_with_auto_recovery.py` on `main` selects only `pending`/`queued` items for the next projection and lacks the previously accepted failed-head preflight;
- `data/batch-analysis/scan-system-health.json` is stale and still reports release 0.9.4.7 with dictionary version 2026.07.19.5.

This is a clear accepted-feature regression. P34/P35 output must not be treated as authoritative completion evidence until durable order is reconciled.

## Next three releases

### Alpha 0.9.4.9 — restore scan authority and validation speed

Priority S:

- Restore strict earliest-unresolved ownership in the active `main` orchestration path.
- Apply dictionary-driven effective attempt limits: safe known transport failures may use up to 5 attempts; unknown, identity, authorisation and privacy failures remain capped at 3.
- Reconcile P33 durable state before allowing P34/P35 to advance.
- Keep maximum concurrency at one and prove there is no later-item bypass.
- Land risk-based test budgets and path-scoped CI; runtime heartbeat-only commits must not run unrelated UI, reward or full-audit matrices.
- Regenerate current scan-system health and audit evidence.

### Alpha 0.9.4.10 — first verified reward batch and interaction evidence

- Import the first reviewable reward records with source locators.
- Add reward summaries, confidence labels and conflict states to location details.
- Report official, multi-source, inferred, unresolved and conflict counts.
- Add performance baselines for map pan, zoom, marker selection and panel transitions.
- Continue Apple-inspired frosted UI standardisation only where it does not delay core requirements.

### Alpha 0.9.4.11 — coverage expansion and deployment verification

- Expand reward coverage in bounded, reviewable batches.
- Complete public GitHub Pages verification records.
- Complete separate physical iPad Safari and desktop verification records.
- Audit workflow noise, heartbeat commit frequency and report freshness.
- Reassess the ultra-HD original map gate without marking it complete prematurely.

## Ultra-high-definition original map stage gate

Status: **not complete**.

Completion requires:

1. final original ultra-HD map base;
2. coordinate and overlay calibration;
3. responsive mobile and desktop rendering;
4. compatibility with locations, routes, progress, favourites, search, filters, panels, evidence and PWA caching;
5. physical iPad Safari and desktop verification.

Tasks that depend on final geometry remain queued until this gate is complete. They remain scheduled but must not be activated or reported as complete early.

## Persistent quality requirements

- Preserve one active scan/download at a time.
- Never allow a later queue item to bypass the earliest unresolved item.
- Never broaden creator authorisation automatically.
- Never retain original video or frame pixels in the public repository.
- Never present inferred rewards as official facts.
- Keep source locators, confidence and conflicts auditable.
- Keep high-definition rendering while providing bounded performance fallbacks.
- Record public deployment and physical-device verification separately from CI.
- Each release must report watchdog/test review results: selected risk tier, relevant check count, skipped unrelated gates, runtime and any proven quality or speed change.
