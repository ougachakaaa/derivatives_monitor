import React, { useEffect, useMemo, useState } from 'react';

const number = value => value == null ? '—' : Number(value).toLocaleString('zh-CN');
const metric = value => value == null ? '—' : `${Number(value).toFixed(2)} vp`;
const timestamp = value => value ? new Date(value / 1000).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '暂无';
const instant = value => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '—';
const shortMinute = value => value ? new Date(value).toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hour12: false }) : '—';
const marketLabels = { OPEN: '开市', BREAK: '盘中休息', CLOSED: '休市', UNKNOWN: '未知' };
const sessionLabels = { DAY: '日盘', NIGHT: '夜盘' };
const phaseLabels = { CONTINUOUS: '连续交易', AUCTION: '集合竞价' };
const healthLabels = { healthy: '运行正常', degraded: '连接或订阅异常', starting: '启动中', stopped: '已停止', failed: '运行失败', stale: '心跳已过期', unknown: '状态未知' };
const reasonLabels = {
  PARTIAL_INPUT: '部分合约输入缺失，当前节点仍可计算', STALE_QUOTE: '报价已超出30秒时效',
  WAITING_FOR_MINUTE: '当前连续交易分钟尚未封口', REFERENCE_MISSING: '缺少该交易日与月份的审核参考包',
  REFERENCE_INVALID: '参考包无效或身份不匹配', TARGET_MONTH_MISSING: '未配置且未选择 MO 到期月',
  CALENDAR_UNKNOWN: '无法从审核日历确定时段', UNSUPPORTED_SESSION: '指定时间不是 MO 连续交易分钟',
  MINUTE_UNSEALED: '指定分钟尚未封口', UNIVERSE_INCOMPLETE: '合约清单不完整',
  FORWARD_PAIRS_MISSING: '不足三组可用的近 ATM 平价报价', FORWARD_UNSYNCHRONIZED: '平价报价时间不同步',
  FORWARD_INCONSISTENT: '三组平价隐含远期不一致', WING_UNBRACKETED: '25Δ 翼节点未被有效报价夹住',
  WING_GAP_TOO_WIDE: '25Δ 翼节点间距过大', INPUTS_UNSYNCHRONIZED: '最终计算输入时间不同步',
  PRICE_OUT_OF_BOUNDS: '期权价格超出 Black-76 边界', EXPIRY_DAY_UNSUPPORTED: '到期日不计算新 Skew', EXPIRED: '合约已到期',
};

