# Atlas Project Roadmap and Version Audit

Updated baseline: Alpha 0.9.3.5

## Audit cadence

- Run a full project audit after every 3 patch releases, and at every minor or major release.
- Compare the current implementation against user requests, assistant commitments, known bugs, deferred work, validation evidence, and prior completed features that may have regressed.
- A task is not complete only because code was committed. Completion requires implementation, automated validation, device-level verification where applicable, and no regression of previously accepted behaviour.
- Every audit updates this file and `data/version-audit.json`.

## Latest audit: Alpha 0.9.3.5 deployment regression

Audit date: 2026-07-19.

Trigger: an accepted feature/version regression was found before the scheduled 0.9.3.8 audit.

Findings:

- The audit ledger and roadmap identify the project as Alpha 0.9.3.5.
- The default-branch `index.html` still displays and cache-busts Alpha 0.9.1.4 assets.
- The default-branch entry page does not explicitly load the Alpha 0.9.3.3/0.9.3.4 liquid-navigation CSS and JavaScript layers.
- Alpha 0.9.3.5 version stamping exists inside `atlas-liquid-nav-0934.js`, but that does not prove the public entry page loads the file.
- The service worker cache name was upgraded to `atlas-alpha-0935-pages-v1`, creating a mixed-release state: a 0.9.3.5 cache can store an entry page whose primary references and visible fallback version remain 0.9.1.4.
- Therefore the user's report that the public site still showed 0.9.3.4 is treated as a real deployment/version-source regression, not merely a browser-cache issue.

Required corrective controls:

1. Use one release manifest/version source for the visible version, asset query strings, service-worker cache name and audit ledger.
2. Make the production entry page explicitly load every required cumulative patch layer.
3. Add a deployment test that fetches the public `index.html` and confirms the intended version and required asset references.
4. Fail validation when the static version, runtime version, service-worker version and audit-ledger version disagree.
5. Do not mark a release deployed until the public GitHub Pages URL is verified after publication.

## Stage gate: ultra-high-definition original map

Status: not complete.

Definition of complete:

1. Original ultra-high-definition map base is usable at all supported zoom levels.
2. Coordinates and overlays align with the original map.
3. Mobile and desktop rendering remain responsive.
4. Existing locations, routes, progress, favourites, discovery state, search, filters, panels, evidence tools and PWA cache work on the new map.
5. The map is verified on iPad Safari and desktop browsers.

Tasks dependent on this gate remain queued, then become active gradually after the gate is complete.

## Active work

### Immediate release recovery

- [ ] Alpha 0.9.3.6: repair the production entry page so its visible version and loaded assets match the intended release.
- [ ] Alpha 0.9.3.6: verify the public GitHub Pages response, not only repository files or JavaScript syntax.
- [ ] Alpha 0.9.3.7: introduce a single release manifest and cross-file version-consistency validation.
- [ ] Alpha 0.9.3.7: add regression checks proving liquid-navigation base and refinement layers are both loaded.
- [ ] Alpha 0.9.3.8: run the next scheduled full audit and resume ultra-HD map work after release recovery is stable.

### Data and evidence pipeline

- [ ] Finish scanning and importing all 23 authorised 达达猪 Assassin's Creed Shadows videos.
- [ ] Resolve the still-unverified catalogue entries and exact Bilibili identifiers.
- [ ] Convert retained descriptors and timestamps into usable map anchors and evidence records.
- [ ] Complete temple location anchoring after the temple scan.
- [ ] Continue priority order: 神社, 九字真言, 109技能点, then 古坟, 秘道, 骑射 and 武形.
- [ ] After 达达猪 is complete, request and record the next creator's authorisation before scanning that creator.
- [ ] Keep original video and frame pixels transient; retain only authorised derived data and attribution records.

### Ultra-high-definition original map

- [ ] Produce the original ultra-high-definition map base.
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
- [ ] Reclassify Alpha 0.9.3.5 liquid-navigation deployment as unverified until the production entry point loads the required layers.
- [ ] Device-verify Alpha 0.9.3.5/0.9.3.6 left-rail smoothness and composition after deployment repair.
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
- [ ] Add regression coverage so a new patch cannot silently remove an older accepted feature or style dependency.
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
