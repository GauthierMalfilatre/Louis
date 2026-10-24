##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the monitoring (EV3): the records of a turn in the traces, the metrics read from them, the drift of a
## prompt that slows the model down, and the dashboard written beside them. The model is a script of replies
##
import json
from datetime import datetime, timedelta
from model.reply import Reply
from monitor.metrics import load, summarize, drift
from monitor.report import report
from tool.tool_call import ToolCall

def records(path) -> list[dict]:
    with open(path, encoding="utf-8") as file:
        return [json.loads(line) for line in file]

def test_a_turn_leaves_its_run_prompt_calls_tool_and_turn_records(chat, folder):
    (folder / "main.py").write_text("print('hi')\n")
    app = chat([Reply(tool_calls=[ToolCall("cat_file", {"path": "main.py"})], prompt_tokens=100, completion_tokens=10),
                Reply(content="Il affiche hi.", prompt_tokens=150, completion_tokens=5, ttft=0.2)])
    app._App__answer("Que fait main.py ?")
    found = records(app.traces)
    assert [record["type"] for record in found] == ["run", "prompt", "llm", "tool", "llm", "turn"]
    run, prompt, first, tool, second, turn = found
    assert run["model"] and "chat.context" in run["settings"]
    # The prompt is written whole once, the calls name it by its version
    assert first["prompt"] == second["prompt"] == prompt["prompt"] and "Louis" in prompt["text"]
    assert (first["status"], first["purpose"], first["prompt_tokens"]) == ("ok", "reply", 100)
    assert first["tool_calls"] == [{"name": "cat_file", "arguments": {"path": "main.py"}}]
    assert (tool["name"], tool["ok"], tool["arguments"]) == ("cat_file", True, {"path": "main.py"})
    assert (turn["reason"], turn["rounds"], turn["tools"]) == ("done", 2, 1)
    assert (turn["prompt_tokens"], turn["completion_tokens"]) == (250, 15)
    assert turn["input"] == "Que fait main.py ?" and turn["output"] == "Il affiche hi."
    # Every record of the turn shares its id
    assert len({record["turn"] for record in (first, tool, second, turn)}) == 1

def test_a_failed_call_is_recorded_as_an_error(chat):
    from model.model_exception import ModelException
    app = chat([])
    def broken(*args, **kwargs):
        raise ModelException("Cannot reach http://ollama")
    app.model.chat = broken
    app._App__answer("Salut")
    llm = next(record for record in records(app.traces) if record["type"] == "llm")
    assert (llm["status"], llm["error"]) == ("error", "Cannot reach http://ollama")
    summary = summarize(load(str(app.traces))[0])
    assert (summary["calls"]["errors"], summary["calls"]["error_rate"], summary["turns"]["failed"]) == (1, 1.0, 1)

def calls(prompt: str, latency: float, start: datetime, count: int = 6) -> list[dict]:
    return [{"type": "llm", "ts": (start + timedelta(minutes=n)).isoformat(), "run": "r", "prompt": prompt,
             "model": "qwen3:8b", "think": False, "status": "ok", "latency": latency, "prompt_tokens": 1000,
             "completion_tokens": 100} for n in range(count)]

def test_a_new_prompt_that_doubles_the_latency_is_an_alert(tmp_path):
    start = datetime(2026, 10, 1, 12)
    path = tmp_path / "traces.jsonl"
    lines = calls("v1", 2.0, start) + calls("v2", 4.0, start + timedelta(hours=1))
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\nnot json\n")
    found, bad = load(str(path))
    assert (len(found), bad) == (12, 1)
    summary = summarize(found)
    assert (summary["calls"]["calls"], summary["calls"]["p50"]) == (12, 3.0)
    [alert] = drift(found)
    assert alert["kind"] == "configuration" and alert["title"] == "prompt v1 → v2" and alert["level"] == "warn"
    [latency] = alert["findings"]
    assert (latency["metric"], latency["before"], latency["after"], latency["bad"]) == ("latency", 2.0, 4.0, True)

def test_small_changes_and_few_calls_are_no_alert(tmp_path):
    start = datetime(2026, 10, 1, 12)
    assert drift(load_lines(tmp_path, calls("v1", 2.0, start) + calls("v2", 2.1, start + timedelta(hours=1)))) == []
    assert drift(load_lines(tmp_path, calls("v1", 2.0, start, 2) + calls("v2", 9.0, start + timedelta(hours=1), 2))) == []

def load_lines(tmp_path, lines: list[dict]) -> list[dict]:
    path = tmp_path / "some.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines))
    return load(str(path))[0]

def test_the_dashboard_is_written_beside_the_traces(tmp_path, capsys):
    path = tmp_path / "traces.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in calls("v1", 2.0, datetime(2026, 10, 1, 12))))
    assert report(str(path)) == 0
    page = (tmp_path / "louis.dashboard.html").read_text()
    assert page.startswith("<!doctype html>")
    assert "Dashboard:" in capsys.readouterr().out
    assert report(str(tmp_path / "none.jsonl")) == 1
