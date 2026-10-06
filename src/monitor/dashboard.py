##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Dashboard: the metrics as one HTML page, whole in its file (no server, no internet): open it in a browser
##
import json

def render(payload: dict) -> str:
    """ The page of the payload made by report: the metrics of each period, and the drift alerts """
    # In a <script> tag, "</script>" in a message of the model would end the data: no "<" is left as it is
    data: str = json.dumps(payload, ensure_ascii=False, default=str).replace("<", "\\u003c")
    return PAGE.replace("__DATA__", data)

PAGE: str = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Louis monitoring</title>
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11, 11, 11, 0.10); --wash: rgba(11, 11, 11, 0.04);
  --s1: #2a78d6; --s2: #eb6834;
  --good: #0ca30c; --good-text: #006300; --warning: #fab219; --critical: #d03b3b;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255, 255, 255, 0.10); --wash: rgba(255, 255, 255, 0.05);
    --s1: #3987e5; --s2: #d95926; --good-text: #0ca30c; --critical: #e66767;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255, 255, 255, 0.10); --wash: rgba(255, 255, 255, 0.05);
  --s1: #3987e5; --s2: #d95926; --good-text: #0ca30c; --critical: #e66767;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1180px; margin: 0 auto; padding: 28px 16px 56px; }
h1 { font-size: 22px; font-weight: 600; margin: 0 0 4px; }
h2 { font-size: 15px; font-weight: 600; margin: 0; }
.meta, .note { color: var(--ink-2); margin: 0; }
.note { font-size: 13px; }
code { font: 12.5px ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
section { margin-top: 24px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; min-width: 0; }
.card > header { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 4px 16px; margin-bottom: 8px; }

/* Drift alerts: an icon and a word carry the status, the color only backs them */
.alerts { display: grid; gap: 10px; }
.alert { display: grid; grid-template-columns: 22px 1fr; gap: 2px 10px; border-left: 3px solid var(--muted); }
.alert.warn { border-left-color: var(--warning); }
.alert.info { border-left-color: var(--s1); }
.alert.good { border-left-color: var(--good); }
.alert .icon { font-size: 16px; line-height: 20px; text-align: center; }
.alert.warn .icon { color: var(--warning); }
.alert.good .icon { color: var(--good); }
.alert.info .icon { color: var(--s1); }
.alert h3 { font-size: 14px; font-weight: 600; margin: 0; }
.alert ul { list-style: none; margin: 6px 0 0; padding: 0; display: grid; gap: 2px; }
.alert li { display: flex; flex-wrap: wrap; gap: 4px 10px; }
.alert li .what { color: var(--ink-2); min-width: 170px; }
.alert li .values { font-variant-numeric: tabular-nums; }
.delta { font-weight: 600; font-variant-numeric: tabular-nums; }
.delta.bad { color: var(--critical); }
.delta.better { color: var(--good-text); }
.delta.neutral { color: var(--ink-2); }

/* Filters: one row, above everything they scope */
.filters { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin-top: 28px; }
.segmented { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; padding: 2px; background: var(--surface); }
.segmented button { font: inherit; color: var(--ink-2); background: none; border: 0; border-radius: 6px; padding: 5px 12px; cursor: pointer; }
.segmented button:hover { background: var(--wash); }
.segmented button[aria-pressed="true"] { color: var(--ink); background: var(--wash); font-weight: 600; box-shadow: inset 0 0 0 1px var(--border); }
.segmented button:focus-visible, svg:focus-visible, summary:focus-visible { outline: 2px solid var(--s1); outline-offset: 2px; }

.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-top: 14px; }
.kpi .label { color: var(--ink-2); font-size: 13px; }
.kpi .value { font-size: 26px; font-weight: 600; margin: 2px 0; letter-spacing: -0.01em; }
.kpi .sub { color: var(--ink-2); font-size: 12.5px; }

