# Atlas Project Roadmap and Version Audit

Updated baseline: **Alpha 0.9.4.8**  
Latest full audit: **2026-08-15 — regression-triggered**

## Operating rules

- User-requested product behaviour has priority over arbitrary test-count targets.
- Validation is risk-based: low-risk documentation/rules about 40–100 targeted checks; ordinary feature changes about 80–180 relevant checks; scheduler, persistence, queue schema, cache, deployment and map-core changes about 180–300 relevant checks; major/minor releases, scheduled full audits and migrations may use complete relevant matrices up to about 500 checks per gate.
- Every release must review watchdog speed, polling, duplicate scheduling, path-scoped CI, repeated checks and total validation time without weakening quality floors.
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

### Reward evidence pipeline
- [x] Four evidence states: official confirmed, multi-source confirmed, high-confidence inference and unresolved.
- [x] Reward record JSON schema.
- [x] Standard Simplified Chinese terminology and translation rules.
- [x] 3430-location reward record coverage without fabricated rewards.
- [x] 35 bounded reward batches generated.
- [x] 125 multi-source-confirmed records.
- [x] 872 high-confidence inference records.
- [x] 2433 unresolved records remain explicit.
- [ ] Human review and locking for generated records.
- [ ] Official-source confirmations.
- [ ] Reward status, confidence, evidence and conflict summary in every location detail.
- [ ] Gradual verified coverage expansion with no inference presented as official.

### Audit and verification status
- [x] Dedicated Alpha 0.9.4.8 audit executable.
- [x] Regression-triggered audits on 2026-07-22, 2026-07-26, 2026-07-28 and 2026-08-15.
- [x] Latest report: `data/audits/full-audit-0948-regression-20260815.json`.
- [ ] Synchronize release/cache identity across `release-manifest.json`, `atlas-bootstrap.js` and `sw.js`.
- [ ] Restore one authoritative scan batch identity.
- [ ] Restore bounded recovery safety policy.
- [ ] Restore strict earliest-unresolved queue ownership.
- [ ] Regenerate current scan-system health evidence.
- [ ] Prove dynamic validation budgets and path-scoped CI on `main`.
- [ ] Public GitHub Pages verification.
- [ ] Physical iPad Safari and desktop verification.

## Critical regressions confirmed on 2026-08-15

### 1. Release and service-worker cache namespace drift persists

- `release-manifest.json`: `atlas-alpha-0948-pages-v1-monitor-v11-ipad-adaptive-markers-1`
- `atlas-bootstrap.js`: `atlas-alpha-0948-pages-v1-monitor-v11-ipad-adaptive-markers-1`
- `sw.js`: `atlas-alpha-0948-pages-v1-monitor-v12-ipad-adaptive-markers-1-sheet-drag-1-reward-summary-1-ai-repair-1`

Release synchronisation, service-worker upgrade simulation, cache invalidation and conflict detection cannot be treated as verified until all release owners use one namespace.

### 2. Batch authority and queue scope are freshly inconsistent

The active scan manifest still declares batch `eleven-production-p080-v1`, `maximumQueueItems=1` and `processingOrder=strict-p080-only`. The status file also reports P80 complete. However, the durable queue was recreated on **2026-08-14** as `eleven-ac-shadows-pilot-v2` with **P20, P21 and P22 pending** in the 山城 region.

This is direct evidence that manifest, queue and status do not represent one authoritative batch identity or scope. The accepted single-authority and strict-order guarantees are therefore not currently proven.

### 3. Recovery safety regression persists

The active manifest still allows:
- `maxAttemptsPerItem=20`;
- `retryTechnicalFailuresUntilResolved=true`;
- `blockUnknownOrIdentityFailures=false`;
- `neverModifySourceCodeAutomatically=false`.

This contradicts accepted behaviour: known transient failures must remain bounded; unknown/identity/authorization/privacy failures must stop safely; executable source must never be modified automatically by recovery logic.

### 4. Watchdog/test speed policy is documented but not landed on main

The primary Atlas CI still unconditionally runs multiple fixed 500-scenario matrices, the full project audit and browser/Playwright gates. Path-scoped dynamic test budgets are not proven active on `main`, so unrelated runtime-progress or cross-project changes can still trigger expensive Atlas-wide validation.

## Conversation-history requirements rechecked

The 2026-08-15 audit rechecked all project commitments available in the current project conversation context, including:
- one active scan/download at a time;
- no later item bypassing the earliest unresolved item;
- bounded retries for known transfer failures;
- safe stop for unknown, identity, authorization and privacy failures;
- no automatic executable-source modification;
- per-release watchdog/test optimisation with measurable speed improvement and preserved quality floors;
- risk-based and path-scoped CI instead of unrelated fixed full matrices;
- no reward inference presented as official confirmation;
- ultra-HD original-map dependent work remaining queued until the stage gate is genuinely complete;
- separate CI, public deployment and physical iPad/desktop verification evidence.

## Repository scope observation

The COD11 live-translator work remains a separate product concern under the same repository. It is not by itself an Atlas runtime regression, but shared-repository ownership still increases path-filtering and release-noise risk and must be reviewed before 0.9.4.11.

## Next three releases

### Alpha 0.9.4.9 — restore release and scan authority
Priority S:
- Synchronize cache namespace across release manifest, bootstrap and service worker.
- Restore one batch identity across manifest, queue, status, runtime and monitor.
- Restore strict earliest-unresolved ownership and one active task maximum.
- Restore dictionary-driven bounded retries: safe known transport failures up to 5; unknown, identity, authorization and privacy failures capped and blocked safely.
- Restore `neverModifyExecutableSourceAutomatically=true` / equivalent effective policy.
- Land risk-based test budgets and path-scoped CI; heartbeat-only and `cod11-live-translator/**` commits must not run unrelated Atlas UI, reward or full-audit matrices.
- Regenerate current health, release-sync and cache-upgrade evidence.

### Alpha 0.9.4.10 — reviewed rewards and interaction evidence
- Human-review and lock the first bounded reward batches.
- Add official-source confirmations where verifiable evidence exists.
- Add reward summaries, confidence labels, source locators and conflict states to location details.
- Report official, multi-source, inferred, unresolved, reviewed, locked and conflict counts.
- Add performance baselines for map pan, zoom, marker selection, panel transitions and iPad rendering.

### Alpha 0.9.4.11 — coverage expansion and scheduled audit
- Expand human-reviewed reward coverage in bounded batches.
- Complete public GitHub Pages verification records.
- Complete separate physical iPad Safari and desktop verification records.
- Audit workflow noise, heartbeat commit frequency and repository project separation.
- Run the scheduled full audit.
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
- Keep release manifest, bootstrap and service worker on one cache namespace.
- Never broaden creator authorisation automatically.
- Never retain original video or frame pixels in the public repository.
- Never modify executable source automatically from a recovery workflow.
- Never present inferred rewards as official facts.
- Keep source locators, confidence and conflicts auditable.
- Keep high-definition rendering while providing bounded performance fallbacks.
- Record public deployment and physical-device verification separately from CI.
- Each release must report watchdog/test review results: selected risk tier, relevant check count, skipped unrelated gates, runtime and proven quality or speed change.
