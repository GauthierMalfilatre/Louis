##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Metrics: what the records of the recorder tell over time (call volume, latency, errors, tokens) and their drift
##
## A drift is told two ways. Against the configuration it took over from: a new prompt, or a new model, is compared
## with the one used before it. And against the past: the last day is compared with the week before it
##
from collections import Counter
from datetime import datetime, timedelta
import json
import math

# Fewer calls than this tell nothing: a configuration or a period with less is never compared
MIN_CALLS: int = 5
# The changes that are told: of the median latency (both a share and seconds, 0.1s to 0.2s is noise), of the
# tokens per call, and of the error rate (in points)
LATENCY_DRIFT: float = 0.30
LATENCY_FLOOR: float = 0.30
TOKENS_DRIFT : float = 0.30
ERRORS_DRIFT : float = 0.05
# The recent calls, compared with the ones before them
RECENT  : timedelta = timedelta(days=1)
BASELINE: timedelta = timedelta(days=7)
# The ends of a turn where the user got no answer
FAILED_TURNS: frozenset[str] = frozenset({"error", "loop", "rounds", "length"})
# Past this span, the series go by day instead of by hour
HOURLY_SPAN: timedelta = timedelta(days=3)
# The alerts shown: the most recent ones, the others are in the table of the configurations
MAX_ALERTS: int = 6

