##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the dashboard: its page is a script, which a merge can break without any check of Python seeing it
##
import re
import shutil
import subprocess
import pytest
from monitor.dashboard import render
from monitor.metrics import summarize

# One record of each kind the tiles are drawn from: every tile of the page is written
RECORDS: list[dict] = [
    {"type": "llm", "purpose": "reply", "status": "ok", "latency": 1.0, "prompt": "p", "model": "m", "think": False},
    {"type": "turn", "reason": "done", "latency": 2.0, "react": True, "steps": 2, "checks": 1, "revised": 0},
    {"type": "structured", "valid": True, "attempts": 1},
    {"type": "plan", "answered": True, "approved": True, "waited": 1.5, "actions": []},
]

@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_script_of_the_dashboard_parses(tmp_path):
    from datetime import datetime
    records: list[dict] = [{**record, "at": datetime(2026, 10, 1, 12), "run": "r", "v": 1} for record in RECORDS]
    page: str = render({"source": "traces.jsonl", "generated": "2026-10-01T12:00", "bad": 0, "thresholds": "",
                        "alerts": [], "selected": "all",
                        "ranges": [{"key": "all", "label": "All", "summary": summarize(records)}]})
    script: str = re.search(r"^<script>\n(.*)^</script>$", page, re.MULTILINE | re.DOTALL).group(1)
    (tmp_path / "dashboard.js").write_text(script)
    checked = subprocess.run(["node", "--check", str(tmp_path / "dashboard.js")], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
