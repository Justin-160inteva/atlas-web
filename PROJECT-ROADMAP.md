# Atlas Project Roadmap and Version Audit

Updated baseline: Alpha 0.9.4.4

## Audit cadence

- Run a full project audit after every 3 patch releases, and at every minor or major release.
- Compare the current implementation against user requests, assistant commitments, known bugs, deferred work, validation evidence, and prior completed features that may have regressed.
- A task is not complete only because code was committed. Completion requires implementation, automated validation, device-level verification where applicable, and no regression of previously accepted behaviour.
- Every audit updates this file and `data/version-audit.json`.

## Per-change release verification gate

- Every completed program change must pass 200–500 independently recorded automated assertions or scenario checks before it can be called complete.
- Low-risk isolated changes use at least 200 checks; normal UI/logic changes use 300; high-risk navigation, rendering, cache, deployment, persistence and map changes use 500.
- Repeating one identical command hundreds of times does not count. The checks must cover distinct behaviours, states, dependencies, devices/viewports and regression risks.
- Every release must commit a verification report under `data/release-verification/`.
- Public GitHub Pages deployment must be verified after publication.
- Physical iPad or desktop testing must be recorded separately and cannot be replaced by CI or static analysis.
- Full policy: `RELEASE-VERIFICATION-POLICY.md`.

## Latest full audit: Alpha 0.9.4.4

Audit date: 2026-07-20.

Triggers:

- Current version 0.9.4.4 is beyond the previously scheduled 0.9.3.8 audit threshold.
- The project crossed from the 0.9.3 patch line into the 0.9.4 patch line.
- Previously accepted cumulative navigation loading remains insufficiently proven and is treated as an open regression risk.

### Confirmed completion evidence

- `release-manifest.json`, `index.html`, `atlas-bootstrap.js` and `sw.js` now share the Alpha 0.9.4.4 release and cache namespace.
- The visible entry-page version and asset cache-busting query strings are stamped as 0.9.4.4.
- `atlas-bootstrap.js` owns visible version stamping, manifest conflict detection and service-worker registration.
- The release manifest defines runtime ownership and high-risk invariants for navigation, controls, settings, data recovery, iPad rendering and service-worker upgrade simulation.
- The authorised video pipeline has progressed, but the current P07–P11 batch remains 4/5 with one item requiring human review.

### Incomplete or partially complete

- The ultra-high-definition original map stage gate is still not complete. HD runtime files exist, but there is no recorded evidence that the final original map base, coordinate calibration, full overlay alignment, responsive rendering and physical iPad verification all pass.
- Repository evidence does not prove that every file listed in `release-manifest.json.releaseAssets` is actually loaded by the production entry path. In particular, `index.html` does not explicitly reference `atlas-liquid-nav-0934.js`, `atlas-controls-0938.js` or `atlas-ipad-nav-0940.js`.
- A committed release manifest is not yet sufficient proof of public deployment correctness; the public GitHub Pages response and active service-worker controller still require post-deployment verification.
- Full 500-check release evidence and separate physical-device evidence for 0.9.4.4 were not located in the files inspected by this audit.
- The 23 authorised 达达猪 scans are not complete; one current item is blocked by an OpenCV media-open failure and requires human review.
- Evidence descriptors have not yet been fully converted into validated map anchors.
- The “完整版 / 终极完整版” completeness requirement remains unaudited end-to-end.

### Regression and technical-debt findings

- **Open high-risk regression risk:** cumulative navigation/control/iPad patch loading is declared in the release manifest but not directly demonstrated by the static production entry page. Until browser validation proves the runtime loads and executes each owner exactly once, accepted navigation behaviour remains at risk.
- **Release-evidence debt:** the repository needs one machine-readable verification index tying each release to its 200–500 checks, workflow run, public deployment response and device test record.
- **Runtime ownership debt:** release assets and runtime owners should be validated against the browser's loaded-resource graph, not only string consistency.
- **Scan-pipeline blocker:** unknown OpenCV media-open failures stop automatic recovery and require a documented human-resolution path.
- **Conversation-history limitation:** no additional retrievable project conversation archive was available to this run beyond the maintained roadmap/audit ledger and accessible recent project context. Existing recorded requests and commitments therefore remain authoritative until a fuller archive is available.

## Stage gate: ultra-high-definition original map

Status: not complete.

Definition of complete:

1. Original ultra-high-definition map base is usable at all supported zoom levels.
2. Coordinates and overlays align with the original map.
3. Mobile and desktop rendering remain responsive.
4. Existing locations, routes, progress, favourites, discovery state, search, filters, panels, evidence tools and PWA cache work on the new map.
5. The map is verified on iPad Safari and desktop browsers.

Tasks dependent on this gate remain queued, then become active gradually after the gate is complete.

## Next three release priorities

### Alpha 0.9.4.5 — prove the production runtime graph

- [ ] Add a browser assertion that every `releaseAssets` entry is loaded exactly once or explicitly classify it as declarative-only.
- [ ] Prove cumulative liquid navigation, controls and iPad compositor owners execute in the public entry path.
- [ ] Add a machine-readable release verification index linking checks, workflow run, public deployment and device evidence.
- [ ] Resolve or formally isolate the current authorised scan item requiring human review.