async function get(path, signal) {
  const response = await fetch(path, { signal, cache: 'no-store' });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
  return body;
}
const query = values => Object.entries(values).filter(([, value]) => value != null && value !== '').map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`).join('&');
const period = value => value ? `${value.trading_day} · ${sessionLabels[value.session]} · ${value.start} → ${value.end}` : '暂无已知时段';

function Reasons({ reasons = [] }) {
  if (!reasons.length) return <p className="muted">未报告异常原因。</p>;
  return <ul className="reasons">{reasons.map(reason => <li key={reason}><span>{reasonLabels[reason] || '业务前提未满足'}</span><code>{reason}</code></li>)}</ul>;
}

function reportState(result) {
  if (!result) return { text: '等待数据', tone: 'neutral' };
  if (result.status !== 'OK') return { text: '不可计算', tone: 'bad' };
  if (result.historical) return { text: '历史分钟', tone: 'history' };
  if (!result.current_usable) return { text: '当前不可用', tone: 'warn' };
  if (result.quality?.completeness === 'PARTIAL' || result.reasons?.includes('PARTIAL_INPUT')) return { text: '当前可用 · 部分输入', tone: 'warn' };
  return { text: '当前可用', tone: 'good' };
}

function Quality({ result }) {
  const quality = result?.quality;
  if (!quality) return <div className="quality-empty">未取得质量证据</div>;
  return <div className="quality-grid" aria-label="数据质量">
    <div><span>完整性</span><strong>{quality.completeness || '未知'}</strong></div><div><span>可用 / 预期</span><strong>{number(quality.usable_count)} / {number(quality.expected_count)}</strong></div>
    <div><span>缺失</span><strong>{number(quality.missing_count)}</strong></div><div><span>过期 / 无效</span><strong>{number(quality.stale_count)} / {number(quality.invalid_count)}</strong></div>
  </div>;
}

function Trend({ series, selectedMinute }) {
  const all = series?.points || [];
  const valid = all.filter(point => point.status === 'OK' && point.skew_25d_vp != null);
  if (!valid.length) return <div className="trend-empty">当日尚无可绘制的 Skew 分钟点；失败分钟不会被填补。</div>;
  const width = 720, height = 180, pad = 18;
  const values = valid.map(point => point.skew_25d_vp), low = Math.min(...values), high = Math.max(...values), span = high - low || 1;
  const x = point => pad + (all.indexOf(point) / Math.max(1, all.length - 1)) * (width - pad * 2);
  const y = point => pad + (high - point.skew_25d_vp) / span * (height - pad * 2);
  const runs = []; let run = [];
  all.forEach(point => { if (point.status === 'OK' && point.skew_25d_vp != null) run.push(point); else if (run.length) { runs.push(run); run = []; } });
  if (run.length) runs.push(run);
  return <div className="trend" data-testid="trend"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="当日 Skew 分钟走势"><line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} className="axis" />
    {runs.map((points, index) => <polyline key={index} points={points.map(point => `${x(point)},${y(point)}`).join(' ')} />)}
    {valid.map(point => <circle key={point.minute} cx={x(point)} cy={y(point)} r={point.minute === selectedMinute ? 5 : 2.5} className={point.minute === selectedMinute ? 'selected' : ''} />)}</svg>
    <div className="trend-scale"><span>{shortMinute(all[0]?.minute)} · {metric(valid[0].skew_25d_vp)}</span><span>{shortMinute(all.at(-1)?.minute)} · {metric(valid.at(-1).skew_25d_vp)}</span></div></div>;
}

function BusinessReport({ result, series, loading, error, seriesError, view, onCurrent }) {
  const state = reportState(result);
  return <>{error && <div className="business-error" role="alert"><strong>Skew API 不可用</strong><span>{error}。当前可见指标只来自成功响应；失败请求的旧结果不会被保留为当前值。</span></div>}
    {seriesError && <div className="business-error" role="alert"><strong>当日变化不可用</strong><span>{seriesError}。已清除旧的序列与变化值；当前 Skew 来自本次成功的 latest 响应。</span></div>}
    <section className="hero" aria-label="Skew 业务汇报"><div className="hero-main"><div className="hero-heading"><div><p className="kicker">{view === 'history' ? '指定分钟回看' : '最新封口分钟'}</p><h2>{result?.scope ? `${result.scope.product}${result.scope.month} · 25Δ Put−Call` : 'MO 25Δ Put−Call'}</h2></div><div className={`state ${state.tone}`} data-testid="business-state">{loading ? '正在读取' : state.text}</div></div>
      {result?.reference?.source_kind === 'SYNTHETIC' && <div className="test-double" data-testid="test-double">TEST DOUBLE · 非真实市场证据</div>}
      <div className="headline-value" data-testid="skew-value">{metric(result?.skew_25d_vp)}</div><p className="definition">Skew = 25Δ Put IV − 25Δ Call IV。页面只展示 API 结果，不在浏览器中重算 IV 或 Skew。</p>
      <div className="headline-grid"><div><span>当日变化</span><strong data-testid="daily-change">{metric(series?.change_vp)}</strong><small>{series?.baseline ? `相对 ${shortMinute(series.baseline.minute)} 的首个有效点` : '无有效基准，不使用昨收'}</small></div><div><span>数据分钟</span><strong>{shortMinute(result?.valuation_at)}</strong><small>{instant(result?.valuation_at)}</small></div><div><span>观察状态</span><strong>{result?.historical ? '历史' : result?.current_usable ? '当前' : '当前不可用'}</strong><small>{result?.current_usable ? '当前时效条件满足' : '不声称实时有效'}</small></div></div>
      {view === 'history' && <button className="text-button" onClick={onCurrent}>返回当前视图</button>}</div>
      <aside className="trust"><h3>可信程度</h3><Quality result={result} /><h3>{result?.status === 'OK' ? '状态说明' : '不可计算原因'}</h3><Reasons reasons={result?.reasons} /><dl className="trace"><div><dt>Raw revision</dt><dd>{number(result?.raw_revision)}</dd></div><div><dt>算法</dt><dd>{result?.algorithm_version || '—'}</dd></div><div><dt>参考包</dt><dd>{result?.reference?.bundle_id || '—'}</dd></div></dl></aside></section></>;
}

function HistoryControls({ days, month, onResult, onError }) {
  const [historyDay, setHistoryDay] = useState(''), [historyTime, setHistoryTime] = useState('09:30'), [busy, setBusy] = useState(false);
  useEffect(() => { if (!historyDay && days.length) setHistoryDay(days[0].day); }, [days, historyDay]);
  const submit = async event => { event.preventDefault(); if (!historyDay || !historyTime) return; setBusy(true); onResult(null); onError('');
    const minute = `${historyDay.slice(0, 4)}-${historyDay.slice(4, 6)}-${historyDay.slice(6, 8)}T${historyTime}:00+08:00`;
    try { onResult(await get(`/api/skew/minute?${query({ day: historyDay, minute, month })}`)); } catch (error) { onError(error.message); } finally { setBusy(false); }
  };
  return <form className="history-controls" onSubmit={submit}><div><label htmlFor="history-day">交易日</label><select id="history-day" value={historyDay} onChange={event => setHistoryDay(event.target.value)} required><option value="">请选择</option>{days.map(item => <option key={item.day} value={item.day}>{item.day}</option>)}</select></div><div><label htmlFor="history-time">连续交易分钟</label><input id="history-time" aria-label="回看分钟" type="time" step="60" value={historyTime} onChange={event => setHistoryTime(event.target.value)} required /></div><button type="submit" disabled={busy || !historyDay}>{busy ? '正在回看…' : '回看指定分钟'}</button></form>;
}

function Diagnostics({ health, healthError, days, daysError, diagnosticDay, setDiagnosticDay, data, dataError, updated, coverage, coverageError, sessions, sessionsError }) {
  const collector = health?.collector, heartbeat = collector?.heartbeat, current = data?.day === diagnosticDay ? data : null;
  const freshHeartbeat = collector && !['unknown', 'stale'].includes(collector.status);
  const ctp = freshHeartbeat ? (heartbeat?.connected && heartbeat?.logged_in ? '已连接 / 已登录' : '未连接或未登录') : '未知';
  return <details className="diagnostics"><summary><span><strong>运行与数据诊断</strong><small>Collector / CTP / coverage / database / session</small></span><span className="disclosure">展开诊断</span></summary><div className="diagnostic-body">
    <section className="cards" aria-label="服务健康"><article><h2>Python API</h2><strong className={health ? 'good' : 'warn'}>{health ? '运行正常' : '不可达 / 状态未知'}</strong><p>{healthError || (health ? (health.data.readable ? '共享数据目录可读' : health.data.error) : '正在检查…')}</p></article><article><h2>C++ Collector</h2><strong className={collector?.status === 'healthy' ? 'good' : 'warn'}>{healthLabels[collector?.status] || '状态未知'}</strong><p>主循环：{collector?.process_alive ? '心跳有效' : '未确认存活'} · CTP：{ctp}</p><p>订阅 {freshHeartbeat ? `${number(heartbeat.subscribed)} / ${number(heartbeat.expected)}` : '—'}</p></article></section>
    <p className="muted">应用状态来自 API 与 Collector 心跳；休市无新行情不等于进程停止。</p>
    <section className="panel" aria-label="市场交易时段"><h2>市场交易时段</h2>{sessionsError && <p role="alert">市场时段读取失败：{sessionsError}。当前时段未知，未显示旧状态。</p>}{sessions && <div className="table-wrap"><table><thead><tr><th>交易所</th><th>品种</th><th>逻辑交易日</th><th>市场状态</th><th>日 / 夜盘</th><th>交易阶段</th><th>最近时段</th><th>下一时段</th></tr></thead><tbody>{sessions.markets?.map(row => <tr key={`${row.exchange}-${row.product}`} data-testid={`market-${row.exchange}-${row.product}`}><td>{row.exchange}</td><td>{row.product}</td><td>{row.trading_day || '未知'}</td><td>{marketLabels[row.market_state] || '未知'} ({row.market_state}){row.reason && <div>{row.reason}</div>}</td><td>{sessionLabels[row.session] || '—'}</td><td>{phaseLabels[row.phase] || '—'}</td><td>{period(row.latest_session)}</td><td>{period(row.next_session)}</td></tr>)}</tbody></table></div>}</section>
    <section className="panel" aria-label="多市场覆盖统计"><h2>多市场覆盖统计</h2>{coverageError && <p role="alert">覆盖统计读取失败：{coverageError}。未显示旧数据。</p>}{coverage && <><p className={coverage.complete ? 'good' : 'warn'}>{coverage.complete ? '全部目标订阅成功' : '覆盖尚未完整确认'}</p><div className="table-wrap"><table><thead><tr><th>交易所</th><th>品种</th><th>月份</th><th>发现 / 清单 / 目标</th><th>已订阅</th><th>失败</th><th>已接收</th><th>无推送</th><th>清单</th></tr></thead><tbody>{coverage.groups?.map(row => <tr key={`${row.exchange}-${row.product}-${row.month}`}><td>{row.exchange || 'CFFEX'}</td><td>{row.product}</td><td>{row.month}</td><td>{number(row.discovered)} / {number(row.listed)} / {number(row.target)}</td><td>{number(row.subscribed)}</td><td>{number(row.failed)}</td><td>{number(row.received)}</td><td>{row.no_push ? `已订阅暂无推送 (${number(row.no_push)})` : '0'}</td><td>{row.verified ? '官方已核对' : row.stale ? '清单缺失或过期' : '公开链条待核对'}</td></tr>)}</tbody></table></div></>}</section>
    <section className="panel"><div className="section-title"><h2>采集数据量</h2><label>交易日 <select aria-label="诊断交易日" value={diagnosticDay} onChange={event => setDiagnosticDay(event.target.value)}><option value="">请选择</option>{days.map(item => <option key={item.day} value={item.day}>{item.day}</option>)}</select></label></div>{daysError && <p role="alert">交易日列表读取失败：{daysError}</p>}{!daysError && !days.length && <p>暂无交易日文件。</p>}{dataError && <p role="alert">数据读取失败：{dataError}。未显示旧数据。</p>}<div className="metrics"><div><span>日 snapshot 行数</span><strong data-testid="rows">{number(current?.summary.rows)}</strong></div><div><span>文件 + WAL 占用</span><strong>{current ? `${(current.summary.size_bytes / 1048576).toFixed(2)} MiB` : '—'}</strong></div><div><span>本次运行接收 / 写入</span><strong>{freshHeartbeat ? `${number(heartbeat.accepted)} / ${number(heartbeat.written)}` : '—'}</strong></div></div><p className="muted">snapshot 是采样结果，不等于原始 tick。最后接收：{freshHeartbeat ? timestamp(heartbeat.last_received_us) : '未知'} · 刷新：{current ? timestamp(updated * 1000) : '暂无'}</p>{current && <p className="muted">最近 run 来源：{[...new Set(current.summary.runs.map(run => run.source))].join('、') || '暂无'}</p>}</section>
    <section className="panel"><h2>最近 20 条 snapshot</h2><div className="table-wrap"><table><thead><tr><th>合约</th><th>最新价</th><th>买一 / 卖一</th><th>成交量</th><th>接收时间</th></tr></thead><tbody>{current?.snapshots.rows.map(row => <tr key={row.id}><td>{row.InstrumentID}</td><td>{number(row.LastPrice)}</td><td>{number(row.BidPrice1)} / {number(row.AskPrice1)}</td><td>{number(row.Volume)}</td><td>{timestamp(row.received_us)}</td></tr>)}</tbody></table></div></section>
  </div></details>;
}

export default function App({ pollMs = 5000 }) {
  const [month, setMonth] = useState('');
  const [health, setHealth] = useState(null), [healthError, setHealthError] = useState(''); const [days, setDays] = useState([]), [daysError, setDaysError] = useState('');
  const [diagnosticDay, setDiagnosticDay] = useState(''), [data, setData] = useState(null), [dataError, setDataError] = useState(''), [updated, setUpdated] = useState(null);
  const [coverage, setCoverage] = useState(null), [coverageError, setCoverageError] = useState(''); const [sessions, setSessions] = useState(null), [sessionsError, setSessionsError] = useState('');
  const [latest, setLatest] = useState(null), [series, setSeries] = useState(null), [businessError, setBusinessError] = useState(''), [seriesError, setSeriesError] = useState(''), [businessLoading, setBusinessLoading] = useState(true);
  const [history, setHistory] = useState(null), [historyError, setHistoryError] = useState('');

  useEffect(() => { let cancelled = false, busy = false, controller; const refresh = async () => { if (busy) return; busy = true; controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 4000);
    const update = async (work, success, failure) => { try { const value = await work; if (!cancelled) success(value); } catch (error) { if (!cancelled) failure(error.name === 'AbortError' ? '请求超时' : error.message); } };
    try { await Promise.all([update(get('/api/sessions', controller.signal), value => { setSessions(value); setSessionsError(''); }, error => { setSessions(null); setSessionsError(error); }), update(get('/api/coverage', controller.signal), value => { setCoverage(value); setCoverageError(''); }, error => { setCoverage(null); setCoverageError(error); }), update(get('/api/health', controller.signal), value => { setHealth(value); setHealthError(''); }, error => { setHealth(null); setHealthError(error); }), update(get('/api/days', controller.signal), value => { setDays(value.days); setDaysError(''); if (!diagnosticDay && value.days.length) setDiagnosticDay(value.days[0].day); }, error => { setDays([]); setDaysError(error); }), ...(diagnosticDay ? [update(Promise.all([get(`/api/summary?day=${encodeURIComponent(diagnosticDay)}`, controller.signal), get(`/api/snapshots?day=${encodeURIComponent(diagnosticDay)}&limit=20`, controller.signal)]), ([summary, snapshots]) => { setData({ day: diagnosticDay, summary, snapshots }); setDataError(''); setUpdated(Date.now()); }, error => { setData(null); setDataError(error); })] : [])]); } finally { clearTimeout(timeout); busy = false; }
  }; refresh(); const timer = setInterval(refresh, pollMs); return () => { cancelled = true; clearInterval(timer); controller?.abort(); }; }, [diagnosticDay, pollMs]);

  const moMonths = useMemo(() => [...new Set((coverage?.groups || []).filter(row => row.product === 'MO' && row.month).map(row => row.month))].sort(), [coverage]);
  useEffect(() => { if (!month && moMonths.length) setMonth(moMonths[0]); }, [month, moMonths]);
  useEffect(() => { let cancelled = false, busy = false, controller; setLatest(null); setSeries(null); setBusinessError(''); setSeriesError(''); setHistory(null); setHistoryError(''); setBusinessLoading(true);
    const refresh = async () => { if (busy) return; busy = true; controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 4000);
      try { const current = await get(`/api/skew/latest?${query({ month })}`, controller.signal); if (cancelled) return; setLatest(current); setBusinessError(''); setBusinessLoading(false); if (current.scope?.trading_day) { try { const daily = await get(`/api/skew/series?${query({ day: current.scope.trading_day, month })}`, controller.signal); if (!cancelled) { setSeries(daily); setSeriesError(''); } } catch (error) { if (!cancelled) { setSeries(null); setSeriesError(error.name === 'AbortError' ? '请求超时' : error.message); } } } else { setSeries(null); setSeriesError(''); }
      } catch (error) { if (!cancelled) { setLatest(null); setSeries(null); setBusinessError(error.name === 'AbortError' ? '请求超时' : error.message); setSeriesError(''); setBusinessLoading(false); } } finally { clearTimeout(timeout); busy = false; }
    }; refresh(); const timer = setInterval(refresh, pollMs); return () => { cancelled = true; clearInterval(timer); controller?.abort(); }; }, [month, pollMs]);

  const displayed = history || latest;
  return <main><header><div><p className="eyebrow">DERIVATIVES MONITOR</p><h1>MO Skew 业务汇报</h1></div><div className="month-control"><label htmlFor="month">MO 到期月</label><select id="month" aria-label="MO 到期月" value={month} onChange={event => setMonth(event.target.value)}><option value="">服务默认月</option>{moMonths.map(value => <option key={value} value={value}>MO{value}</option>)}</select><span>每 5 秒刷新 · 北京时间</span></div></header>
    <BusinessReport result={displayed} series={history ? null : series} loading={businessLoading && !history} error={historyError || businessError} seriesError={history ? '' : seriesError} view={history ? 'history' : 'current'} onCurrent={() => { setHistory(null); setHistoryError(''); }} />
    <section className="panel review" aria-label="分钟回看"><div className="section-title"><div><p className="kicker">当日走势与回看</p><h2>指定一个已封口的连续交易分钟</h2></div><span className="muted">历史结果始终标记为历史，不会显示为当前值。</span></div><HistoryControls days={days} month={month} onResult={setHistory} onError={setHistoryError} /><Trend series={series} selectedMinute={history?.minute} /></section>
    <Diagnostics {...{ health, healthError, days, daysError, diagnosticDay, setDiagnosticDay, data, dataError, updated, coverage, coverageError, sessions, sessionsError }} />
  </main>;
}
