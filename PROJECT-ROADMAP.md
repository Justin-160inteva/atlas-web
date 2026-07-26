# Atlas Project Roadmap and Version Audit

Updated baseline: **Alpha 0.9.4.8**  
Latest full audit: **2026-07-26 — regression-triggered**

## Operating rules

- User-requested product behaviour has priority over test-count targets.
- Validation is risk-based:
  - low-risk documentation or isolated rules: about 40–100 targeted checks;
  - ordinary feature changes: about 80–180 checks;
  - scheduler, persistence, queue schema, cache, deployment and map-core changes: about 180–300 checks;
  - major/minor releases, scheduled full audits and migrations may use complete relevant matrices up to about 500 checks per gate.
- Every release must review watchdog speed, polling, duplicate scheduling, path-scoped CI, repeated checks and total validation time.
- Regular full audits occur every three patch releases. Regression-triggered audits do not advance the regular counter; the next scheduled audit remains **Alpha 0.9.4.11**.
- A task is complete only after implementation, automated validation and, where applicable, separate public-deployment and physical-device verification.
- Project-side AI improvements mean better evidence structures, confidence, conflict detection, prioritisation and recovery logic; they are not described as autonomous model training.

## Completed release line

### Alpha 0.9.4.3 — navigation geometry and interaction

- Bottom navigation centring and safe-area placement repaired.
- Left rail made fully visible.
- Frosted navigation media and closed-panel inert behaviour added.
- Returning from filter, route or progress no longer blocks the left rail.

### Alpha 0.9.4.4 — navigation medium and scan recovery

- Left-rail liquid medium recovery repaired on iPad and other profiles.
- Known OpenCV media-open failure classified and safely retried.

### Alpha 0.9.4.5 — heartbeat self-healing and full audit

- Durable queue state made authoritative over stale runtime heartbeats.
- Duplicate monitor controller removed.
- Serial queue supervision added.
- Full framework audit completed.

### Alpha 0.9.4.6 — marker and icon redesign

- Settings icon simplified to a radial-eight SVG design.
- Map pin geometry rebuilt with a longer continuous teardrop tail.
- Marker selection changed to scale-only feedback: 1.28×, 190 ms, stable tip anchor, zero selection decoration layers.

### Alpha 0.9.4.7 — unified data and evidence centre

- Database status and evidence reconstruction combined under one settings shell.
- Production scan status and local evidence storage retain separate privacy boundaries.
- Serial scan support and queue schema recovery retained.

## Alpha 0.9.4.8 — regression blocked

### 3430 个点位奖励证据管线

- [x] Four evidence states: official confirmed, multi-source confirmed, high-confidence inference and unresolved.
- [x] Reward record JSON schema.
- [x] Standard Simplified Chinese terminology and translation rules.
- [x] 3430-location unresolved coverage index without fabricated rewards.
- [x] Reward evidence contract matrix.
- [ ] Stable mapping from every location ID to one reward record.
- [ ] First reviewable official and multi-source reward batch.
- [ ] Duplicate, source-locator, terminology and conflict reports for every batch.
- [ ] Reward status, confidence and evidence summary in location details.
- [ ] Gradual verified coverage expansion; unresolved locations remain explicit.

### Audit and verification status

- [x] Dedicated Alpha 0.9.4.8 audit executable.
- [x] Regression-triggered audit on 2026-07-22.
- [x] Second regression-triggered audit on 2026-07-26.
- [x] Audit report: `data/audits/full-audit-0948-regression-20260726.json`.
- [ ] Restore one authoritative scan batch identity.
- [ ] Restore bounded recovery safety policy.
- [ ] Restore strict earliest-unresolved queue ownership.
- [ ] Regenerate current scan-system health evidence.
- [ ] Prove dynamic validation budgets and path-scoped CI on `main`.
- [ ] Public GitHub Pages verification.
- [ ] Physical iPad Safari and desktop verification.

## Critical regressions confirmed on 2026-07-26

### 1. Batch authority mismatch

The active manifest identifies **final single episode P80**, with `maximumQueueItems=1` and `strict-p080-only`, while the referenced durable queue contains **P20–P22 in 山城**. Status and runtime report P80 complete. Manifest, queue, status and runtime therefore no longer represent one authoritative batch.

### 2. Recovery safety policy regression

The active manifest currently allows:

- `maxAttemptsPerItem=20`;
- `retryTechnicalFailuresUntilResolved=true`;
- `blockUnknownOrIdentityFailures=false`;
- `neverModifySourceCodeAutomatically=false`.

This contradicts accepted behaviour: known transient failures must remain bounded, unknown/identity/authorization/privacy failures must stop safely, and executable source must never be modified automatically.

### 3. Queue scope mismatch

The manifest permits one P80 item, but the queue contains three P20–P22 items. No new scan result should be treated as authoritative until scope and identity are reconciled.

## Next three releases

### Alpha 0.9.4.9 — restore scan authority and validation speed

Priority S:

- Restore one batch identity across manifest, queue, status, runtime and monitor.
- Restore strict earliest-unresolved ownership and one active task maximum.
- Restore dictionary-driven bounded retries: safe known transport failures up to 5; unknown, identity, authorization and privacy failures capped at 3 and blocked safely.
- Restore `neverModifyExecutableSourceAutomatically=true`.
- Land risk-based test budgets and path-scoped CI; heartbeat-only commits must not run unrelated UI, reward or full-audit matrices.
- Regenerate current health and audit evidence.

### Alpha 0.9.4.10 — first verified reward batch and interaction evidence

- Import the first reviewable reward records with source locators.
- Add reward summaries, confidence labels and conflict states to location details.
- Report official, multi-source, inferred, unresolved and conflict counts.
- Add performance baselines for map pan, zoom, marker selection and panel transitions.
- Continue Apple-inspired frosted UI standardisation only where it does not delay core requirements.

### Alpha 0.9.4.11 — coverage expansion and scheduled audit

- Expand reward coverage in bounded, reviewable batches.
- Complete public GitHub Pages verification records.
- Complete separate physical iPad Safari and desktop verification records.
- Audit workflow noise, heartbeat commit frequency and report freshness.
- Run the scheduled full audit if this version is reached.
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
- Keep manifest, queue, status, runtime and monitor on one batch identity.
- Never broaden creator authorisation automatically.
- Never retain original video or frame pixels in the public repository.
- Never modify executable source automatically from a recovery workflow.
- Never present inferred rewards as official facts.
- Keep source locators, confidence and conflicts auditable.
- Keep high-definition rendering while providing bounded performance fallbacks.
- Record public deployment and physical-device verification separately from CI.
- Each release must report watchdog/test review results: selected risk tier, relevant check count, skipped unrelated gates, runtime and proven quality or speed change.
