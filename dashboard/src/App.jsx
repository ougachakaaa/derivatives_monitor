import React, { useEffect, useState } from 'react';

const number = value => value == null ? '—' : Number(value).toLocaleString('zh-CN');
const timestamp = value => value ? new Date(value / 1000).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '暂无';
const labels = { healthy: '运行正常', degraded: '连接或订阅异常', starting: '启动中', stopped: '已停止', failed: '运行失败', stale: '心跳已过期', unknown: '状态未知' };

async function get(path, signal) {
  const response = await fetch(path, { signal, cache: 'no-store' });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
  return body;
}

// Each resource has its own failure state. No successful old response stays green
// after a failed refresh; a day switch aborts all requests from the previous day.
export default function App({ pollMs = 5000 }) {
  const [day, setDay] = useState('');
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState('');
  const [days, setDays] = useState([]);
  const [daysError, setDaysError] = useState('');
  const [data, setData] = useState(null);
  const [dataError, setDataError] = useState('');
  const [updated, setUpdated] = useState(null);

  useEffect(() => {
    let cancelled = false;
    let busy = false;
    let controller;
    setData(null);
    setDataError('');
    const refresh = async () => {
      if (busy) return;
      busy = true;
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 4000);
      const update = async (work, success, failure) => {
        try { const value = await work; if (!cancelled) success(value); }
        catch (error) { if (!cancelled) failure(error.name === 'AbortError' ? '请求超时' : error.message); }
      };
      try {
        await Promise.all([
          update(get('/api/health', controller.signal), value => { setHealth(value); setHealthError(''); }, error => { setHealth(null); setHealthError(error); }),
          update(get('/api/days', controller.signal), value => {
            setDays(value.days); setDaysError('');
            if (!day && value.days.length) setDay(value.days[0].day);
          }, error => { setDays([]); setDaysError(error); }),
          ...(day ? [update(Promise.all([
            get(`/api/summary?day=${encodeURIComponent(day)}`, controller.signal),
            get(`/api/snapshots?day=${encodeURIComponent(day)}&limit=20`, controller.signal),
          ]), ([summary, snapshots]) => { setData({ day, summary, snapshots }); setDataError(''); setUpdated(Date.now()); }, error => { setData(null); setDataError(error); })] : []),
        ]);
      } finally { clearTimeout(timeout); busy = false; }
    };
    refresh();
    const timer = setInterval(refresh, pollMs);
    return () => { cancelled = true; clearInterval(timer); controller?.abort(); };
  }, [day, pollMs]);

  const collector = health?.collector;
  const heartbeat = collector?.heartbeat;
  const current = data?.day === day ? data : null;
  const freshHeartbeat = collector && !['unknown', 'stale'].includes(collector.status);
  const ctp = freshHeartbeat ? (heartbeat?.connected && heartbeat?.logged_in ? '已连接 / 已登录' : '未连接或未登录') : '未知';

  return <main>
    <header><div><p className="eyebrow">DERIVATIVES MONITOR</p><h1>采集运行看板</h1></div><span className="muted">每 5 秒刷新 · 北京时间</span></header>
    <section className="cards" aria-label="服务健康">
      <article><h2>Python API</h2><strong className={health ? 'good' : 'warn'}>{health ? '运行正常' : '不可达 / 状态未知'}</strong><p>{healthError || (health ? (health.data.readable ? '共享数据目录可读' : health.data.error) : '正在检查…')}</p></article>
      <article><h2>C++ Collector</h2><strong className={collector?.status === 'healthy' ? 'good' : 'warn'}>{labels[collector?.status] || '状态未知'}</strong><p>主循环：{collector?.process_alive ? '心跳有效' : '未确认存活'} · CTP：{ctp}</p><p>订阅 {freshHeartbeat ? `${number(heartbeat.subscribed)} / ${number(heartbeat.expected)}` : '—'}</p></article>
    </section>
    <p className="muted">应用状态来自 API 与 Collector 心跳；休市无新行情不等于进程停止。</p>
    <section className="panel">
      <div className="section-title"><h2>采集数据量</h2><label>交易日 <select aria-label="交易日" value={day} onChange={event => setDay(event.target.value)}><option value="">请选择</option>{days.map(item => <option key={item.day} value={item.day}>{item.day}</option>)}</select></label></div>
      {daysError && <p role="alert">交易日列表读取失败：{daysError}</p>}
      {!daysError && !days.length && <p>暂无交易日文件，等待 Collector 写入。</p>}
      {dataError && <p role="alert">数据读取失败：{dataError}。未显示旧数据。</p>}
      <div className="metrics"><div><span>日 snapshot 行数</span><strong data-testid="rows">{number(current?.summary.rows)}</strong></div><div><span>文件 + WAL 占用</span><strong>{current ? `${(current.summary.size_bytes / 1048576).toFixed(2)} MiB` : '—'}</strong></div><div><span>本次运行接收 / 写入</span><strong>{freshHeartbeat ? `${number(heartbeat.accepted)} / ${number(heartbeat.written)}` : '—'}</strong></div></div>
      <p className="muted">snapshot 是采样结果，不等于原始 tick。最后接收：{freshHeartbeat ? timestamp(heartbeat.last_received_us) : '未知'} · 数据刷新：{current ? timestamp(updated * 1000) : '暂无'}</p>
      {current && <><div className="table-wrap"><table><thead><tr><th>合约</th><th>snapshot 行数</th><th>最近接收时间</th></tr></thead><tbody>{current.summary.instruments.map(item => <tr key={item.instrument}><td>{item.instrument}</td><td>{number(item.rows)}</td><td>{timestamp(item.last_received_us)}</td></tr>)}</tbody></table></div>{current.summary.rows === 0 && <p>该日数据库有效，暂时没有 snapshot。</p>}<p className="muted">最近 run 来源：{[...new Set(current.summary.runs.map(run => run.source))].join('、') || '暂无'}</p></>}
    </section>
    <section className="panel"><h2>最近 20 条 snapshot</h2><div className="table-wrap"><table><thead><tr><th>合约</th><th>最新价</th><th>买一 / 卖一</th><th>成交量</th><th>接收时间</th></tr></thead><tbody>{current?.snapshots.rows.map(row => <tr key={row.id}><td>{row.InstrumentID}</td><td>{number(row.LastPrice)}</td><td>{number(row.BidPrice1)} / {number(row.AskPrice1)}</td><td>{number(row.Volume)}</td><td>{timestamp(row.received_us)}</td></tr>)}</tbody></table></div></section>
  </main>;
}