.charts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.charts .wide { grid-column: 1 / -1; }
@media (max-width: 760px) { .charts { grid-template-columns: minmax(0, 1fr); } }
.legend { display: flex; flex-wrap: wrap; gap: 4px 14px; color: var(--ink-2); font-size: 12.5px; }
.key { display: inline-flex; align-items: center; gap: 6px; }
.key i { display: inline-block; width: 14px; height: 2px; border-radius: 1px; }
.key i.box { width: 10px; height: 10px; border-radius: 2px; }
.key i.rule { width: 1px; height: 12px; background: var(--ink-2); }
.plot { position: relative; }
.plot svg { display: block; width: 100%; height: auto; overflow: visible; }
.grid { stroke: var(--grid); stroke-width: 1; }
.axis { stroke: var(--axis); stroke-width: 1; }
.tick { fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.mark { stroke: var(--ink-2); stroke-width: 1; opacity: 0.55; }
.mark-label { fill: var(--ink-2); font-size: 11px; }
.end-label { fill: var(--ink-2); font-size: 11px; font-variant-numeric: tabular-nums; }
.crosshair { stroke: var(--ink-2); stroke-width: 1; }
.empty { color: var(--muted); padding: 40px 0; text-align: center; }
.tip { position: absolute; pointer-events: none; z-index: 2; min-width: 150px; background: var(--surface); color: var(--ink);
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 12.5px; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12); }
.tip[hidden] { display: none; }
.tip .when { color: var(--ink-2); margin-bottom: 4px; }
.tip .row { display: flex; align-items: center; gap: 8px; }
.tip .row strong { font-variant-numeric: tabular-nums; }
.tip .row span { color: var(--ink-2); }

.tables { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
@media (max-width: 760px) { .tables { grid-template-columns: minmax(0, 1fr); } }
.scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; font-weight: 600; color: var(--ink-2); padding: 6px 10px 6px 0; border-bottom: 1px solid var(--axis); white-space: nowrap; }
td { padding: 6px 10px 6px 0; border-bottom: 1px solid var(--grid); vertical-align: top; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
td .dim { color: var(--ink-2); display: block; font-size: 12px; max-width: 360px; overflow-wrap: anywhere; }
td .finding { white-space: nowrap; }
td.text { max-width: 420px; overflow-wrap: anywhere; color: var(--ink-2); }
.badge { display: inline-block; font-size: 11.5px; padding: 0 6px; border-radius: 4px; background: var(--wash); color: var(--ink-2); }
.bar { display: inline-block; height: 8px; border-radius: 0 2px 2px 0; background: var(--s1); vertical-align: middle; margin-right: 6px; }
details summary { cursor: pointer; font-weight: 600; }
details[open] summary { margin-bottom: 10px; }
</style>
</head>
<body>
<main>
  <header>
    <h1>Louis monitoring</h1>
    <p class="meta" id="meta"></p>
  </header>

  <section aria-labelledby="alerts-title">
    <h2 id="alerts-title">Drift</h2>
    <p class="note">Each new prompt or model against the one it replaced, and the last 24 h against the week before, over the whole history.</p>
    <div class="alerts" id="alerts" style="margin-top: 10px"></div>
  </section>

  <div class="filters">
    <div class="segmented" role="group" aria-label="Period" id="ranges"></div>
    <p class="note" id="period"></p>
  </div>

  <div class="kpis" id="kpis"></div>

  <section class="charts" id="charts">
    <figure class="card wide" id="chart-latency" style="margin: 0">
      <header><h2>Latency per model call</h2><div class="legend"></div></header>
      <p class="note">Seconds from the request to the end of the reply. Vertical lines: a new prompt or model.</p>
      <div class="plot"></div>
    </figure>
    <figure class="card" id="chart-volume" style="margin: 0">
      <header><h2>Call volume</h2><div class="legend"></div></header>
      <p class="note">Requests to the model.</p>
      <div class="plot"></div>
    </figure>
    <figure class="card" id="chart-errors" style="margin: 0">
      <header><h2>Error rate</h2><div class="legend"></div></header>
      <p class="note">Failed model calls, and answers that ended badly.</p>
      <div class="plot"></div>
    </figure>
    <figure class="card" id="chart-prompt" style="margin: 0">
      <header><h2>Prompt tokens per call</h2><div class="legend"></div></header>
      <p class="note">What the model reads: system prompt, tools, history.</p>
      <div class="plot"></div>
    </figure>
    <figure class="card" id="chart-reply" style="margin: 0">
      <header><h2>Reply tokens per call</h2><div class="legend"></div></header>
      <p class="note">What the model writes.</p>
      <div class="plot"></div>
    </figure>
  </section>

  <section class="card">
    <details>
      <summary>Chart data as a table</summary>
      <div class="scroll"><table id="series-table"></table></div>
    </details>
  </section>

  <section class="card">
    <header><h2>Prompts and models</h2></header>
    <p class="note">The calls grouped by what they ran on, newest first. Each one is compared with the one it took over from (thinking the same way).</p>
    <div class="scroll"><table id="configurations"></table></div>
  </section>

  <div class="tables">
    <section class="card">
      <header><h2>Tools</h2></header>
      <div class="scroll"><table id="tools"></table></div>
    </section>
    <section class="card">
      <header><h2>Answers by outcome</h2></header>
      <div class="scroll"><table id="outcomes"></table></div>
    </section>
  </div>

  <section class="card">
    <header><h2>Slowest calls</h2></header>
    <p class="note">What the model was last given is often why: a big file read, a long history.</p>
    <div class="scroll"><table id="slowest"></table></div>
  </section>

  <section class="card">
    <header><h2>Recent problems</h2></header>
    <div class="scroll"><table id="problems"></table></div>
  </section>
</main>

<script type="application/json" id="data">__DATA__</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("data").textContent);
const SVG = "http://www.w3.org/2000/svg";