def load(path: str) -> tuple[list[dict], int]:
    """
        The records of a file, oldest first, each with its local time (at, naive: the days are the user's), and the
        count of lines that were not records (one cut in the middle by a crash...)
    """
    records: list[dict] = []
    bad: int = 0
    with open(path, encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            try:
                record: dict = json.loads(line)
                record["at"] = datetime.fromisoformat(record["ts"]).astimezone().replace(tzinfo=None)
            except (ValueError, KeyError, TypeError):
                bad += 1
                continue
            records.append(record)
    records.sort(key=lambda record: record["at"])
    return records, bad

def percentile(values: list[float], q: float) -> float | None:
    """ The value under which the share q of the values are, between two of them if needed """
    if not values:
        return None
    ordered: list[float] = sorted(values)
    k: float = (len(ordered) - 1) * q
    low: int = math.floor(k)
    high: int = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (k - low)

def mean(values: list[float]) -> float | None:
    """ The mean of the values, None without any """
    return sum(values) / len(values) if values else None

def ratio(part: float, whole: float) -> float | None:
    """ part over whole, None when whole is nothing """
    return part / whole if whole else None

def calls_stats(calls: list[dict]) -> dict:
    """
        What model calls tell: how many, how fast, how often they failed, what they cost. The latency and the tokens
        are those of the calls that worked: a call cut by a timeout says nothing about the speed of the model.
        A cancelled call is no error: the user stopped it
    """
    done: list[dict] = [call for call in calls if call.get("status") == "ok"]
    failed: int = sum(1 for call in calls if call.get("status") == "error")
    latencies: list[float] = [call["latency"] for call in done]
    timed: list[dict] = [call for call in done if call.get("generation")]
    return {
        "calls"            : len(calls),
        "ok"               : len(done),
        "errors"           : failed,
        "error_rate"       : ratio(failed, len(done) + failed),
        "p50"              : percentile(latencies, 0.50),
        "p95"              : percentile(latencies, 0.95),
        "mean"             : mean(latencies),
        "ttft"             : percentile([call["ttft"] for call in done if call.get("ttft") is not None], 0.50),
        "load"             : sum(1 for call in done if (call.get("load") or 0) >= 1.0),
        "prompt_tokens"    : mean([call.get("prompt_tokens", 0) for call in done]),
        "completion_tokens": mean([call.get("completion_tokens", 0) for call in done]),
        # Tokens generated per second: how fast the model writes, whatever the length of its replies
        "speed"            : ratio(sum(call["completion_tokens"] for call in timed), sum(call["generation"] for call in timed)),
    }

def working(record: dict, key: str) -> float:
    """ How long louis worked on a turn or a tool call: its time, but the one it waited for the user to answer """
    return max(0.0, record.get(key, 0.0) - record.get("waited", 0.0))

def turns_stats(turns: list[dict]) -> dict:
    """ What the answers tell: how many, how many failed, how long the user waited for the ones that ended well """
    answered: list[float] = [working(turn, "latency") for turn in turns if turn.get("reason") == "done"]
    failed: int = sum(1 for turn in turns if turn.get("reason") in FAILED_TURNS)
    return {
        "turns"       : len(turns),
        "failed"      : failed,
        "failure_rate": ratio(failed, len(turns)),
        "p50"         : percentile(answered, 0.50),
        "p95"         : percentile(answered, 0.95),
        "rounds"      : mean([turn.get("rounds", 0) for turn in turns]),
    }

def tools_stats(tools: list[dict]) -> list[dict]:
    """ Each tool: how often it was called, how often it could not do it, how long it took. Most called first """
    by_name: dict[str, list[dict]] = {}
    for tool in tools:
        by_name.setdefault(tool.get("name", "?"), []).append(tool)
    rows: list[dict] = []
    for name, calls in by_name.items():
        errors: int = sum(1 for call in calls if not call.get("ok"))
        durations: list[float] = [working(call, "duration") for call in calls]
        rows.append({
            "name": name, "calls": len(calls), "errors": errors, "error_rate": ratio(errors, len(calls)),
            "p50": percentile(durations, 0.50), "p95": percentile(durations, 0.95)
        })
    return sorted(rows, key=lambda row: -row["calls"])

def floor(at: datetime, by: str) -> datetime:
    """ The start of the hour or of the day at is in """
    at = at.replace(minute=0, second=0, microsecond=0)
    return at.replace(hour=0) if by == "day" else at

def series(records: list[dict], start: datetime, end: datetime, by: str) -> list[dict]:
    """ The metrics hour by hour, or day by day, from start to end: the empty ones too, time goes on without calls """
    step: timedelta = timedelta(hours=1) if by == "hour" else timedelta(days=1)
    buckets: dict[datetime, dict[str, list[dict]]] = {}
    at: datetime = floor(start, by)
    while at <= end:
        buckets[at] = {"llm": [], "turn": [], "tool": []}
        at += step
    for record in records:
        if record["type"] in ("llm", "turn", "tool"):
            buckets.setdefault(floor(record["at"], by), {"llm": [], "turn": [], "tool": []})[record["type"]].append(record)

    points: list[dict] = []
    for at, group in sorted(buckets.items()):
        calls: dict = calls_stats(group["llm"])
        turns: dict = turns_stats(group["turn"])
        points.append({
            "t"                : at.isoformat(timespec="minutes"),
            "calls"            : calls["calls"],
            "errors"           : calls["errors"],
            "error_rate"       : calls["error_rate"],
            "p50"              : calls["p50"],
            "p95"              : calls["p95"],
            "ttft"             : calls["ttft"],
            "prompt_tokens"    : calls["prompt_tokens"],
            "completion_tokens": calls["completion_tokens"],
            "turns"            : turns["turns"],
            "failed_turns"     : turns["failed"],
            "tools"            : len(group["tool"]),
            "tool_errors"      : sum(1 for tool in group["tool"] if not tool.get("ok")),
        })
    return points

def configurations(calls: list[dict], prompts: dict[str, dict]) -> list[dict]:
    """
        The calls grouped by what they ran on (prompt, model, thinking), in the order they first appeared. Each one is
        compared with the one it took over from: the last one before it that thinks the same way (/think alone makes
        every reply much longer, it would hide what a prompt changed)
    """
    groups: dict[tuple, list[dict]] = {}
    for call in calls:
        groups.setdefault((call.get("prompt"), call.get("model"), bool(call.get("think"))), []).append(call)

    rows: list[dict] = []
    for (prompt, model, think), group in groups.items():
        text: str = (prompts.get(prompt) or {}).get("text") or ""
        row: dict = {
            "prompt": prompt, "model": model, "think": think,
            "first": group[0]["at"], "last": group[-1]["at"],
            "chars": (prompts.get(prompt) or {}).get("chars"),
            "preview": next((line.strip() for line in text.splitlines() if line.strip()), None),
            **calls_stats(group),
            "previous": None, "findings": [],
        }
        previous: int | None = next((i for i in range(len(rows) - 1, -1, -1) if rows[i]["think"] == think), None)
        if previous is not None:
            row["previous"] = previous
            row["findings"] = compare(rows[previous], row)
        rows.append(row)
    return rows

def compare(before: dict, after: dict) -> list[dict]:
    """
        What changed from the calls before to the calls after, past its threshold: the median latency, the tokens per
        call and the error rate. bad tells a change for the worse: slower, or failing more
    """
    findings: list[dict] = []

    def told(metric: str, old: float, new: float, bad: bool) -> None:
        findings.append({"metric": metric, "before": old, "after": new, "change": ratio(new - old, old), "bad": bad})

    if before["ok"] >= MIN_CALLS and after["ok"] >= MIN_CALLS:
        old, new = before["p50"], after["p50"]
        if abs(new - old) >= LATENCY_FLOOR and abs(new - old) >= LATENCY_DRIFT * old:
            told("latency", old, new, new > old)
        for metric in ("prompt_tokens", "completion_tokens"):
            old, new = before[metric], after[metric]
            if old and abs(new - old) >= TOKENS_DRIFT * old:
                told(metric, old, new, False)
    if before["ok"] + before["errors"] >= MIN_CALLS and after["ok"] + after["errors"] >= MIN_CALLS:
        old, new = before["error_rate"], after["error_rate"]
        if abs(new - old) >= ERRORS_DRIFT:
            told("error_rate", old, new, new > old)
    return findings

def drift(records: list[dict]) -> list[dict]:
    """
        The drifts worth a look, most recent first: a configuration against the one before it, the last day against
        the week before it. Always on all the records: a drift needs its past
    """
    calls: list[dict] = [record for record in records if record["type"] == "llm"]
    prompts: dict[str, dict] = {record["prompt"]: record for record in records if record["type"] == "prompt"}
    rows: list[dict] = configurations(calls, prompts)
    found: list[dict] = []
    for row in rows:
        if not row["findings"]:
            continue
        before: dict = rows[row["previous"]]
        changed: list[str] = []
        if row["prompt"] != before["prompt"]:
            changed.append(f"prompt {before['prompt']} → {row['prompt']}")
        if row["model"] != before["model"]:
            changed.append(f"model {before['model']} → {row['model']}")
        found.append({
            "kind": "configuration", "since": row["first"], "title": ", ".join(changed),
            "calls": [before["ok"], row["ok"]], "findings": row["findings"],
            "level": "warn" if any(finding["bad"] for finding in row["findings"]) else "info",
        })

    if calls:
        end: datetime = calls[-1]["at"]
        recent: list[dict] = [call for call in calls if call["at"] > end - RECENT]
        past: list[dict] = [call for call in calls if end - RECENT - BASELINE < call["at"] <= end - RECENT]
        findings: list[dict] = compare(calls_stats(past), calls_stats(recent)) if past and recent else []
        if findings:
            found.append({
                "kind": "recent", "since": end - RECENT, "title": "last 24 h against the 7 days before",
                "calls": [len(past), len(recent)], "findings": findings,
                "level": "warn" if any(finding["bad"] for finding in findings) else "info",
            })
    found.sort(key=lambda alert: alert["since"], reverse=True)
    return dated(found[:MAX_ALERTS])

def problems(calls: list[dict], turns: list[dict], most: int = 10) -> list[dict]:
    """ The last model calls that failed, and the last answers that did not end well """
    found: list[dict] = [
        {"at": call["at"], "kind": "model call", "message": call.get("error")}
        for call in calls if call.get("status") == "error"
    ] + [
        {"at": turn["at"], "kind": f"turn {turn['reason']}", "message": turn.get("message")}
        for turn in turns if turn.get("reason") in FAILED_TURNS
    ]
    return sorted(found, key=lambda problem: problem["at"], reverse=True)[:most]

def slowest(calls: list[dict], most: int = 5) -> list[dict]:
    """ The slowest calls that worked, with what they were given: why they were slow is often there """
    rows: list[dict] = []
    for call in sorted((call for call in calls if call.get("status") == "ok"), key=lambda call: -call["latency"])[:most]:
        given: list[dict] = call.get("input") or []
        rows.append({
            "at": call["at"], "latency": call["latency"], "load": call.get("load"), "round": call.get("round"),
            "prompt_tokens": call.get("prompt_tokens"), "completion_tokens": call.get("completion_tokens"),
            "prompt": call.get("prompt"), "input": given[-1].get("content") if given else None,
            "tool": given[-1].get("tool") if given else None,
        })
    return rows

def dated(value):
    """ The summary as JSON can hold it: the times as text """
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, dict):
        return {key: dated(item) for key, item in value.items()}
    if isinstance(value, list):
        return [dated(item) for item in value]
    return value

