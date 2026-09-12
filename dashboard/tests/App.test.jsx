import React from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../src/App.jsx';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const health = { query: { status: 'healthy' }, data: { readable: true }, collector: { status: 'healthy', process_alive: true, heartbeat: { connected: true, logged_in: true, expected: 10, subscribed: 10, accepted: 100, written: 80, last_received_us: 1789522260000000 } } };
const quality = { completeness: 'COMPLETE', expected_count: 10, observed_count: 10, usable_count: 10, missing_count: 0, stale_count: 0, invalid_count: 0 };
const current = { schema_version: 1, status: 'OK', reasons: [], scope: { exchange: 'CFFEX', product: 'MO', month: '2610', trading_day: '20260916' }, minute: '2026-09-16T09:31:00+08:00', valuation_at: '2026-09-16T09:32:00+08:00', historical: false, current_usable: true, skew_25d_vp: 1.2345, quality, raw_revision: 88, algorithm_version: '1.0.0', reference: { bundle_id: 'fixture-2610', source_kind: 'SYNTHETIC' } };
const series = { status: 'OK', baseline: { minute: '2026-09-16T09:30:00+08:00', skew_25d_vp: .5 }, change_vp: .7345, points: [{ ...current, minute: '2026-09-16T09:30:00+08:00', skew_25d_vp: .5 }, current] };

function fixture(path) {
  if (path.startsWith('/api/skew/latest')) return current;
  if (path.startsWith('/api/skew/series')) return series;
  if (path.startsWith('/api/skew/minute')) return { ...current, historical: true, current_usable: false, minute: '2026-09-16T09:30:00+08:00', valuation_at: '2026-09-16T09:31:00+08:00' };
  if (path === '/api/sessions') return { markets: [{ exchange: 'CFFEX', product: 'MO', trading_day: '20260916', session_state: 'OPEN', session: 'DAY', phase: 'CONTINUOUS' }] };
  if (path === '/api/coverage') return { complete: true, collector_current: true, groups: [{ exchange: 'CFFEX', product: 'MO', month: '2610', discovered: 10, listed: 10, target: 10, subscribed: 10, failed: 0, received: 10, no_push: 0, verified: true }], instruments: [], update: {} };
  if (path === '/api/health') return health;
  if (path === '/api/days') return { days: [{ day: '20260916' }, { day: '20260915' }] };
  if (path.includes('/summary')) return { rows: 5, size_bytes: 4096, instruments: [], runs: [{ source: 'TEST DOUBLE UI' }] };
  if (path.includes('/snapshots')) return { rows: [] };
  throw new Error(`unexpected ${path}`);
}
const response = body => ({ ok: true, json: async () => body });
const mount = (override = () => undefined, pollMs = 5000) => {
  const fetch = vi.fn(async path => { const value = override(path); return value === undefined ? response(fixture(path)) : value; });
  vi.stubGlobal('fetch', fetch); render(<App pollMs={pollMs} />); return fetch;
};

test('first screen reports selected MO current value, daily change, time, quality and TEST DOUBLE', async () => {
  const fetch = mount();
  await waitFor(() => expect(screen.getByTestId('skew-value').textContent).toBe('1.23 vp'));
  await waitFor(() => expect(screen.getByTestId('daily-change').textContent).toBe('0.73 vp'));
  expect(screen.getByTestId('business-state').textContent).toBe('当前可用');
  expect(screen.getByText('COMPLETE')).toBeTruthy();
  expect(screen.getByTestId('test-double')).toBeTruthy();
  await waitFor(() => expect(screen.getByLabelText('MO 到期月').value).toBe('2610'));
  expect(fetch.mock.calls.some(([url]) => url.includes('/api/skew/latest?month=2610'))).toBe(true);
  expect(screen.getByText('运行与数据诊断').closest('details').open).toBe(false);
});