/* Every text of the data goes in with textContent: the replies and the files read are not markup */
function el(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child != null) node.append(child);
  return node;
}
function svg(tag, attrs) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, value);
  return node;
}

const fmt = {
  seconds(v) {
    if (v == null) return "–";
    if (v < 1) return Math.round(v * 1000) + " ms";
    if (v < 10) return v.toFixed(2) + " s";
    if (v < 100) return v.toFixed(1) + " s";
    return Math.round(v).toLocaleString("en-US") + " s";
  },
  secondsTick(v) { return v === 0 ? "0" : v < 1 ? Math.round(v * 1000) + " ms" : +v.toFixed(2) + " s"; },
  percent(v, digits = 1) { return v == null ? "–" : (v * 100).toFixed(digits) + "%"; },
  percentTick(v) { return +(v * 100).toFixed(1) + "%"; },
  count(v) { return v == null ? "–" : Math.round(v).toLocaleString("en-US"); },
  compact(v) { return v >= 10000 ? +(v / 1000).toFixed(1) + "K" : Math.round(v).toLocaleString("en-US"); },
  date(iso) { return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" }); },
  when(iso) {
    return iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "–";
  },
  hour(iso) { return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }); },
};

const METRICS = {
  latency:           { label: "Median latency", value: fmt.seconds },
  prompt_tokens:     { label: "Prompt tokens per call", value: fmt.count },
  completion_tokens: { label: "Reply tokens per call", value: fmt.count },
  error_rate:        { label: "Error rate", value: v => fmt.percent(v) },
};

/* A change, signed, with an arrow: its color is never the only sign of it */
function delta(finding) {
  const up = finding.after > finding.before;
  const text = finding.metric === "error_rate"
    ? (up ? "+" : "−") + Math.abs((finding.after - finding.before) * 100).toFixed(1) + " pts"
    : (up ? "+" : "−") + Math.abs(finding.change * 100).toFixed(0) + "%";
  const tone = finding.bad ? "bad" : (finding.metric === "latency" || finding.metric === "error_rate") ? "better" : "neutral";
  return el("span", { class: "delta " + tone, text: (up ? "▲ " : "▼ ") + text });
}

