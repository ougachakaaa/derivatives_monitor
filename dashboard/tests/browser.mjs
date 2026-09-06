// Optional actual-browser acceptance, launched by tests/read_path_smoke.py.
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(process.argv[2]);
  await page.getByTestId('rows').filter({ hasText: /^[0-9,]+$/ }).waitFor();
  assert.equal(await page.getByText('运行正常', { exact: true }).count(), 2);
  await page.getByText(/TEST DOUBLE/).waitFor();
  await page.route('**/api/**', route => route.abort());
  await page.getByText('不可达 / 状态未知').waitFor({ timeout: 12000 });
  assert.equal(await page.getByTestId('rows').textContent(), '—');
  assert.equal(await page.getByText('运行正常', { exact: true }).count(), 0);
  await page.unroute('**/api/**');
  await page.getByTestId('rows').filter({ hasText: /^[0-9,]+$/ }).waitFor({ timeout: 12000 });
  assert.equal(await page.getByText('运行正常', { exact: true }).count(), 2);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  assert.deepEqual(errors, []);
  console.log('PASS: Chromium React render, actual HTTP counts, network failure, recovery, mobile layout');
} finally { await browser.close(); }