### Alpha 0.9.4.6 — stabilise deployment and regression coverage

- [ ] Run the complete 500-scenario navigation, rendering, cache, persistence and service-worker upgrade matrix.
- [ ] Verify the public GitHub Pages response, loaded resources, visible version and active service-worker cache after deployment.
- [ ] Recheck search, filters, route, progress, favourites, panels, settings and quick rail on desktop and iPad Safari.
- [ ] Continue authorised scans without widening creator authorisation or retaining original media.

### Alpha 0.9.4.7 — scheduled full audit and map-gate progress

- [ ] Run the next full version audit.
- [ ] Reassess whether the ultra-HD original map stage gate can move from pending to partially complete or complete, using recorded evidence only.
- [ ] Continue coordinate calibration, marker alignment and efficient visible-region/tile rendering.
- [ ] Activate deferred anchoring tasks gradually only if the map gate becomes complete.

## Active work

### Data and evidence pipeline

- [ ] Finish scanning and importing all 23 authorised 达达猪 Assassin's Creed Shadows videos.
- [ ] Resolve the still-unverified catalogue entries and exact Bilibili identifiers.
- [ ] Convert retained descriptors and timestamps into usable map anchors and evidence records.
- [ ] Complete temple location anchoring after the temple scan.
- [ ] Continue priority order: 神社, 九字真言, 109技能点, then 古坟, 秘道, 骑射 and 武形.
- [ ] After 达达猪 is complete, request and record the next creator's authorisation before scanning that creator.
- [ ] Keep original video and frame pixels transient; retain only authorised derived data and attribution records.

### Ultra-high-definition original map

- [ ] Produce the final original ultra-high-definition map base.
- [ ] Define coordinate transformation and calibration points.
- [ ] Validate marker alignment across regions and zoom levels.
- [ ] Add efficient tile or visible-region rendering for the final map.
- [ ] Verify offline caching strategy without making first load excessive.

### Performance and stability

- [ ] Maintain a 60 FPS target on supported mobile and desktop hardware.
- [ ] Add repeatable performance baselines for map pan, pinch zoom, button zoom, panel opening and marker selection.
- [ ] Test on iPad Safari and desktop, not only through static syntax checks.
- [ ] Preserve automatic quality degradation for constrained devices.
- [ ] Audit every new visual layer for duplicate animation, excessive blur, forced layout and full-canvas redraw regressions.

### Interface and interaction

- [x] Restore bottom navigation functions after hidden-content regression.
- [x] Replace fluorescent active strips with shared liquid selection media.
- [x] Attach the header to the browser viewport edge with safe-area support.
- [x] Keep the approved bottom navigation liquid-glass behaviour.
- [x] Integrate left-rail icons into the shared selection medium and remove separate selected icon frames.
- [ ] Browser-prove cumulative navigation/control/iPad owner loading in Alpha 0.9.4.5.
- [ ] Device-verify left-rail smoothness and composition after deployment.
- [ ] Recheck all panels, bottom sheets, search, route, progress, favourites and category filters after each navigation-layer change.
- [ ] Continue refining mobile and desktop control spacing where screenshots reveal crowding or overlap.

### Typography and visual identity

- [x] Establish display, UI and data font roles with non-Ubisoft font sources.
- [x] Add font licence documentation and avoid extracting Ubisoft font files.
- [ ] Create the actual original Atlas display font assets or licensed subsets; the current stage uses CSS aliases and system/open-source fallbacks.
- [ ] Design original special SVG glyphs only where needed, without tracing Ubisoft title lettering.
- [ ] Test font loading, readability and layout stability on Chinese mobile and desktop interfaces.

### Core product completeness

- [ ] Re-audit the original “完整版 / 终极完整版” requirement against the current feature set.
- [ ] Verify all 3430 imported locations for category, naming, duplicates and coordinate accuracy.
- [ ] Validate search, filters, favourites, discovery progress, routes, progress views and evidence workflows end-to-end.
- [ ] Verify PWA installation, offline loading and cache migration between releases.
- [ ] Add browser-resource regression coverage so a new patch cannot silently remove an older accepted feature or style dependency.
- [ ] Add public-deployment verification so repository state cannot be mistaken for the live release state.

## Deferred until the ultra-HD map gate opens

- [ ] Gradually complete all location anchoring from scanned creator evidence.
- [ ] Increase route quality using the final map geometry and validated obstacles.
- [ ] Refine region and landmark presentation against the final original map.
- [ ] Complete unresolved visual polish and product-completeness items discovered in version audits.

## Audit output requirements

Each audit must report:

1. Current version and previous audited version.
2. Requests and commitments newly discovered from conversation history.
3. Completed items with proof.
4. Incomplete, partially complete and regressed items.
5. Newly found bugs or technical debt.
6. Priority order for the next three releases.
7. Tasks blocked by the ultra-HD map or creator authorisation.
8. Changes written back to the roadmap and audit ledger.
