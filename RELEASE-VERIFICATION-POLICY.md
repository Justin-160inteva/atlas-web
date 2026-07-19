# Atlas Release Verification Policy

Effective from Alpha 0.9.3.6.

## Required verification volume

Every completed program change must pass a release-specific verification matrix before it is described as complete.

- Low-risk documentation or isolated data changes: minimum 200 automated assertions/checks.
- Normal UI, logic, data pipeline or styling changes: 300 automated assertions/checks.
- High-risk navigation, rendering, cache, deployment, persistence, map, service-worker or cross-layer changes: 500 automated assertions/checks.

The number refers to independently recorded assertions or scenario checks, not 200 to 500 meaningless repetitions of the same command.

## Required categories

Each release matrix must cover applicable checks from these categories:

1. JavaScript syntax and module loading.
2. CSS parsing, cascade order and cumulative layer dependencies.
3. HTML entry-point references and version consistency.
4. Service-worker installation, activation, upgrade and cache migration.
5. Public deployment version and required asset availability.
6. Mobile and desktop viewport layouts.
7. iPad Safari-specific safe area, touch and cache behaviour.
8. Bottom navigation and left navigation state transitions.
9. Search, filters, route, progress, favourites and discovery state.
10. Panels, sheets, overlays and aria-hidden state.
11. Pointer, touch, wheel, pinch and button zoom interactions.
12. Canvas rendering, marker selection and visible-region drawing.
13. Performance budget and long-task regressions.
14. Offline fallback and first-load behaviour.
15. Persistence in localStorage and restoration after reload.
16. Evidence, authorisation and analysis pipeline integrity.
17. Backward regression against previously accepted screenshots and behaviour.
18. Cross-file release version consistency.
19. Error handling and missing-resource behaviour.
20. Accessibility and reduced-motion fallbacks.

## Release completion rule

A release cannot be marked complete until all of the following are true:

- The required assertion count has passed.
- No critical or high-severity regression remains.
- The public GitHub Pages entry point has been verified after deployment.
- Previously accepted functionality remains present.
- Device-dependent items are either verified on the target device or explicitly marked as awaiting device verification.
- The verification report is committed to `data/release-verification/`.

## Honesty rule

Static checks, code inspection and CI cannot be described as physical iPad or desktop testing. Device validation must be recorded separately. A release may be code-complete while still awaiting device verification.

## Risk classification examples

### 200 checks

- Documentation updates.
- Isolated catalogue metadata corrections.
- Non-runtime licence or roadmap changes.

### 300 checks

- One panel layout change.
- Typography adjustments.
- A contained data import or filtering improvement.

### 500 checks

- Service-worker or deployment changes.
- Navigation architecture changes.
- Map rendering, coordinates, markers or performance changes.
- Cross-version asset loading changes.
- Any fix for a previously observed regression.
