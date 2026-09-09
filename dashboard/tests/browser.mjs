// Actual Chromium UI acceptance. Skew responses are explicit TEST DOUBLE;
// diagnostic endpoints still use the temporary C++ -> SQLite -> FastAPI stack.
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  let state = 'partial';
  const quality = { completeness: 'PARTIAL', expected_count: 12, observed_count: 11, usable_count: 10, missing_count: 1, stale_count: 0, invalid_count: 0 };
  const current = { schema_version: 1, status: 'OK', reasons: ['PARTIAL_INPUT'], scope: { exchange: 'CFFEX', product: 'MO', month: '2610', trading_day: '20260907' }, minute: '2026-09-07T09:31:00+08:00', valuation_at: '2026-09-07T09:32:00+08:00', historical: false, current_usable: true, skew_25d_vp: 1.23, quality, raw_revision: 42, algorithm_version: 'mo-skew-25d-v1.0.0', reference: { bundle_id: 'browser-test-double', source_kind: 'SYNTHETIC' } };
  const series = { status: 'OK', baseline: { minute: '2026-09-07T09:30:00+08:00', skew_25d_vp: .5 }, change_vp: .73, points: [{ ...current, minute: '2026-09-07T09:30:00+08:00', skew_25d_vp: .5 }, current] };

  await page.route('**/api/coverage', route => route.fulfill({ json: { complete: true, collector_current: true, groups: [{ exchange: 'CFFEX', product: 'MO', month: '2610', discovered: 12, listed: 12, target: 12, subscribed: 12, failed: 0, received: 12, no_push: 0, verified: true }], instruments: [], update: {} } }));
  await page.route('**/api/skew/**', route => {
    if (state === 'disconnect') return route.abort();
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/series')) return route.fulfill({ json: state === 'unavailable' ? { ...series, change_vp: null, points: [{ ...current, status: 'UNAVAILABLE', skew_25d_vp: null }] } : series });
    if (url.pathname.endsWith('/minute')) return route.fulfill({ json: { ...current, historical: true, current_usable: false, minute: '2026-09-07T09:30:00+08:00', valuation_at: '2026-09-07T09:31:00+08:00' } });
    if (state === 'stale') return route.fulfill({ json: { ...current, current_usable: false, reasons: ['STALE_QUOTE'], quality: { ...quality, stale_count: 2 } } });
    if (state === 'unavailable') return route.fulfill({ json: { ...current, status: 'UNAVAILABLE', current_usable: false, skew_25d_vp: null, reasons: ['FORWARD_PAIRS_MISSING'], quality: { ...quality, usable_count: 4, missing_count: 8 } } });
    return route.fulfill({ json: current });
  });

  await page.goto(process.argv[2]);
  await page.getByTestId('skew-value').filter({ hasText: '1.23 vp' }).waitFor();
  await page.getByTestId('daily-change').filter({ hasText: '0.73 vp' }).waitFor();
  await page.getByText('当前可用 · 部分输入').waitFor();
  await page.getByTestId('test-double').waitFor();
  assert.equal(await page.locator('details.diagnostics').getAttribute('open'), null);

  await page.getByRole('button', { name: '回看指定分钟' }).click();
  await page.getByText('历史分钟').waitFor();
  await page.getByText('返回当前视图').click();

  state = 'stale';
  await page.getByTestId('business-state').filter({ hasText: /^当前不可用$/ }).waitFor({ timeout: 12000 });
  await page.getByText('STALE_QUOTE').waitFor();
  state = 'unavailable';
  await page.getByTestId('business-state').filter({ hasText: /^不可计算$/ }).waitFor({ timeout: 12000 });
  assert.equal(await page.getByTestId('skew-value').textContent(), '—');
  assert.equal(await page.getByTestId('daily-change').textContent(), '—');

  state = 'disconnect';
  await page.getByText(/Skew API 不可用/).waitFor({ timeout: 12000 });
  assert.equal(await page.getByTestId('skew-value').textContent(), '—');
  state = 'partial';
  await page.getByTestId('skew-value').filter({ hasText: '1.23 vp' }).waitFor({ timeout: 12000 });

  await page.getByText('运行与数据诊断').click();
  await page.getByTestId('rows').filter({ hasText: /^[0-9,]+$/ }).waitFor();
  assert.equal(await page.getByText('运行正常', { exact: true }).count(), 2);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  assert.deepEqual(errors, []);
  console.log('PASS: Chromium MO Skew TEST DOUBLE current/change/history/PARTIAL/STALE/UNAVAILABLE/disconnect; actual diagnostic HTTP; mobile layout');
} finally { await browser.close(); }