function renderAlerts() {
  const root = document.getElementById("alerts");
  root.replaceChildren();
  if (!DATA.alerts.length) {
    root.append(el("div", { class: "card alert good" },
      el("span", { class: "icon", "aria-hidden": "true", text: "✓" }),
      el("div", {},
        el("h3", { text: "No drift past the thresholds" }),
        el("p", { class: "note", text: DATA.thresholds }))));
    return;
  }
  for (const alert of DATA.alerts) {
    const title = alert.kind === "recent" ? "Last 24 h against the 7 days before" : alert.title;
    const since = alert.kind === "recent" ? "" : "since " + fmt.when(alert.since) + " · ";
    const list = el("ul");
    for (const finding of alert.findings) {
      const metric = METRICS[finding.metric];
      list.append(el("li", {},
        el("span", { class: "what", text: metric.label }),
        el("span", { class: "values", text: metric.value(finding.before) + " → " + metric.value(finding.after) }),
        delta(finding)));
    }
    root.append(el("div", { class: "card alert " + alert.level },
      el("span", { class: "icon", "aria-hidden": "true", text: alert.level === "warn" ? "⚠" : "ℹ" }),
      el("div", {},
        el("h3", { text: (alert.level === "warn" ? "Worse: " : "Changed: ") + title }),
        el("p", { class: "note", text: since + "compared on " + fmt.count(alert.calls[0]) + " → " + fmt.count(alert.calls[1]) + " calls" }),
        list)));
  }
}

function renderKpis(s) {
  const tiles = [
    ["Model calls", fmt.count(s.calls.calls), s.runs + (s.runs === 1 ? " run" : " runs") + " of louis"],
    ["Median latency", fmt.seconds(s.calls.p50), "p95 " + fmt.seconds(s.calls.p95) + " · first token " + fmt.seconds(s.calls.ttft)],
    ["Error rate", fmt.percent(s.calls.error_rate), fmt.count(s.calls.errors) + " failed " + (s.calls.errors === 1 ? "call" : "calls")],
    ["Prompt tokens per call", fmt.count(s.calls.prompt_tokens),
      fmt.count(s.calls.completion_tokens) + " reply · " + (s.calls.speed ? s.calls.speed.toFixed(1) + " tok/s" : "–")],
    ["Answers", fmt.count(s.turns.turns), "median " + fmt.seconds(s.turns.p50) + " · " + fmt.percent(s.turns.failure_rate) + " failed"],
    ["Tool calls", fmt.count(s.tools.calls), fmt.percent(s.tools.calls ? s.tools.errors / s.tools.calls : null) + " could not do it"],
  ];
  // Only once JSON replies were asked (/json, louis --ask): most runs never do
  if (s.structured && s.structured.replies) {
    tiles.push(["JSON replies", fmt.percent(s.structured.valid_rate) + " valid",
      fmt.count(s.structured.replies) + " asked · " + fmt.percent(s.structured.first_try_rate) + " at once"]);
  }
  document.getElementById("kpis").replaceChildren(...tiles.map(([label, value, sub]) =>
    el("div", { class: "card kpi" }, el("div", { class: "label", text: label }), el("div", { class: "value", text: value }),
      el("div", { class: "sub", text: sub }))));
}

function niceTicks(max, count) {
  const raw = max / count;
  const power = 10 ** Math.floor(Math.log10(raw));
  const f = raw / power;
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * power;
  const ticks = [];
  for (let v = 0; v <= Math.ceil(max / step - 1e-9) * step + step / 2; v += step) ticks.push(+v.toFixed(10));
  return ticks;
}

function bucketLabel(iso, by) {
  const at = new Date(iso);
  return by === "day" || at.getHours() === 0 ? fmt.date(iso) : fmt.hour(iso);
}

