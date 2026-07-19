# Atlas Project Roadmap and Version Audit

Updated baseline: Alpha 0.9.4.2

## Audit cadence

- Run a full project audit after every 3 patch releases, and at every minor or major release.
- The current full audit was triggered by the new 0.9.4 minor line. The next scheduled audit is Alpha 0.9.4.5.
- Compare the current implementation against user requests, assistant commitments, known bugs, deferred work, validation evidence, and prior completed features that may have regressed.
- A task is not complete only because code was committed. Completion requires implementation, automated validation, device-level verification where applicable, and no regression of previously accepted behaviour.
- Every audit updates this file and `data/version-audit.json`.

## Project-specific delivery mode

Atlas changes now follow a three-gate workflow:

1. **Fast gate:** syntax, schemas, changed-file contracts and deterministic unit scenarios.
2. **Risk gate:** 200–500 independent checks chosen by change risk, including browser/device profiles and accepted-feature regression coverage.
3. **Publish gate:** merge-state validation, public GitHub Pages verification, service-worker/cache verification and separate physical-device evidence where applicable.

Additional rules:

- Pull requests must validate their own commit, never a forced checkout of `main`.
- Generated health or conflict reports may be committed only when their semantic result changes; timestamp-only commits are prohibited.
- `release-manifest.json` remains the canonical product release source.
- Runtime subcomponents must have one coherent version across source, HTML cache-busting, service-worker cache generation and their validation workflow.
- Validation must assert behavioural boundaries where possible instead of copying brittle implementation literals.
- High-risk changes are developed on isolated branches and are not merged until required checks pass.

## Per-change release verification gate

- Every completed program change must pass 200–500 independently recorded automated assertions or scenario checks before it can be called complete.
- Low-risk isolated changes use at least 200 checks; normal UI/logic changes use 300; high-risk navigation, rendering, cache, deployment, persistence and map changes use 500.
- Repeating one identical command hundreds of times does not count. The checks must cover distinct behaviours, states, dependencies, devices/viewports and regression risks.
- Every release must commit or upload a verification report under `data/release-verification/` or as an immutable workflow artifact.
- Public GitHub Pages deployment must be verified after publication.
- Physical iPad or desktop testing must be recorded separately and cannot be replaced by Chromium emulation, CI or static analysis.
- Full policy: `RELEASE-VERIFICATION-POLICY.md`.

## Latest full audit: Alpha 0.9.4.2 minor-version audit

Audit date: 2026-07-19.

Trigger: a new minor release line was detected; the canonical release manifest is Alpha 0.9.4.2 while the previous roadmap and audit ledger still described 0.9.3.x.

### Completed with repository evidence

- Alpha 0.9.4.2 has one canonical release manifest and release owner.
- The conflict reasoner reports no critical or high findings for the main product release.
- The browser conflict matrix passed 372 checks across desktop, compact desktop, iPad landscape, iPad portrait, compact tablet and mobile profiles.
- The authorised 达达猪 catalogue is complete: 23 of 23 items are imported, with zero unresolved and zero remaining.
- Release scripts, visible release label, service-worker registration, controls, liquid navigation, data guard, settings and major navigation interactions were covered by the browser matrix.
- Existing media-retention safeguards remain active; original video and frame pixels are not retained in the repository.

### Incomplete, partially complete or regressed

- The scan-system health report currently records 35 of 42 checks passing and 7 failing.
- The failures are primarily contract drift: the realtime bridge, monitor HTML, service-worker generation and validation scripts describe different versions, polling intervals and freshness thresholds.
- The scan-system workflow forced `ref: main`, so pull requests could pass while validating the old main branch instead of the proposed code.
- Health workflows produced repeated timestamp-only bot commits, increasing noise, merge conflicts and review cost without changing project state.
- The previous roadmap baseline was 0.9.3.6 and the audit ledger was 0.9.3.5, both behind the canonical 0.9.4.2 release.
- The static conflict report still contains 25 CSS/runtime ownership warnings and a 50/100 risk score. These are not accepted regressions yet, but they are technical debt that can hide future cascade conflicts.
- Public GitHub Pages verification for the optimization branch has not occurred because it is not merged or deployed.
- Physical iPad Safari and desktop-browser verification for the current optimization branch has not been recorded.

