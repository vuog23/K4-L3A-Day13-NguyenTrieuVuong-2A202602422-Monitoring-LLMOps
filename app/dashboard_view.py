from __future__ import annotations


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Day 13 Observability Dashboard</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, Segoe UI, Arial, sans-serif; background: #0c1422; color: #edf4ff; }
    * { box-sizing: border-box; }
    body { margin: 0; padding: 28px; }
    header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 20px; }
    h1 { font-size: 26px; margin: 0 0 8px; }
    .subtitle, .muted { color: #a7b8cc; font-size: 13px; }
    .pill { background: #162b43; border: 1px solid #35506b; border-radius: 999px; padding: 8px 12px; white-space: nowrap; font-size: 13px; }
    .slo { display: flex; gap: 12px; flex-wrap: wrap; margin: 0 0 18px; }
    .slo .pill { border-radius: 10px; }
    main { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
    article { min-width: 0; background: #132238; border: 1px solid #28425e; border-radius: 14px; padding: 18px; }
    h2 { font-size: 16px; margin: 0 0 5px; }
    .unit { color: #8fa6bf; font-size: 12px; margin-bottom: 14px; }
    .metrics { display: flex; flex-wrap: wrap; gap: 12px 20px; min-height: 54px; align-items: baseline; }
    .metric { font-size: 12px; color: #a7b8cc; }
    .metric strong { display: block; color: #f3f8ff; font-size: 21px; font-weight: 650; margin-top: 2px; }
    .chart { width: 100%; height: 150px; margin-top: 10px; display: block; }
    .threshold { border-top: 1px solid #28425e; padding-top: 9px; margin-top: 8px; color: #d8b877; font-size: 12px; }
    .legend { display: flex; gap: 12px; flex-wrap: wrap; color: #a7b8cc; font-size: 11px; }
    .legend span::before { content: ''; display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; background: var(--color); }
    footer { margin-top: 18px; color: #8fa6bf; font-size: 12px; }
    @media (max-width: 1100px) { main { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 680px) { body { padding: 14px; } header { display: block; } main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <div><h1>Day 13 · Monitoring &amp; LLMOps</h1><div class="subtitle">Six live panels from <code>data/logs.jsonl</code> · Metrics → Logs → Traces</div></div>
    <div id="window" class="pill">Loading 60-minute window…</div>
  </header>
  <div class="slo" id="slo"></div>
  <main id="panels"></main>
  <footer id="footer">Loading dashboard data…</footer>
  <script>
    const colors = ['#5ed4f4', '#b59aff', '#67d7a4'];
    const labelMap = {
      p50: 'P50', p95: 'P95', p99: 'P99', ttft_p95: 'TTFT P95',
      count: 'Requests', rate_per_minute: 'Current req/min',
      error_rate_pct: 'Error rate', tool_success_rate_pct: 'Retrieval success',
      total: 'Total cost', tokens_in: 'Input', tokens_out: 'Output', mean: 'Mean score'
    };
    function fmt(value, unit, key) {
      if (value === null || value === undefined) return '—';
      if (unit === 'usd') return '$' + Number(value).toFixed(4);
      if (unit === 'percent' || key.endsWith('_pct')) return Number(value).toFixed(1) + '%';
      if (unit === 'score_0_to_1') return Number(value).toFixed(3);
      if (unit === 'ms') return Number(value).toFixed(0) + ' ms';
      return Number(value).toLocaleString();
    }
    function chart(series, threshold, minutes) {
      const entries = Object.entries(series);
      const values = entries.flatMap(([, data]) => data.filter(value => value !== null));
      const maxValue = Math.max(1, ...values);
      const yMax = Math.max(maxValue * 1.15, threshold.value <= maxValue * 1.4 ? threshold.value * 1.08 : 0);
      const x = index => 34 + index * 476 / Math.max(minutes.length - 1, 1);
      const y = value => 128 - value / yMax * 108;
      const thresholdY = threshold.value > yMax ? 20 : y(threshold.value);
      const lines = entries.map(([name, data], index) => {
        let paths = [], run = [];
        data.forEach((value, point) => {
          if (value === null) { if (run.length) paths.push(run.join(' ')); run = []; }
          else run.push(`${x(point).toFixed(1)},${y(value).toFixed(1)}`);
        });
        if (run.length) paths.push(run.join(' '));
        return paths.map(points => `<polyline points="${points}" fill="none" stroke="${colors[index]}" stroke-width="2.5" stroke-linejoin="round"/>`).join('');
      }).join('');
      return `<svg class="chart" viewBox="0 0 540 150" role="img" aria-label="60-minute time series">
        <line x1="34" y1="128" x2="510" y2="128" stroke="#496078"/>
        <line x1="34" y1="${thresholdY}" x2="510" y2="${thresholdY}" stroke="#d8b877" stroke-width="1.5" stroke-dasharray="5 5"/>
        ${lines}
        <text x="34" y="146" fill="#91a8c0" font-size="10">${minutes[0]}</text>
        <text x="472" y="146" fill="#91a8c0" font-size="10">${minutes[minutes.length - 1]} UTC</text>
      </svg>`;
    }
    function card(panel, minutes) {
      const article = document.createElement('article');
      const metrics = Object.entries(panel.metrics)
        .filter(([key]) => key !== 'error_breakdown')
        .map(([key, value]) => `<div class="metric">${labelMap[key] || key}<strong>${fmt(value, panel.unit, key)}</strong></div>`).join('');
      const breakdown = panel.metrics.error_breakdown
        ? `<div class="muted">Error types: ${Object.entries(panel.metrics.error_breakdown).map(([key, value]) => `${key}: ${value}`).join(', ') || 'none'}</div>` : '';
      const legend = Object.keys(panel.series).map((key, index) => `<span style="--color:${colors[index]}">${labelMap[key] || key}</span>`).join('');
      const t = panel.threshold;
      article.innerHTML = `<h2>${panel.title}</h2><div class="unit">Unit: ${panel.unit}</div><div class="metrics">${metrics}</div>${breakdown}
        ${chart(panel.series, t, minutes)}<div class="legend">${legend}</div>
        <div class="threshold">Threshold / SLO line: ${labelMap[t.aggregation] || t.aggregation} ${t.operator === 'lte' ? '≤' : '≥'} ${fmt(t.value, panel.unit, t.aggregation)}</div>`;
      return article;
    }
    async function refresh() {
      try {
        const response = await fetch('/dashboard/data', {cache: 'no-store'});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        document.getElementById('window').textContent = `Last ${data.time_range_minutes} minutes · ${new Date(data.window_start).toISOString().slice(11, 16)}–${new Date(data.generated_at).toISOString().slice(11, 16)} UTC`;
        const slo = data.slo;
        document.getElementById('slo').innerHTML = `<div class="pill">SLO ${slo.name}: <strong>${fmt(slo.actual_percent, 'percent', 'actual_pct')}</strong> / ${slo.target_percent}% target</div><div class="pill">Good requests: <strong>${slo.good_requests}/${slo.total_requests}</strong></div><div class="pill">Remaining error budget: <strong>${slo.remaining_budget_requests}</strong> requests</div>`;
        const container = document.getElementById('panels');
        container.replaceChildren(...data.panels.map(panel => card(panel, data.minutes)));
        document.getElementById('footer').textContent = `Updated ${new Date(data.generated_at).toISOString()} · Refresh every ${data.refresh_seconds} seconds · Source: data/logs.jsonl`;
        if (!window.dashboardRefreshSet) { window.dashboardRefreshSet = true; setInterval(refresh, data.refresh_seconds * 1000); }
      } catch (error) { document.getElementById('footer').textContent = `Dashboard refresh failed: ${error}`; }
    }
    refresh();
  </script>
</body>
</html>"""