/* A time chart, one scale: lines (spanning the empty periods, with dots on the real points when few) or stacked columns */
function chart(id, s, opts) {
  const card = document.getElementById(id);
  const plot = card.querySelector(".plot");
  const legend = card.querySelector(".legend");
  legend.replaceChildren();
  if (opts.series.length > 1 || opts.marks) {
    for (const serie of opts.series) {
      const key = el("i", { class: opts.kind === "stack" ? "box" : "" });
      key.style.background = serie.color;
      legend.append(el("span", { class: "key" }, key, document.createTextNode(serie.label)));
    }
    if (opts.marks && s.marks.length) legend.append(el("span", { class: "key" }, el("i", { class: "rule" }), document.createTextNode("new prompt or model")));
  }
  const points = s.series;
  const values = points.map(p => opts.kind === "stack"
    ? opts.series.reduce((sum, serie) => sum + (p[serie.key] || 0), 0)
    : Math.max(...opts.series.map(serie => p[serie.key] ?? 0)));
  const real = points.filter(p => opts.series.some(serie => p[serie.key] != null && (opts.kind !== "stack" || p[serie.key] > 0)));
  plot.replaceChildren();
  if (!real.length) { plot.append(el("div", { class: "empty", text: "No calls in this period." })); return; }

  const width = Math.max(plot.clientWidth, 280), height = opts.height || 220;
  const labelled = opts.kind === "line";
  const m = { top: 20, right: labelled ? 76 : 12, bottom: 26, left: 56 };
  const w = width - m.left - m.right, h = height - m.top - m.bottom;
  const band = w / points.length;
  const x = i => m.left + band * (i + 0.5);
  const ticks = niceTicks(Math.max(...values, opts.floor || 0) || 1, 4);
  const top = ticks[ticks.length - 1];
  const y = v => m.top + h - (v / top) * h;

  const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, width, height, role: "img", tabindex: "0",
    "aria-label": card.querySelector("h2").textContent + ": use the arrow keys to read the values, or open the data table" });
  for (const t of ticks) {
    root.append(svg("line", { class: t === 0 ? "axis" : "grid", x1: m.left, x2: width - m.right, y1: y(t), y2: y(t) }));
    const tick = svg("text", { class: "tick", x: m.left - 8, y: y(t), "text-anchor": "end", "dominant-baseline": "middle" });
    tick.textContent = opts.tick(t);
    root.append(tick);
  }
  const every = Math.max(1, Math.ceil(points.length / Math.max(1, Math.floor(w / 72))));
  for (let i = 0; i < points.length; i += every) {
    const label = svg("text", { class: "tick", x: x(i), y: height - 6, "text-anchor": "middle" });
    label.textContent = bucketLabel(points[i].t, s.by);
    root.append(label);
  }

  // Where a prompt or a model changed: in the period it first answered
  if (opts.marks) {
    const times = points.map(p => new Date(p.t).getTime());
    let lastLabel = -Infinity;
    for (const mark of s.marks) {
      const at = new Date(mark.t).getTime();
      let i = times.findIndex((t, k) => t <= at && (k === times.length - 1 || times[k + 1] > at));
      if (i < 0) continue;
      root.append(svg("line", { class: "mark", x1: x(i), x2: x(i), y1: m.top - 4, y2: m.top + h }));
      if (opts.markLabels && x(i) - lastLabel > 90) {
        // Near the right end, the label goes left of its line: the ends of the lines are labelled there
        const right = x(i) > width - m.right - 110;
        const label = svg("text", { class: "mark-label", x: x(i) + (right ? -4 : 4), y: m.top - 8, "text-anchor": right ? "end" : "start" });
        label.textContent = "prompt " + (mark.prompt || "?");
        root.append(label);
        lastLabel = x(i);
      }
    }
  }

  if (opts.kind === "stack") {
    const bar = Math.max(2, Math.min(24, band * 0.7));
    points.forEach((p, i) => {
      let base = 0;
      const filled = opts.series.filter(serie => p[serie.key] > 0);
      filled.forEach((serie, k) => {
        const y0 = y(base) - (k > 0 ? 2 : 0), y1 = y(base + p[serie.key]);
        base += p[serie.key];
        if (y0 - y1 < 0.5) return;
        const r = k === filled.length - 1 ? Math.min(4, bar / 2, y0 - y1) : 0;
        const left = x(i) - bar / 2, right = left + bar;
        root.append(svg("path", { fill: serie.color,
          d: `M${left},${y0}V${y1 + r}Q${left},${y1} ${left + r},${y1}H${right - r}Q${right},${y1} ${right},${y1 + r}V${y0}Z` }));
      });
    });
  } else {
    const ends = [];
    for (const serie of opts.series) {
      const pts = points.map((p, i) => [i, p[serie.key]]).filter(([, v]) => v != null);
      if (!pts.length) continue;
      root.append(svg("path", { fill: "none", stroke: serie.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round",
        d: pts.map(([i, v], k) => (k ? "L" : "M") + x(i) + "," + y(v)).join("") }));
      const dots = pts.length <= 40 ? pts : [pts[pts.length - 1]];
      for (const [i, v] of dots) root.append(svg("circle", { cx: x(i), cy: y(v), r: 4, fill: serie.color, stroke: "var(--surface)", "stroke-width": 2 }));
      const [i, v] = pts[pts.length - 1];
      ends.push({ y: y(v), x: x(i), text: (opts.series.length > 1 ? serie.label + " " : "") + opts.value(v) });
    }
    // Labels at the ends of the lines, unless they would overlap: then the legend and the tooltip carry them
    ends.sort((a, b) => a.y - b.y);
    if (ends.every((end, k) => k === 0 || end.y - ends[k - 1].y >= 13)) {
      for (const end of ends) {
        const label = svg("text", { class: "end-label", x: end.x + 8, y: end.y, "dominant-baseline": "middle" });
        label.textContent = end.text;
        root.append(label);
      }
    }
  }

  // Hover and keyboard: a crosshair on the nearest period, one tooltip with every series
  const cross = svg("line", { class: "crosshair", y1: m.top, y2: m.top + h, visibility: "hidden" });
  const hit = svg("rect", { x: m.left, y: 0, width: w, height: m.top + h, fill: "transparent" });
  root.append(cross, hit);
  plot.append(root);
  const tip = el("div", { class: "tip", hidden: "" });
  plot.append(tip);
  let current = null;
  function show(i, px) {
    current = i;
    const p = points[i];
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
    const rows = opts.series.map(serie => {
      const key = el("i");
      key.style.cssText = `display:inline-block;width:12px;height:2px;border-radius:1px;background:${serie.color}`;
      return el("div", { class: "row" }, key, el("strong", { text: p[serie.key] == null ? "–" : opts.value(p[serie.key]) }),
        el("span", { text: serie.label }));
    });
    const when = s.by === "day" ? fmt.date(p.t) : fmt.when(p.t);
    tip.replaceChildren(el("div", { class: "when", text: when }), ...rows,
      ...(opts.extra ? [el("div", { class: "row" }, el("span", { text: opts.extra(p) }))] : []));
    tip.hidden = false;
    const scale = plot.clientWidth / width;
    const left = (px ?? x(i)) * scale;
    const room = plot.clientWidth - tip.offsetWidth;
    tip.style.left = Math.max(0, Math.min(room, left + 12 > room ? left - tip.offsetWidth - 12 : left + 12)) + "px";
    tip.style.top = (m.top * scale) + "px";
  }
  function hide() { current = null; cross.setAttribute("visibility", "hidden"); tip.hidden = true; }
  hit.addEventListener("pointermove", event => {
    const box = root.getBoundingClientRect();
    const px = (event.clientX - box.left) * (width / box.width);
    show(Math.max(0, Math.min(points.length - 1, Math.floor((px - m.left) / band))), px);
  });
  hit.addEventListener("pointerleave", hide);
  root.addEventListener("blur", hide);
  root.addEventListener("focus", () => show(points.lastIndexOf(real[real.length - 1])));
  root.addEventListener("keydown", event => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    show(Math.max(0, Math.min(points.length - 1, (current ?? points.length - 1) + (event.key === "ArrowRight" ? 1 : -1))));
  });
}