def summarize(records: list[dict], *, days: float | None = None, by: str | None = None) -> dict:
    """
        Everything the dashboard shows of a period: the last days of the records, or all of them. by is "hour" or
        "day", chosen from the span when not given
    """
    prompts: dict[str, dict] = {record["prompt"]: record for record in records if record["type"] == "prompt"}
    end: datetime = records[-1]["at"] if records else datetime.now()
    if days is not None:
        records = [record for record in records if record["at"] >= end - timedelta(days=days)]
    start: datetime = records[0]["at"] if records else end
    by = by or ("hour" if end - start <= HOURLY_SPAN else "day")

    calls: list[dict] = [record for record in records if record["type"] == "llm"]
    turns: list[dict] = [record for record in records if record["type"] == "turn"]
    tools: list[dict] = [record for record in records if record["type"] == "tool"]
    rows: list[dict] = configurations(calls, prompts)

    # Where a prompt or a model starts on the charts: /think is no change of the setup
    marks: list[dict] = []
    for row in rows:
        if not any(mark["prompt"] == row["prompt"] and mark["model"] == row["model"] for mark in marks):
            marks.append({"t": row["first"], "prompt": row["prompt"], "model": row["model"]})

    return dated({
        "start": start, "end": end, "by": by, "days": days,
        "runs": len({record["run"] for record in records}),
        "calls": calls_stats(calls),
        "turns": turns_stats(turns),
        "tools": {"calls": len(tools), "errors": sum(1 for tool in tools if not tool.get("ok"))},
        "guard": sum(1 for record in records if record["type"] == "guard"),
        "series": series(records, start, end, by),
        "configurations": rows,
        # The first one is where the period starts, not a change
        "marks": marks[1:],
        "outcomes": dict(Counter(turn.get("reason") for turn in turns).most_common()),
        "by_tool": tools_stats(tools),
        "problems": problems(calls, turns),
        "slowest": slowest(calls),
    })
