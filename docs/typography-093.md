# Atlas Alpha 0.9.3.0 typography implementation

## Runtime layers

- `Atlas Kage Display`: local alias for open/system high-contrast serif fallbacks.
- `Atlas UI Sans`: local alias for open/system CJK sans-serif fallbacks.
- `--font-data`: platform monospace stack for numerical and diagnostic data.

No external font request is required for the first implementation stage, so typography does not delay map rendering or add a new network dependency.

## Visual hierarchy

Display typography is restricted to brand, headings, section labels, and prominent names. Interface copy remains a legible sans-serif. Coordinates, counters, percentages, route metrics, and performance diagnostics use tabular monospace numerals.

## Original treatment

The visual identity is created with original CSS hierarchy, spacing, weight, condensed presentation, restrained red title strokes, and platform/Open Font License fallbacks. It does not reproduce the outlines of the Assassin's Creed Shadows title mark.

## Performance

- local font lookup and system fallback only;
- `font-display: swap` declarations;
- no bundled font binaries;
- no layout-blocking remote stylesheet;
- reduced tracking and title shadows on mobile;
- typography stylesheet is stored in the service-worker cache.