### User requests and assistant commitments checked

- Preserve previously accepted bottom navigation, left-rail liquid selection, header safe-area behaviour, settings, favourites, progress, route, search, filters, panels and PWA behaviour.
- Increase execution speed without reducing the existing 200–500-check completion standard.
- Keep scanning, recovery and heartbeat behaviour automatic, bounded and privacy-preserving.
- Finish authorised creator evidence processing, then activate map anchoring gradually after the ultra-HD original-map gate opens.
- Do not treat a commit, a static syntax pass or a repository version label as proof of public deployment or device correctness.

### Current repair branch

`optimization/fast-safe-atlas-0942` contains the first project-specific optimization package:

- Align realtime monitor source, HTML cache version, displayed timing contract and freshness thresholds.
- Refresh the monitor service-worker cache generation.
- Make scan-monitor and scan-system validation run on pull requests.
- Make scan-system pull requests validate their own ref.
- Replace stale literal assertions with behaviour-bound checks.
- Suppress timestamp-only health-report commits.
- Add explicit checks for PR-ref correctness and report deduplication.

This package is not complete until CI, the required risk gate, public deployment verification and applicable physical-device verification pass.

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

### Alpha 0.9.4.3 — fast and safe engineering baseline

- [ ] Merge the monitor-contract and scan-health workflow repair only after all required checks pass.
- [ ] Produce a high-risk verification report covering monitor, recovery, cache, workflow-ref and report-dedup behaviour.
- [ ] Verify the public GitHub Pages response after deployment.
- [ ] Record physical iPad Safari and desktop verification.
- [ ] Close the scan-monitor contract-drift regression only after deployed evidence exists.

### Alpha 0.9.4.4 — reduce conflict and maintenance cost

- [ ] Consolidate CSS ownership for bottom navigation, quick rail, panels, glass effects and active transforms.
- [ ] Reduce the conflict-reasoner warning count and risk score without visual regression.
- [ ] Ensure all generated reports are artifact-first and commit only semantic state changes.
- [ ] Add changed-file test selection so isolated edits receive fast feedback before the full risk gate.

### Alpha 0.9.4.5 — scheduled full audit and map resumption

- [ ] Run the next scheduled full audit.
- [ ] Recheck all accepted product functions against user requests and prior commitments.
- [ ] Resume ultra-HD map base, tiling and coordinate-calibration work after release stability is proven.
- [ ] Re-evaluate deferred evidence-to-map anchoring against the map stage gate.

### Data and evidence pipeline

- [x] Scan and import all 23 authorised 达达猪 Assassin's Creed Shadows catalogue items.
- [x] Resolve the catalogue to zero unresolved and zero remaining items.
- [ ] Convert retained descriptors and timestamps into usable map anchors and evidence records.
- [ ] Complete temple and remaining category location anchoring after the ultra-HD map coordinate system is stable.
- [ ] After 达达猪 evidence integration is complete, request and record the next creator's authorisation before scanning that creator.
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
- [ ] Test on iPad Safari and desktop, not only through static syntax checks or Chromium emulation.
- [ ] Preserve automatic quality degradation for constrained devices.
- [ ] Audit every new visual layer for duplicate animation, excessive blur, forced layout and full-canvas redraw regressions.

### Interface and interaction

- [x] Restore bottom navigation functions after hidden-content regression.
- [x] Replace fluorescent active strips with shared liquid selection media.
- [x] Attach the header to the browser viewport edge with safe-area support.
- [x] Keep the approved bottom navigation liquid-glass behaviour.
- [x] Integrate left-rail icons into the shared selection medium and remove separate selected icon frames.
- [ ] Device-verify current left-rail smoothness and composition after the optimization release deploys.
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
- [ ] Verify all imported locations for category, naming, duplicates and coordinate accuracy.
- [ ] Validate search, filters, favourites, discovery progress, routes, progress views and evidence workflows end-to-end.
- [ ] Verify PWA installation, offline loading and cache migration between releases.
- [ ] Preserve regression coverage so a new patch cannot silently remove an older accepted feature or style dependency.
- [ ] Preserve public-deployment verification so repository state cannot be mistaken for the live release state.

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