test('PARTIAL is visible without suppressing a usable API value', async () => {
  mount(path => path.startsWith('/api/skew/latest') ? response({ ...current, reasons: ['PARTIAL_INPUT'], quality: { ...quality, completeness: 'PARTIAL', observed_count: 9, usable_count: 8, missing_count: 1 } }) : undefined);
  await screen.findByText('当前可用 · 部分输入');
  expect(screen.getByTestId('skew-value').textContent).toBe('1.23 vp');
  expect(screen.getByText('PARTIAL_INPUT')).toBeTruthy();
});

test('STALE current result is not presented as currently usable', async () => {
  mount(path => path.startsWith('/api/skew/latest') ? response({ ...current, current_usable: false, reasons: ['STALE_QUOTE'], quality: { ...quality, stale_count: 2 } }) : undefined);
  await screen.findByText('当前不可用');
  expect(screen.getByText('STALE_QUOTE')).toBeTruthy();
  expect(screen.getByText('不声称实时有效')).toBeTruthy();
});

test('UNAVAILABLE exposes reason and never invents a numeric value or daily fallback', async () => {
  mount(path => path.startsWith('/api/skew/latest') ? response({ ...current, status: 'UNAVAILABLE', current_usable: false, skew_25d_vp: null, reasons: ['FORWARD_PAIRS_MISSING'], quality: { ...quality, usable_count: 4, missing_count: 6 } }) : path.startsWith('/api/skew/series') ? response({ ...series, change_vp: null }) : undefined);
  await screen.findByText('不可计算');
  expect(screen.getByTestId('skew-value').textContent).toBe('—');
  expect(screen.getByTestId('daily-change').textContent).toBe('—');
  expect(screen.getByText('FORWARD_PAIRS_MISSING')).toBeTruthy();
});

test('specified minute review is explicitly historical and sends day, minute and month', async () => {
  const fetch = mount();
  await waitFor(() => expect(document.getElementById('history-day').value).toBe('20260916'));
  await waitFor(() => expect(screen.getByLabelText('MO 到期月').value).toBe('2610'));
  fireEvent.change(screen.getByLabelText('回看分钟'), { target: { value: '09:30' } });
  fireEvent.click(screen.getByRole('button', { name: '回看指定分钟' }));
  await screen.findByText('历史分钟');
  const call = fetch.mock.calls.find(([url]) => url.startsWith('/api/skew/minute'))[0];
  expect(call).toContain('day=20260916'); expect(call).toContain('month=2610'); expect(call).toContain('09%3A30%3A00%2B08%3A00');
  expect(screen.getByText('返回当前视图')).toBeTruthy();
});

test('latest API disconnect clears old current and series values, then recovers', async () => {
  let broken = false;
  mount(path => broken && path.startsWith('/api/skew/') ? Promise.reject(new Error('network disconnected')) : undefined, 30);
  await waitFor(() => expect(screen.getByTestId('skew-value').textContent).toBe('1.23 vp'));
  broken = true;
  await waitFor(() => expect(screen.getByTestId('skew-value').textContent).toBe('—'));
  expect(screen.getByTestId('daily-change').textContent).toBe('—');
  expect(screen.getByText(/network disconnected/)).toBeTruthy();
  broken = false;
  await waitFor(() => expect(screen.getByTestId('skew-value').textContent).toBe('1.23 vp'));
});

test('diagnostic data remains available but failures clear its old evidence independently', async () => {
  let broken = false;
  mount(path => broken && ['/api/health', '/api/coverage'].includes(path) ? Promise.reject(new Error('diagnostic unavailable')) : undefined, 30);
  await waitFor(() => expect(screen.getByTestId('rows').textContent).toBe('5'));
  fireEvent.click(screen.getByText('运行与数据诊断'));
  expect(screen.getAllByText('运行正常')).toHaveLength(2);
  broken = true;
  await screen.findAllByText(/diagnostic unavailable/);
  expect(screen.queryAllByText('运行正常')).toHaveLength(0);
  expect(screen.getByTestId('skew-value').textContent).toBe('1.23 vp');
});