function table(id, columns, rows) {
  const head = el("tr", {}, ...columns.map(column => el("th", { class: column.num ? "num" : "", text: column.label })));
  const body = rows.map(row => el("tr", {}, ...columns.map(column => {
    const value = column.value(row);
    const cell = el("td", { class: column.num ? "num" : column.text ? "text" : "" });
    if (value instanceof Node) cell.append(value); else cell.textContent = value ?? "–";
    return cell;
  })));
  document.getElementById(id).replaceChildren(el("thead", {}, head), el("tbody", {}, ...body));
  if (!rows.length) document.getElementById(id).append(el("tbody", {}, el("tr", {}, el("td", { class: "text", colspan: columns.length, text: "Nothing in this period." }))));
}

const OUTCOMES = {
  done: "answered", cancelled: "cancelled by the user", error: "error", refused: "refused by the guard",
  loop: "stopped: going round in circles", rounds: "stopped: too many rounds of tools", length: "reply cut: too long",
};

function renderTables(s) {
  table("series-table", [
    { label: "Period", value: p => s.by === "day" ? fmt.date(p.t) : fmt.when(p.t) },
    { label: "Calls", num: true, value: p => fmt.count(p.calls) },
    { label: "Errors", num: true, value: p => fmt.count(p.errors) },
    { label: "Median", num: true, value: p => fmt.seconds(p.p50) },
    { label: "p95", num: true, value: p => fmt.seconds(p.p95) },
    { label: "First token", num: true, value: p => fmt.seconds(p.ttft) },
    { label: "Prompt tok.", num: true, value: p => fmt.count(p.prompt_tokens) },
    { label: "Reply tok.", num: true, value: p => fmt.count(p.completion_tokens) },
    { label: "Answers", num: true, value: p => fmt.count(p.turns) },
    { label: "Failed", num: true, value: p => fmt.count(p.failed_turns) },
  ], s.series.filter(p => p.calls || p.turns));

  const rows = s.configurations.map((row, index) => ({ ...row, index })).reverse();
  table("configurations", [
    { label: "Prompt", value: row => {
      const cell = el("div", {}, el("code", { text: row.prompt || "?" }), row.think ? el("span", { class: "badge", text: "think", style: "margin-left:6px" }) : null);
      if (row.preview) cell.append(el("span", { class: "dim", text: row.preview + (row.chars ? " · " + fmt.count(row.chars) + " chars" : "") }));
      return cell;
    } },
    { label: "Model", value: row => row.model },
    { label: "Used", value: row => fmt.when(row.first) + " → " + fmt.when(row.last) },
    { label: "Calls", num: true, value: row => fmt.count(row.calls) },
    { label: "Median", num: true, value: row => fmt.seconds(row.p50) },
    { label: "p95", num: true, value: row => fmt.seconds(row.p95) },
    { label: "Prompt tok.", num: true, value: row => fmt.count(row.prompt_tokens) },
    { label: "Reply tok.", num: true, value: row => fmt.count(row.completion_tokens) },
    { label: "Tok/s", num: true, value: row => row.speed ? row.speed.toFixed(1) : "–" },
    { label: "Errors", num: true, value: row => fmt.percent(row.error_rate) },
    { label: "Against the one before", value: row => {
      if (row.previous == null) return "first one";
      const before = s.configurations[row.previous];
      const cell = el("div", {}, el("span", { class: "dim", text: "vs " + (before.prompt || "?") + (before.model !== row.model ? " · " + before.model : "") }));
      if (!row.findings.length) cell.append(el("span", { class: "dim", text: before.ok < 5 || row.ok < 5 ? "too few calls to compare" : "no change past the thresholds" }));
      for (const finding of row.findings) cell.append(el("div", { class: "finding" }, document.createTextNode(METRICS[finding.metric].label + " "), delta(finding)));
      return cell;
    } },
  ], rows);

  table("tools", [
    { label: "Tool", value: row => el("code", { text: row.name }) },
    { label: "Calls", num: true, value: row => fmt.count(row.calls) },
    { label: "Could not", num: true, value: row => fmt.percent(row.error_rate) },
    { label: "Median", num: true, value: row => fmt.seconds(row.p50) },
    { label: "p95", num: true, value: row => fmt.seconds(row.p95) },
  ], s.by_tool);

  const total = Object.values(s.outcomes).reduce((a, b) => a + b, 0);
  const most = Math.max(1, ...Object.values(s.outcomes));
  table("outcomes", [
    { label: "Outcome", value: row => OUTCOMES[row[0]] || row[0] },
    { label: "Answers", num: true, value: row => fmt.count(row[1]) },
    { label: "Share", value: row => {
      const bar = el("span", { class: "bar" });
      bar.style.width = Math.max(2, 120 * row[1] / most) + "px";
      return el("span", {}, bar, document.createTextNode(fmt.percent(row[1] / total, 0)));
    } },
  ], Object.entries(s.outcomes));

  table("slowest", [
    { label: "When", value: row => fmt.when(row.at) },
    { label: "Latency", num: true, value: row => fmt.seconds(row.latency) },
    { label: "Model load", num: true, value: row => row.load >= 0.1 ? fmt.seconds(row.load) : "–" },
    { label: "Prompt tok.", num: true, value: row => fmt.count(row.prompt_tokens) },
    { label: "Reply tok.", num: true, value: row => fmt.count(row.completion_tokens) },
    { label: "Round", num: true, value: row => row.round == null ? "–" : String(row.round + 1) },
    { label: "Last given", text: true, value: row => (row.tool ? row.tool + ": " : "") + (row.input || "").slice(0, 160) },
  ], s.slowest);

  table("problems", [
    { label: "When", value: row => fmt.when(row.at) },
    { label: "What", value: row => row.kind },
    { label: "Message", text: true, value: row => row.message || "–" },
  ], s.problems);
}

