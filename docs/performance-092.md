# Atlas Alpha 0.9.2.0 performance plan

## Runtime targets

- Primary interaction target: 60 FPS on supported mobile and desktop hardware.
- Frame deadline: 16.7 ms; Atlas reserves roughly 10 ms for JavaScript and Canvas work.
- No permanent animation loop. Rendering is event-driven and synchronized with `requestAnimationFrame()`.
- Automatic quality fallback when repeated frames exceed the budget.

A fixed frame rate cannot be guaranteed on every browser, thermal state, power mode, or low-end device. The runtime therefore prioritizes stable frame pacing and reduces pixel density and optional HD work before allowing prolonged jank.

## Implemented optimizations

1. Replaced the mobile 22 ms throttle and desktop `setTimeout` + rAF chain with one coalesced rAF scheduler.
2. Added adaptive Canvas DPR based on viewport area, device memory, CPU concurrency, and measured frame cost.
3. Cropped the 4096 map image to the visible source rectangle before drawing.
4. Cached the enabled/favorites location filter instead of filtering the full catalog every frame.
5. Paused HD tile generation and HD compositing during drag, pinch, wheel, and low-quality fallback.
6. Moved HD tile work to idle periods; removed forced idle timeouts and disabled pixel sharpening on mobile/low-power devices.
7. Used `OffscreenCanvas` for optional desktop tile preparation when supported.
8. Reduced redundant HD tile fade redraws.
9. Disabled backdrop blur, transitions, and animations during direct map interaction.
10. Added CSS containment and `content-visibility` for hidden panels.
11. Added Long Animation Frame / Long Task observation and a runtime diagnostic API.

## Diagnostics

Open the site with `?perf=1` to display the live FPS, Canvas draw time, DPR, and current adaptive quality level.

The same data is available from the browser console:

```js
AtlasPerf092.report()
```

Quality can be tested manually:

```js
AtlasPerf092.setQuality(0) // high
AtlasPerf092.setQuality(1) // balanced
AtlasPerf092.setQuality(2) // performance
```

## Primary references

- https://web.dev/articles/rendering-performance
- https://web.dev/articles/animations-overview
- https://web.dev/articles/optimize-long-tasks
- https://web.dev/articles/canvas-performance
- https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial/Optimizing_canvas
- https://developer.mozilla.org/en-US/docs/Web/API/Performance_API/Long_animation_frame_timing
- https://developer.mozilla.org/en-US/docs/Web/API/Window/requestIdleCallback
- https://web.dev/articles/content-visibility
- https://webkit.org/blog/14908/motionmark-1-3/
