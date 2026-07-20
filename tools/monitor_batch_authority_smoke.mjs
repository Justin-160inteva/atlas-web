import fs from 'node:fs/promises';
import process from 'node:process';
import { chromium } from 'playwright';

const baseURL = process.env.ATLAS_URL || 'http://127.0.0.1:4173/';
const manifest = JSON.parse(await fs.readFile(new URL('../release-manifest.json', import.meta.url), 'utf8'));
const required = Number(manifest.invariants.requiredMonitorBatchAuthorityChecks || 500);
const results = [];
let failed = false;

function record(name, passed, detail) {
  results.push({ name, passed: Boolean(passed), detail });
  if (!passed) failed = true;
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1180, height: 820 } });
await page.goto(`${baseURL}scan-monitor.html?authority-smoke=1`, { waitUntil: 'domcontentloaded', timeout: 45_000 });
await page.waitForFunction(() => typeof window.AtlasScanMonitor?.chooseDurableBatch === 'function', null, { timeout: 15_000 });

for (let index = 0; index < 100; index += 1) {
  const result = await page.evaluate(index => {
    const ids = Array.from({ length: 10 }, (_, item) => `next-${index}-${item}`);
    const status = {
      batchId: 'next10', pilotRegion: 'NEXT10', complete: true,
      summary: { total: 10, imported: 10 },
      updatedAt: '2026-07-20T03:17:06Z',
      items: ids.map((id, item) => ({ externalSourceId: id, page: item + 12, state: 'imported' }))
    };
    const queue = {
      queueId: 'legacy3', pilotRegion: '山城', updatedAt: '2026-07-20T11:27:49Z',
      items: [20, 21, 22].map(page => ({ externalSourceId: `legacy-${page}`, page, state: 'pending' }))
    };
    const runtime = { schemaVersion: 4, pilotRegion: 'NEXT10', state: 'complete', stage: 'complete', updatedAt: '2026-07-20T03:17:06Z' };
    return window.AtlasScanMonitor.chooseDurableBatch(queue, status, runtime, { items: [] });
  }, index);
  record(`terminal-status-beats-newer-legacy-queue-${index}`, result.source === 'status' && result.items.length === 10 && result.complete && result.mismatch, JSON.stringify({ source: result.source, items: result.items.length, mismatch: result.mismatch }));
}

for (let index = 0; index < 100; index += 1) {
  const result = await page.evaluate(index => {
    const queue = {
      queueId: `active-${index}`, pilotRegion: 'ACTIVE', status: 'in_progress', updatedAt: '2026-07-20T12:00:00Z',
      items: [{ externalSourceId: `active-${index}`, page: index + 30, state: 'running' }]
    };
    const status = {
      batchId: 'old-complete', pilotRegion: 'OLD', complete: false,
      summary: { total: 5, imported: 4 }, updatedAt: '2026-07-20T11:00:00Z',
      items: Array.from({ length: 5 }, (_, item) => ({ externalSourceId: `old-${item}`, state: item < 4 ? 'imported' : 'pending' }))
    };
    const runtime = { schemaVersion: 4, pilotRegion: 'ACTIVE', externalSourceId: `active-${index}`, state: 'running', stage: 'download', updatedAt: '2026-07-20T12:00:01Z' };
    return window.AtlasScanMonitor.chooseDurableBatch(queue, status, runtime, { items: [] });
  }, index);
  record(`active-runtime-keeps-current-queue-${index}`, result.source === 'queue' && result.items.length === 1 && !result.complete && result.mismatch, JSON.stringify({ source: result.source, items: result.items.length }));
}

for (let index = 0; index < 100; index += 1) {
  const result = await page.evaluate(index => {
    const status = {
      batchId: `status-only-${index}`, pilotRegion: 'STATUS', complete: index % 2 === 0,
      summary: { total: 2, imported: index % 2 === 0 ? 2 : 1 }, updatedAt: '2026-07-20T10:00:00Z',
      items: [{ externalSourceId: `s-${index}-0`, state: 'imported' }, { externalSourceId: `s-${index}-1`, state: index % 2 === 0 ? 'imported' : 'pending' }]
    };
    return window.AtlasScanMonitor.chooseDurableBatch({}, status, null, { items: [] });
  }, index);
  record(`status-used-when-queue-empty-${index}`, result.source === 'status' && result.items.length === 2, JSON.stringify({ source: result.source, items: result.items.length }));
}

for (let index = 0; index < 100; index += 1) {
  const result = await page.evaluate(index => {
    const id = `same-${index}`;
    const queue = { queueId: id, pilotRegion: 'SAME', status: 'queued', updatedAt: '2026-07-20T12:00:00Z', items: [{ externalSourceId: id, state: 'pending' }] };
    const status = { batchId: id, pilotRegion: 'SAME', complete: false, summary: { total: 1, imported: 0 }, updatedAt: '2026-07-20T11:59:00Z', items: [{ externalSourceId: id, state: 'pending' }] };
    return window.AtlasScanMonitor.chooseDurableBatch(queue, status, null, { items: [] });
  }, index);
  record(`matching-active-batch-keeps-queue-${index}`, result.source === 'queue' && !result.mismatch && result.items.length === 1, JSON.stringify({ source: result.source, mismatch: result.mismatch }));
}

for (let index = 0; index < 100; index += 1) {
  const result = await page.evaluate(index => {
    const id = `complete-${index}`;
    const queue = { queueId: id, pilotRegion: 'DONE', status: 'complete', updatedAt: '2026-07-20T03:17:05Z', items: [{ externalSourceId: id, state: 'imported' }] };
    const status = { batchId: id, pilotRegion: 'DONE', complete: true, summary: { total: 1, imported: 1 }, updatedAt: '2026-07-20T03:17:06Z', items: [{ externalSourceId: id, state: 'imported' }] };
    return window.AtlasScanMonitor.chooseDurableBatch(queue, status, { schemaVersion: 4, pilotRegion: 'DONE', state: 'complete', stage: 'complete', updatedAt: '2026-07-20T03:17:06Z' }, { items: [] });
  }, index);
  record(`terminal-status-remains-authoritative-${index}`, result.source === 'status' && result.complete && result.items[0]?.state === 'imported', JSON.stringify({ source: result.source, complete: result.complete }));
}

await browser.close();

const report = {
  schemaVersion: 1,
  generatedAt: new Date().toISOString(),
  totalChecks: results.length,
  requiredChecks: required,
  passed: !failed && results.length === required,
  checks: results
};
await fs.mkdir(new URL('../data/conflict-reports/', import.meta.url), { recursive: true });
await fs.writeFile(new URL('../data/conflict-reports/monitor-batch-authority-matrix.json', import.meta.url), `${JSON.stringify(report, null, 2)}\n`);
console.log(`Monitor batch authority matrix: ${results.filter(item => item.passed).length}/${results.length} checks passed`);
if (results.length !== required) {
  console.error(`Expected exactly ${required} checks, got ${results.length}`);
  process.exit(3);
}
if (failed) process.exit(2);