function renderCharts(s) {
  const css = getComputedStyle(document.documentElement);
  const color = name => css.getPropertyValue(name).trim();
  chart("chart-latency", s, { kind: "line", marks: true, markLabels: true, tick: fmt.secondsTick, value: fmt.seconds, height: 260,
    series: [{ key: "p50", label: "median", color: color("--s1") }, { key: "p95", label: "p95", color: color("--s2") }],
    extra: p => fmt.count(p.calls) + " calls" });
  chart("chart-volume", s, { kind: "stack", marks: true, tick: fmt.compact, value: fmt.count,
    series: [{ key: "ok", label: "worked", color: color("--s1") }, { key: "errors", label: "failed", color: color("--critical") }] });
  chart("chart-errors", s, { kind: "line", marks: true, tick: fmt.percentTick, value: v => fmt.percent(v), floor: 0.05,
    series: [{ key: "error_rate", label: "calls", color: color("--s1") }, { key: "failure_rate", label: "answers", color: color("--s2") }] });
  chart("chart-prompt", s, { kind: "line", marks: true, tick: fmt.compact, value: fmt.count,
    series: [{ key: "prompt_tokens", label: "prompt tokens", color: color("--s1") }] });
  chart("chart-reply", s, { kind: "line", marks: true, tick: fmt.compact, value: fmt.count,
    series: [{ key: "completion_tokens", label: "reply tokens", color: color("--s1") }] });
}

