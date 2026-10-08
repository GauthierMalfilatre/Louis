##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Report: the metrics of the traces, in the terminal, and as the dashboard page
##
from .metrics import load, summarize, drift, MIN_CALLS, LATENCY_DRIFT, TOKENS_DRIFT, ERRORS_DRIFT
from .dashboard import render
from datetime import datetime
import os
import pathlib
import webbrowser

DASHBOARD_FILE: str = "louis.dashboard.html"

# The periods the page can show: key, label, days (None: all of them)
RANGES: tuple[tuple[str, str, float | None], ...] = (
    ("day", "Last day", 1), ("week", "Last 7 days", 7), ("month", "Last 30 days", 30), ("all", "All", None)
)

THRESHOLDS: str = (
    f"Told past ±{LATENCY_DRIFT:.0%} of median latency, ±{TOKENS_DRIFT:.0%} of tokens per call or "
    f"±{ERRORS_DRIFT * 100:.0f} points of error rate, with {MIN_CALLS} calls at least on each side."
)

def seconds(value: float | None) -> str:
    """ A duration, in the unit that reads best """
    if value is None:
        return "–"
    return f"{value * 1000:.0f} ms" if value < 1 else f"{value:.2f} s" if value < 10 else f"{value:.1f} s"

def percent(value: float | None) -> str:
    """ A share, in percent """
    return "–" if value is None else f"{value:.1%}"

def count(value: float | None) -> str:
    """ A count, with its thousands apart """
    return "–" if value is None else f"{value:,.0f}"

def when(iso: str) -> str:
    """ A time of the summary, short """
    return datetime.fromisoformat(iso).strftime("%d %b %H:%M")

def finding(item: dict) -> str:
    """ One change of an alert, on one line """
    labels: dict[str, tuple[str, callable]] = {
        "latency"          : ("median latency", seconds),
        "prompt_tokens"    : ("prompt tokens per call", count),
        "completion_tokens": ("reply tokens per call", count),
        "error_rate"       : ("error rate", percent),
    }
    label, shown = labels[item["metric"]]
    change: str = (f"{(item['after'] - item['before']) * 100:+.1f} pts" if item["metric"] == "error_rate"
                   else f"{item['change']:+.0%}" if item["change"] is not None else "")
    return f"{'▲' if item['after'] > item['before'] else '▼'} {label} {shown(item['before'])} → {shown(item['after'])} ({change})"

def grade(value: float | None) -> str:
    """ A mean score of the judge, out of 5 """
    return f"{value:.1f}/5" if value is not None else "–"

def judged(scores: dict) -> list[str]:
    """ The lines of the answers judged: all of them, then each version (prompt and model) when there are several """
    if not scores["answers"]:
        return []
    def line(label: str, values: dict) -> str:
        return (f"  {label:<12} {count(values['answers']):>7}   faithful {percent(values['faithfulness'])} · "
                f"relevance {grade(values['relevance'])} · coherence {grade(values['coherence'])} · "
                f"claims flagged {percent(values['flagged_rate'])} ({values['contradicted']} contradicted)")
    lines: list[str] = [line("judged", scores)]
    if len(scores["versions"]) > 1:
        lines += [line(f"  {version['prompt'] or '?'}", version) + f" · {version['model']}" for version in scores["versions"]]
    return lines

def text(summary: dict, alerts: list[dict], path: str) -> str:
    """ The summary of all the calls, and the drift alerts, for the terminal """
    calls, turns, tools = summary["calls"], summary["turns"], summary["tools"]
    structured: dict = summary.get("structured") or {"replies": 0}
    lines: list[str] = [
        f"Louis monitoring · {path}",
        f"  {when(summary['start'])} → {when(summary['end'])} · {summary['runs']} run{'s' if summary['runs'] != 1 else ''}",
        f"  model calls  {count(calls['calls']):>7}   median {seconds(calls['p50'])} · p95 {seconds(calls['p95'])} · "
        f"first token {seconds(calls['ttft'])} · errors {percent(calls['error_rate'])}",
        f"  answers      {count(turns['turns']):>7}   median {seconds(turns['p50'])} · failed {percent(turns['failure_rate'])}",
        f"  tokens/call  {count(calls['prompt_tokens']):>7}   prompt · {count(calls['completion_tokens'])} reply · "
        f"{f'{calls['speed']:.1f}' if calls['speed'] else '–'} tok/s",
        f"  tool calls   {count(tools['calls']):>7}   could not do it {percent(tools['errors'] / tools['calls'] if tools['calls'] else None)}",
        *([f"  json replies {count(structured['replies']):>7}   valid {percent(structured['valid_rate'])} · "
           f"at once {percent(structured['first_try_rate'])}"] if structured["replies"] else []),
        *judged(summary.get("eval") or {"answers": 0}),
        "",
        "Drift",
    ]
    if not alerts:
        lines.append(f"  ✓ none. {THRESHOLDS}")
    for alert in alerts:
        title: str = "last 24 h against the 7 days before" if alert["kind"] == "recent" else alert["title"]
        since: str = "" if alert["kind"] == "recent" else f"since {when(alert['since'])}, "
        lines.append(f"  {'⚠' if alert['level'] == 'warn' else 'ℹ'} {title} ({since}{alert['calls'][0]} → {alert['calls'][1]} calls)")
        lines += [f"      {finding(item)}" for item in alert["findings"]]
    return "\n".join(lines)

def report(path: str, output: str | None = None, *, open_browser: bool = False) -> int:
    """ Print the metrics of the traces at path, write the dashboard (next to them by default), open it if asked """
    if not os.path.exists(path):
        print(f"No traces in {path} yet: they are written as louis answers (LOUIS_TRACES sets where).")
        return 1
    records, bad = load(path)
    alerts: list[dict] = drift(records)
    summaries: dict[str, dict] = {key: summarize(records, days=days) for key, _, days in RANGES}

    everything: dict = summaries["all"]
    span_days: float = (datetime.fromisoformat(everything["end"]) - datetime.fromisoformat(everything["start"])).days
    output = output or os.path.join(os.path.dirname(os.path.abspath(path)), DASHBOARD_FILE)
    with open(output, "w", encoding="utf-8") as file:
        file.write(render({
            "source": os.path.abspath(path),
            "generated": datetime.now().isoformat(timespec="seconds"),
            "bad": bad,
            "thresholds": THRESHOLDS,
            "alerts": alerts,
            # Past a month, the last one is shown first: the start of a long history hides what changed lately
            "selected": "all" if span_days <= 30 else "month",
            "ranges": [{"key": key, "label": label, "summary": summaries[key]} for key, label, _ in RANGES],
        }))

    print(text(everything, alerts, path))
    if bad:
        print(f"\n{bad} lines of {path} could not be read: skipped")
    print(f"\nDashboard: {output}")
    if open_browser:
        webbrowser.open(pathlib.Path(output).resolve().as_uri())
    return 0
