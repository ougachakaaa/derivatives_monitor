import React from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react';
import App from '../src/App.jsx';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const health = { query: { status: 'healthy' }, data: { readable: true }, collector: {
  status: 'healthy', process_alive: true,
  heartbeat: { connected: true, logged_in: true, expected: 1, subscribed: 1, accepted: 10, written: 5, last_received_us: 0 },
}};
function fixture(path) {
  if (path === '/api/sessions') return { as_of: '2026-09-07T23:00:00+08:00', markets: [
    { exchange: 'CFFEX', product: 'IF', trading_day: '20260908', market_state: 'CLOSED', session: null, phase: null },
    { exchange: 'SHFE', product: 'AU', trading_day: '20260908', market_state: 'OPEN', session: 'NIGHT', phase: 'CONTINUOUS' },
  ] };
  if (path === '/api/coverage') return { complete: false, collector_current: true, groups: [{ product: 'IO', month: '2609', discovered: 2, listed: 2, target: 2, subscribed: 1, pending: 0, failed: 1, received: 0, no_push: 1, verified: true }], instruments: [], update: {} };
  if (path === '/api/health') return health;
  if (path === '/api/days') return { days: [{ day: '20260904' }, { day: '20260903' }] };
  if (path.includes('/summary')) return { rows: 5, size_bytes: 4096, instruments: [{ instrument: 'IF2609', rows: 5, last_received_us: 0 }], runs: [{ source: 'TEST_DOUBLE_UI' }] };
  return { rows: [{ id: 1, InstrumentID: 'IF2609', LastPrice: 4000, BidPrice1: 3999, AskPrice1: 4001, Volume: 20 }] };
}
const response = body => ({ ok: true, json: async () => body });

test('renders service evidence, counts and source; day changes use API parameter', async () => {
  const fetch = vi.fn(async path => response(fixture(path)));
  vi.stubGlobal('fetch', fetch);
  render(<App pollMs={50} />);
  await waitFor(() => expect(screen.getByTestId('rows').textContent).toBe('5'));
  expect(screen.getAllByText('运行正常')).toHaveLength(2);
  expect(screen.getByText(/TEST_DOUBLE_UI/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText('交易日'), { target: { value: '20260903' } });
  await waitFor(() => expect(fetch.mock.calls.some(([url]) => url.includes('summary?day=20260903'))).toBe(true));
});

test('disconnect clears green status and old counts; recovery updates them', async () => {
  let broken = false;
  vi.stubGlobal('fetch', vi.fn(async path => {
    if (broken) throw new Error('network disconnected');
    return response(fixture(path));
  }));
  render(<App pollMs={30} />);
  await waitFor(() => expect(screen.getByTestId('rows').textContent).toBe('5'));
  broken = true;
  await waitFor(() => expect(screen.getByTestId('rows').textContent).toBe('—'));
  expect(screen.queryAllByText('运行正常')).toHaveLength(0);
  expect(screen.getByText(/不可达/)).toBeTruthy();
  broken = false;
  await waitFor(() => expect(screen.getByTestId('rows').textContent).toBe('5'));
  expect(screen.getAllByText('运行正常')).toHaveLength(2);
});

test('empty directory and stale Collector do not imply backend failure', async () => {
  vi.stubGlobal('fetch', vi.fn(async path => response(path === '/api/health'
    ? { ...health, collector: { status: 'stale', process_alive: false, heartbeat: health.collector.heartbeat } }
    : { days: [] })));
  render(<App />);
  await screen.findByText('心跳已过期');
  expect(screen.getAllByText('运行正常')).toHaveLength(1);
  expect(screen.getByText(/暂无交易日文件/)).toBeTruthy();
  expect(screen.getByText(/CTP：未知/)).toBeTruthy();
});

test('database error leaves service health intact and removes counts', async () => {
  vi.stubGlobal('fetch', vi.fn(async path => path.includes('/summary')
    ? { ok: false, json: async () => ({ error: 'WAL sidecars unavailable' }) }
    : response(fixture(path))));
  render(<App />);
  await screen.findByText(/WAL sidecars unavailable/);
  expect(screen.getAllByText('运行正常')).toHaveLength(2);
  expect(screen.getByTestId('rows').textContent).toBe('—');
});


test('coverage distinguishes missing pushes from failed subscriptions and clears on error', async () => {
  let broken = false;
  vi.stubGlobal('fetch', vi.fn(async path => {
    if (path === '/api/coverage' && broken) throw new Error('coverage unavailable');
    return response(fixture(path));
  }));
  render(<App pollMs={30} />);
  await screen.findByText('IO');
  expect(screen.getByText('已订阅暂无推送')).toBeTruthy();
  expect(screen.getByText(/覆盖尚未完整确认/)).toBeTruthy();
  broken = true;
  await screen.findByText(/coverage unavailable/);
  expect(screen.queryByText('IO')).toBeNull();
});


test('market sessions distinguish simultaneous markets without changing service health', async () => {
  let broken = false;
  vi.stubGlobal('fetch', vi.fn(async path => {
    if (path === '/api/sessions' && broken) throw new Error('calendar unavailable');
    return response(fixture(path));
  }));
  render(<App pollMs={30} />);
  await screen.findByTestId('market-SHFE-AU');
  expect(screen.getByTestId('market-SHFE-AU').textContent).toContain('开市 (OPEN)');
  expect(screen.getByTestId('market-SHFE-AU').textContent).toContain('夜盘');
  expect(screen.getByTestId('market-CFFEX-IF').textContent).toContain('休市 (CLOSED)');
  expect(screen.getAllByText('运行正常')).toHaveLength(2);
  broken = true;
  await screen.findByText(/calendar unavailable/);
  expect(screen.queryByTestId('market-SHFE-AU')).toBeNull();
  expect(screen.getAllByText('运行正常')).toHaveLength(2);
  broken = false;
  await screen.findByTestId('market-SHFE-AU');
});

test('unknown calendar does not display an open market', async () => {
  vi.stubGlobal('fetch', vi.fn(async path => response(path === '/api/sessions'
    ? { markets: [{ exchange: 'SHFE', product: 'AG', market_state: 'UNKNOWN', reason: 'calendar missing', trading_day: null }] }
    : fixture(path))));
  render(<App />);
  const row = await screen.findByTestId('market-SHFE-AG');
  expect(row.textContent).toContain('未知 (UNKNOWN)');
  expect(row.textContent).not.toContain('开市');
});
