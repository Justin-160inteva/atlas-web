# Atlas Project Roadmap and Version Audit

Updated baseline: **Alpha 0.9.4.8**

## Operating rules

- Every completed code change must pass 200–500 independently recorded checks.
- Navigation, rendering, cache, deployment, persistence, map and evidence changes use exactly 500 checks.
- Every three patch releases require a full framework audit. Alpha 0.9.4.8 is a mandatory full-audit release; the next mandatory audit is Alpha 0.9.4.11.
- A task is complete only after implementation, automated validation and, where applicable, separate physical-device and public-deployment verification.
- Project-side AI improvements mean better evidence structures, confidence, conflict detection, prioritisation and recovery logic. They are not described as autonomous model training.

## Completed release line

### Alpha 0.9.4.3 — navigation geometry and interaction

- Bottom navigation centring and safe-area placement repaired.
- Left rail is fully visible and no longer embedded into the screen edge.
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
- Dedicated 500-check data-centre matrix added.
- Eleven-item serial scan support and queue schema recovery retained.

## Alpha 0.9.4.8 — active work

### Reward evidence pipeline: 3430 locations

- [x] Define a reward evidence policy with four states:
  - official confirmed;
  - multi-source confirmed;
  - high-confidence inference;
  - unresolved.
- [x] Define the reward record JSON schema.
- [x] Define standard Simplified Chinese terminology and translation rules.
- [x] Initialise a 3430-location coverage index without fabricating rewards.
- [x] Add a dedicated exact-500 reward evidence contract matrix.
- [ ] Generate a stable mapping from every location ID to one reward record.
- [ ] Research and import the first high-confidence batch from official text, game screenshots and authorised/public video evidence.
- [ ] Add duplicate, source-locator, terminology and conflict reports for every batch.
- [ ] Display reward status, confidence and evidence summary in location details.
- [ ] Expand verified coverage gradually; unresolved locations must remain explicitly unresolved.

### Mandatory full framework audit

- [x] Add a dedicated Alpha 0.9.4.8 full-project audit executable.
- [x] Check release assets, duplicate owners, reward contracts and obsolete known controllers.
- [x] Protect locked reward records from automatic overwrite.
- [ ] Run the complete CI gate and review the generated deletion candidates.
- [ ] Delete only files proven to have no runtime owner, no references and no compatibility role.
- [ ] Record public GitHub Pages verification and separate physical iPad verification after release.

## Next releases

### Alpha 0.9.4.9 — first verified reward batch

- Import the first reviewable reward records with source locators.
- Add reward summaries to location details.
- Report official, multi-source, inferred, unresolved and conflict counts.

### Alpha 0.9.4.10 — reward coverage and whole-site interaction polish

- Expand reward coverage in bounded batches.
- Continue Apple-inspired frosted UI standardisation for search, sheets and remaining panels.
- Add performance baselines for map pan, zoom, marker selection and panel transitions.

### Alpha 0.9.4.11 — next mandatory full audit

- Audit the complete reward pipeline, UI owners, Service Worker, workflows and data files.
- Remove only proven-obsolete files.
- Reassess the ultra-HD original map stage gate.

## Ultra-high-definition original map stage gate

Status: **not complete**.

Completion requires:

1. final original ultra-HD map base;
2. coordinate and overlay calibration;
3. responsive mobile and desktop rendering;
4. compatibility with locations, routes, progress, favourites, search, filters, panels, evidence and PWA caching;
5. physical iPad Safari and desktop verification.

Tasks that depend on final geometry remain queued until this gate is complete.

## Persistent quality requirements

- Preserve one active scan/download at a time.
- Never broaden creator authorisation automatically.
- Never retain original video or frame pixels in the public repository.
- Never present inferred rewards as official facts.
- Keep source locators, confidence and conflicts auditable.
- Keep high-definition rendering while providing bounded performance fallbacks.
- Record physical-device verification separately from CI.