let selected = DATA.selected;
try { const saved = localStorage.getItem("louis-monitoring-range"); if (DATA.ranges.some(r => r.key === saved)) selected = saved; } catch (e) {}

function render() {
  const range = DATA.ranges.find(r => r.key === selected) || DATA.ranges[DATA.ranges.length - 1];
  const s = range.summary;
  // The columns of the volume and the rates of the answers come from the counts of each period
  for (const p of s.series) {
    p.ok = p.calls - p.errors;
    p.failure_rate = p.turns ? p.failed_turns / p.turns : null;
  }
  document.getElementById("period").textContent =
    fmt.when(s.start) + " → " + fmt.when(s.end) + " · by " + s.by + (s.guard ? " · guard changed " + s.guard + " messages" : "");
  renderKpis(s);
  renderCharts(s);
  renderTables(s);
}

function renderRanges() {
  const root = document.getElementById("ranges");
  root.replaceChildren(...DATA.ranges.map(range => {
    const button = el("button", { type: "button", "aria-pressed": String(range.key === selected), text: range.label });
    button.addEventListener("click", () => {
      selected = range.key;
      try { localStorage.setItem("louis-monitoring-range", selected); } catch (e) {}
      renderRanges();
      render();
    });
    return button;
  }));
}

document.getElementById("meta").textContent = DATA.source + " · generated " + fmt.when(DATA.generated)
  + (DATA.bad ? " · " + DATA.bad + " unreadable lines skipped" : "");
renderAlerts();
renderRanges();
render();
let resizing;
window.addEventListener("resize", () => { clearTimeout(resizing); resizing = setTimeout(render, 150); });
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render);
</script>
</body>
</html>
"""
