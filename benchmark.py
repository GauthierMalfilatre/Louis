#!/usr/bin/env python3
##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Hardware benchmark: what this machine is, how fast it runs the models of Louis, and which requirements it meets
##   python3 benchmark.py                             the chat model of Louis and qwen3:8b, on this machine
##   python3 benchmark.py --models qwen3:8b --cpu     these models, then the same without the GPU
##   python3 benchmark.py --requirements results/     the requirements told by the results of several machines
##
## eval/bench.py scores what Louis answers; this one measures the machine, with the models alone. It runs before Louis
## is installed: the standard library only, and no venv, on Linux, WSL, macOS and Windows. One machine tells whether it
## meets a level, not where the line between two levels is: run it on several, and give all their results to
## --requirements
##
from __future__ import annotations
from datetime import datetime
import argparse
import glob
import importlib.util
import json
import os
import platform
import re
import shutil
import socket
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

GIB: int = 1024 ** 3
HERE: str = os.path.dirname(os.path.abspath(__file__))

# What the script needs of the settings of Louis, when it is copied alone to another machine
DEFAULTS: dict = {
    "chat.model.name"      : "qwen3.5",
    "chat.model.parameters": "9b",
    "chat.uri"             : "http://localhost:11434",
    "chat.context"         : 24576,
    "chat.options"         : {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "presence_penalty": 0.0},
    "scribe.model"         : "qwen3:4b-instruct",
    "scribe.context"       : 4096,
    "rag.embed.model"      : "nomic-embed-text",
}
# Compared with the chat model of Louis by default
OTHER_MODEL: str = "qwen3:8b"

# Tokens of the prompts sent, as in the traces of real sessions (43 calls): 3187 at p50 (the system prompt and the
# tools alone are most of it), 8062 at p95. None: a full context, what the window of Louis leaves of it (30 % for the reply)
SCENARIOS: dict[str, int | None] = {"typical": 3200, "long": 8000, "full": None}
FULL_SHARE: float = 0.7
# Tokens written by each request: enough for a stable speed, without waiting long on a slow machine
WRITTEN: int = 200
# A request that takes longer is cut: as long as Louis waits for a reply (chat.timeout.response)
TIMEOUT: float = 600.0
# A request expected to take longer is not sent, its scenario is told as skipped: on a CPU, a full context takes many minutes
MAX_EXPECTED: float = 180.0

# What makes Louis usable, and comfortable. These are choices, not measures: a turn takes 3 model calls at p50, 9 at p95
LEVELS: dict[str, dict[str, float]] = {
    "minimum"    : {"tok_s": 10.0, "typical_ttft": 30.0},
    "recommended": {"tok_s": 30.0, "typical_ttft": 5.0, "long_ttft": 15.0},
}
BELOW: str = "below minimum"
# RAM for the system and Louis itself (its guard loads a spaCy model): an estimate, the only memory figure not measured
RESERVE: int = 3 * GIB

INSTRUCTION: str = "Explain in detail, in several long paragraphs, what the text above does."
# Without the code of Louis next to the script: enough text to fill a context
FILLER: str = "def add(first, second):\n    # Add two numbers, and return their sum\n    return first + second\n\n"

class OllamaError(Exception):
    """ Ollama cannot be reached, refused a request, or took too long """

def run(*command: str, timeout: float = 15.0) -> str | None:
    """ What a command wrote, None if it is not there or failed: most of them exist on some machines only """
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None

def read(path: str) -> str | None:
    """ The text of a file, None if it can not be read """
    try:
        with open(path, encoding="utf-8", errors="replace") as file:
            return file.read()
    except OSError:
        return None

def is_wsl() -> bool:
    return "microsoft" in (read("/proc/version") or "").lower()

def cpu_spec() -> dict:
    """ The name of the CPU, its cores, and the instructions llama.cpp goes much faster with """
    name: str | None = platform.processor() or None
    physical: int | None = None
    flags: list[str] = []
    system: str = platform.system()
    if system == "Linux":
        info: str = read("/proc/cpuinfo") or ""
        if found := re.search(r"model name\s*:\s*(.+)", info):
            name = found.group(1).strip()
        if found := re.search(r"^flags\s*:\s*(.+)$", info, re.MULTILINE):
            flags = sorted({"avx", "avx2", "avx512f"} & set(found.group(1).split()))
        cores: set = set(re.findall(r"physical id\s*:\s*(\d+)\n(?:.*\n)*?core id\s*:\s*(\d+)", info))
        physical = len(cores) or None
    elif system == "Darwin":
        name = run("sysctl", "-n", "machdep.cpu.brand_string") or name
        count: str | None = run("sysctl", "-n", "hw.physicalcpu")
        physical = int(count) if count and count.isdigit() else None
    elif system == "Windows":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                name = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass
        count = run("powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_Processor | Measure-Object NumberOfCores -Sum).Sum")
        physical = int(count) if count and count.isdigit() else None
    return {"name": name, "arch": platform.machine(), "physical_cores": physical, "threads": os.cpu_count(), "flags": flags}

def memory_spec() -> dict:
    """ The RAM in bytes: all of it, and what is free now. Under WSL, what the virtual machine was given """
    system: str = platform.system()
    if system == "Linux":
        info: dict = {key: int(value) * 1024
                      for key, value in re.findall(r"^(\w+):\s+(\d+) kB", read("/proc/meminfo") or "", re.MULTILINE)}
        return {"ram": info.get("MemTotal"), "ram_available": info.get("MemAvailable")}
    if system == "Darwin":
        total: str | None = run("sysctl", "-n", "hw.memsize")
        return {"ram": int(total) if total and total.isdigit() else None, "ram_available": None}
    if system == "Windows":
        import ctypes
        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                        ("available", ctypes.c_ulonglong), ("rest", ctypes.c_ulonglong * 5)]
        status: Status = Status()
        status.length = ctypes.sizeof(Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return {"ram": status.total, "ram_available": status.available}
    return {"ram": None, "ram_available": None}

def nvidia_gpus() -> list[dict]:
    output: str | None = run("nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version",
                             "--format=csv,noheader,nounits")
    gpus: list[dict] = []
    for line in (output or "").splitlines():
        fields: list[str] = [field.strip() for field in line.split(",")]
        if len(fields) == 4 and fields[1].isdigit() and fields[2].isdigit():
            gpus.append({"name": fields[0], "vram": int(fields[1]) * 1024 ** 2, "vram_free": int(fields[2]) * 1024 ** 2,
                         "driver": fields[3], "backend": "cuda"})
    return gpus

def linux_gpus() -> list[dict]:
    """ The GPUs nvidia-smi does not see: the kernel gives the VRAM of AMD ones, lspci the names of all """
    gpus: list[dict] = []
    for total in glob.glob("/sys/class/drm/card*/device/mem_info_vram_total"):
        used: str | None = read(total.replace("vram_total", "vram_used"))
        size: int = int((read(total) or "0").strip() or 0)
        gpus.append({"name": "AMD GPU", "vram": size, "vram_free": size - int(used) if used else None, "backend": "rocm"})
    if not gpus:
        for line in (run("lspci") or "").splitlines():
            if re.search(r"VGA|3D controller|Display controller", line) and "NVIDIA" not in line:
                gpus.append({"name": line.split(": ", 1)[-1], "vram": None, "vram_free": None, "backend": None})
    return gpus

def apple_gpus() -> list[dict]:
    """ Apple Silicon shares the RAM with its GPU: no VRAM of its own """
    try:
        displays: list[dict] = json.loads(run("system_profiler", "-json", "SPDisplaysDataType") or "{}").get("SPDisplaysDataType", [])
    except ValueError:
        return []
    return [{"name": gpu.get("sppci_model") or "?", "vram": None, "vram_free": None, "unified": True, "backend": "metal"}
            for gpu in displays]

def windows_gpus() -> list[dict]:
    """ AdapterRAM is cut at 4 GB by Windows: a VRAM of that size or more is not known """
    output: str | None = run("powershell", "-NoProfile", "-Command",
                             "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json")
    try:
        found = json.loads(output or "[]")
    except ValueError:
        return []
    gpus: list[dict] = []
    for gpu in [found] if isinstance(found, dict) else found:
        size: int = gpu.get("AdapterRAM") or 0
        gpus.append({"name": gpu.get("Name") or "?", "vram": size if 0 < size < 4 * GIB else None, "vram_free": None, "backend": None})
    return gpus

def gpu_spec() -> list[dict]:
    gpus: list[dict] = nvidia_gpus()
    if gpus:
        return gpus
    system: str = platform.system()
    if system == "Darwin":
        return apple_gpus()
    return windows_gpus() if system == "Windows" else linux_gpus()

def on_battery() -> bool | None:
    """ A laptop on its battery slows down, and the measures with it. None: not known, or not a laptop """
    system: str = platform.system()
    if system == "Linux":
        for path in glob.glob("/sys/class/power_supply/*/online"):
            return (read(path) or "").strip() == "0"
    elif system == "Darwin":
        output: str | None = run("pmset", "-g", "batt")
        return "Battery Power" in output if output else None
    elif system == "Windows":
        import ctypes
        class Status(ctypes.Structure):
            _fields_ = [("line", ctypes.c_byte), ("rest", ctypes.c_byte * 3), ("life", ctypes.c_ulong), ("full", ctypes.c_ulong)]
        status: Status = Status()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return status.line == 0
    return None

def machine_spec() -> dict:
    """ What the machine is: saved with the results, as the requirements are told in these terms """
    version: tuple = sys.version_info[:2]
    wsl: bool = is_wsl()
    return {
        "system"    : f"{platform.system()} {platform.release()}",
        "wsl"       : wsl,
        "cpu"       : cpu_spec(),
        **memory_spec(),
        "gpus"      : gpu_spec(),
        "disk_free" : shutil.disk_usage(os.path.expanduser("~")).free,
        "python"    : platform.python_version(),
        "python_ok" : version >= (3, 12),
        "docker"    : shutil.which("docker") is not None,
        "on_battery": on_battery(),
    }

class Ollama:
    """ The API of Ollama, with urllib: the benchmark runs before the dependencies of Louis are installed """
    def __init__(self, uri: str):
        self.uri: str = uri.rstrip("/")

    def __open(self, path: str, payload: dict | None, timeout: float):
        data: bytes | None = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.uri + path, data=data, headers={"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as e:
            try:
                message: str = json.loads(e.read()).get("error") or str(e)
            except ValueError:
                message = str(e)
            raise OllamaError(message) from e
        except OSError as e:
            raise OllamaError(f"cannot reach {self.uri}: {e}") from e

    def get(self, path: str, timeout: float = 5.0) -> dict:
        with self.__open(path, None, timeout) as res:
            return json.load(res)

    def post(self, path: str, payload: dict, timeout: float = TIMEOUT) -> dict:
        try:
            with self.__open(path, {**payload, "stream": False}, timeout) as res:
                return json.load(res)
        except OSError as e:
            raise OllamaError(f"no reply: {e}") from e

    def chat(self, model: str, prompt: str, options: dict, think: bool | None = None) -> dict:
        """ A request, streamed to time its first token. What Ollama counted, and the seconds until that token """
        payload: dict = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": True,
                         "keep_alive": "5m", "options": options}
        # The thinking would count as written tokens, on the models that have it only: off, as in Louis (chat.think)
        if think is not None:
            payload["think"] = think
        start: float = time.perf_counter()
        ttft: float | None = None
        try:
            with self.__open("/api/chat", payload, TIMEOUT) as res:
                for line in res:
                    chunk: dict = json.loads(line)
                    if "error" in chunk:
                        raise OllamaError(chunk["error"])
                    message: dict = chunk.get("message") or {}
                    if ttft is None and (message.get("content") or message.get("thinking")):
                        ttft = time.perf_counter() - start
                    if chunk.get("done"):
                        return {**chunk, "ttft": ttft}
        except (OSError, ValueError) as e:
            raise OllamaError(f"no reply: {e}") from e
        raise OllamaError("the reply ended before its end")

    def unload(self, model: str) -> None:
        try:
            self.post("/api/generate", {"model": model, "keep_alive": 0}, 60.0)
        except OllamaError:
            pass

    def loaded(self, model: str | None = None) -> list[dict]:
        models: list[dict] = self.get("/api/ps").get("models") or []
        return [m for m in models if model in (None, m.get("name"), m.get("model"))]

def seconds(chunk: dict, key: str) -> float | None:
    """ A duration of Ollama, in nanoseconds there """
    return chunk[key] / 1e9 if chunk.get(key) else None

def speed(chunk: dict, count: str, duration: str) -> float | None:
    took: float | None = seconds(chunk, duration)
    return chunk.get(count, 0) / took if took else None

def median(values: list) -> float | None:
    present: list[float] = [value for value in values if value is not None]
    return statistics.median(present) if present else None

class Prompts:
    """ Prompts of a given size in tokens, from the code of Louis: what it reads the most """
    def __init__(self):
        self.__text: str = ""
        for path in sorted(glob.glob(os.path.join(HERE, "src", "**", "*.py"), recursive=True)):
            self.__text += read(path) or ""
        # A guess until a first reply tells it, on the low side: a prompt too long would be cut by Ollama
        self.__chars_per_token: float = 3.0

    def make(self, tokens: int) -> tuple[str, int]:
        """
            The prompt and its characters. It starts with something new: Ollama does not evaluate again the start of a
            prompt it has just read, and the prefill would look instant from the second request on
        """
        chars: int = int(tokens * self.__chars_per_token)
        text: str = self.__text or FILLER
        text = (text * (chars // len(text) + 1))[:chars]
        return f"Reference {uuid.uuid4()}\n\n{text}\n\n{INSTRUCTION}", chars

    def learn(self, chars: int, tokens: int) -> None:
        if tokens:
            self.__chars_per_token = chars / tokens

def run_scenario(client: Ollama, prompts: Prompts, model: str, tokens: int, options: dict, think: bool | None,
                 repeat: int, prefill: float | None) -> dict:
    """ The same request several times: their medians, or why it was not sent or did not end """
    if prefill and tokens / prefill > MAX_EXPECTED:
        return {"tokens": tokens, "skipped": f"about {tokens / prefill:.0f} s expected for the prompt alone"}
    done: list[dict] = []
    for _ in range(repeat):
        prompt, chars = prompts.make(tokens)
        try:
            chunk: dict = client.chat(model, prompt, options, think)
        except OllamaError as e:
            return {"tokens": tokens, "error": str(e)}
        prompts.learn(chars, chunk.get("prompt_eval_count", 0))
        done.append(chunk)
    return {
        "tokens"       : round(median([c.get("prompt_eval_count") for c in done]) or 0),
        "written"      : round(median([c.get("eval_count") for c in done]) or 0),
        "ttft"         : median([c["ttft"] for c in done]),
        "prefill_tok_s": median([speed(c, "prompt_eval_count", "prompt_eval_duration") for c in done]),
        "tok_s"        : median([speed(c, "eval_count", "eval_duration") for c in done]),
        "runs"         : len(done),
    }

def bench_model(client: Ollama, prompts: Prompts, model: str, context: int, base: dict, repeat: int, cpu: bool) -> dict:
    """ A model from cold: how long it takes to load, how much memory it holds, and how fast it reads and writes """
    result: dict = {"model": model, "mode": "cpu" if cpu else "default", "scenarios": {}}
    try:
        info: dict = client.post("/api/show", {"model": model})
    except OllamaError as e:
        return {**result, "error": str(e)}
    details: dict = info.get("details") or {}
    result["quantization"] = details.get("quantization_level")
    result["parameters"] = details.get("parameter_size")
    think: bool | None = False if "thinking" in (info.get("capabilities") or []) else None
    options: dict = {**base, "num_ctx": context, "num_predict": WRITTEN, **({"num_gpu": 0} if cpu else {})}

    client.unload(model)
    try:
        first: dict = client.chat(model, "Say hello.", {**options, "num_predict": 8}, think)
        # The tokens of a text, for this model: the prompts of its measures have the same size as those of the others
        prompt, chars = prompts.make(1000)
        prompts.learn(chars, client.chat(model, prompt, {**options, "num_predict": 1}, think).get("prompt_eval_count", 0))
    except OllamaError as e:
        return {**result, "error": str(e)}
    result["load_s"] = seconds(first, "load_duration")
    if held := client.loaded(model):
        size, vram = held[0].get("size", 0), held[0].get("size_vram", 0)
        result["memory"], result["vram"], result["gpu_share"] = size, vram, vram / size if size else None

    prefill: float | None = None
    for name, tokens in SCENARIOS.items():
        wanted: int = int(context * FULL_SHARE) if tokens is None else min(tokens, int(context * FULL_SHARE))
        print(f"  {name} ({wanted} tokens)...", file=sys.stderr, flush=True)
        scenario: dict = run_scenario(client, prompts, model, wanted, options, think, repeat, prefill)
        result["scenarios"][name] = scenario
        prefill = scenario.get("prefill_tok_s") or prefill
    client.unload(model)
    result["level"], result["short_of"] = level_of(result)
    return result

def bench_companions(client: Ollama, installed: set[str], config: dict) -> list[dict]:
    """ What runs next to the chat model: the memory it holds too, on the CPU, as Louis loads it """
    companions: list[dict] = []
    scribe: str = config["scribe.model"]
    embed: str = config["rag.embed.model"]
    for role, model in (("scribe", scribe), ("embedding", embed)):
        if not model:
            continue
        name: str | None = find_model(model, installed)
        entry: dict = {"role": role, "model": model, "installed": name is not None}
        companions.append(entry)
        if name is None:
            continue
        print(f"{role}: {name}...", file=sys.stderr, flush=True)
        try:
            client.unload(name)
            if role == "scribe":
                chunk: dict = client.chat(name, "Write a short title for a session about sorting a list.",
                                          {"num_gpu": 0, "num_ctx": config["scribe.context"], "num_predict": 32})
                entry["tok_s"] = speed(chunk, "eval_count", "eval_duration")
            else:
                client.post("/api/embed", {"model": name, "input": ["a passage of documentation"], "options": {"num_gpu": 0}})
            if held := client.loaded(name):
                entry["memory"] = held[0].get("size", 0)
        except OllamaError as e:
            entry["error"] = str(e)
        client.unload(name)
    return companions

def find_model(model: str, installed: set[str]) -> str | None:
    """ The name of a model as Ollama lists it: nomic-embed-text is nomic-embed-text:latest there """
    for name in (model, f"{model}:latest"):
        if name in installed:
            return name
    return None

def level_of(result: dict) -> tuple[str, list[str]]:
    """ The highest level a run reached, and what it lacks to reach the next. A failed or skipped measure meets no limit """
    scenarios: dict = result.get("scenarios") or {}
    measures: dict[str, float | None] = {
        "tok_s"       : (scenarios.get("typical") or {}).get("tok_s"),
        "typical_ttft": (scenarios.get("typical") or {}).get("ttft"),
        "long_ttft"   : (scenarios.get("long") or {}).get("ttft"),
    }
    def short_of(limits: dict[str, float]) -> list[str]:
        missed: list[str] = []
        for name, limit in limits.items():
            value: float | None = measures[name]
            if name == "tok_s":
                if value is None or value < limit:
                    missed.append(f"writes {number(value)} tok/s, needs {limit:g}")
            elif value is None or value > limit:
                missed.append(f"first token ({name.split('_')[0]}) in {number(value)} s, needs {limit:g}")
        return missed
    below: list[str] = short_of(LEVELS["minimum"])
    if below:
        return BELOW, below
    missed: list[str] = short_of(LEVELS["recommended"])
    return ("minimum", missed) if missed else ("recommended", [])

def number(value: float | None) -> str:
    return "?" if value is None else f"{value:.1f}"

def size(value: int | None) -> str:
    return "?" if value is None else f"{value / GIB:.1f} GiB"

def memory_needs(result: dict) -> dict:
    """
        The memory of the runs and of what runs next to them: it depends on the model and its context, hardly on the
        machine. Enough to run at all (all of it in RAM, or shared with the VRAM), and to fit whole on a GPU
    """
    companions: int = sum(c.get("memory", 0) for c in result.get("companions") or [])
    needs: dict = {}
    for run_ in result.get("runs") or []:
        if run_.get("memory") and run_["mode"] == "default":
            needs[run_["model"]] = {"total": run_["memory"] + companions + RESERVE, "vram": run_["memory"], "ram": companions + RESERVE}
    return needs

def show_machine(machine: dict) -> None:
    cpu: dict = machine["cpu"]
    print(f"System    {machine['system']}{' (WSL)' if machine['wsl'] else ''}, Python {machine['python']}")
    print(f"CPU       {cpu['name'] or '?'}, {cpu['physical_cores'] or '?'} cores, {cpu['threads']} threads"
          f"{', ' + ' '.join(cpu['flags']) if cpu['flags'] else ''}")
    print(f"RAM       {size(machine['ram'])}, {size(machine['ram_available'])} free"
          f"{' (what WSL was given, not all of the machine)' if machine['wsl'] else ''}")
    for gpu in machine["gpus"] or [{"name": "none found", "vram": None}]:
        vram: str = "shared with the RAM" if gpu.get("unified") else f"{size(gpu['vram'])} VRAM, {size(gpu.get('vram_free'))} free"
        print(f"GPU       {gpu['name']}, {vram}")
    print(f"Disk      {size(machine['disk_free'])} free")
    print(f"Ollama    {machine.get('ollama') or 'not reachable'}")
    print(f"Docker    {'yes' if machine['docker'] else 'no (run_code needs it)'}")
    if not machine["python_ok"]:
        print("Warning   Louis needs Python 3.12 or newer")
    if machine["on_battery"]:
        print("Warning   on battery: the measures will be low, plug the machine in")

def show_results(result: dict) -> None:
    rows: list[list[str]] = [["model", "mode", "GPU", "memory", "load", "tok/s", "first token", "first token", "first token", "level"],
                             ["", "", "share", "", "", "", "typical", "long", "full", ""]]
    for r in result["runs"]:
        scenarios: dict = r.get("scenarios") or {}
        share: float | None = r.get("gpu_share")
        rows.append([
            r["model"], r["mode"], "?" if share is None else f"{share:.0%}", size(r.get("memory")), f"{number(r.get('load_s'))} s",
            number((scenarios.get("typical") or {}).get("tok_s")),
            *[f"{number((scenarios.get(name) or {}).get('ttft'))} s" for name in SCENARIOS],
            r.get("level") or BELOW,
        ])
    widths: list[int] = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    print()
    for row in rows:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())
    print()
    for r in result["runs"]:
        if r.get("error"):
            print(f"{r['model']}: {r['error']}")
        for name, scenario in (r.get("scenarios") or {}).items():
            if scenario.get("error") or scenario.get("skipped"):
                print(f"{r['model']} ({r['mode']}), {name}: {scenario.get('error') or scenario['skipped']}")
        for reason in r.get("short_of") or []:
            print(f"{r['model']} ({r['mode']}): {reason}")
    for companion in result["companions"]:
        if not companion["installed"]:
            print(f"{companion['role']}: {companion['model']} is not installed, its memory is not counted (ollama pull {companion['model']})")

def expand(paths: list[str]) -> list[str]:
    """ The result files: a folder stands for its .json files, and a pattern is expanded where the shell does not """
    files: list[str] = []
    for path in paths:
        if os.path.isdir(path):
            files += sorted(glob.glob(os.path.join(path, "*.json")))
        else:
            files += sorted(glob.glob(path)) or [path]
    return files

def requirements(results: list[dict]) -> str:
    """ For each model, the machines measured and the weakest one that reached each level, in Markdown """
    lines: list[str] = []
    models: list[tuple[str, str]] = sorted({(r["model"], r["mode"]) for result in results for r in result.get("runs") or []})
    for model, mode in models:
        rows: list[tuple[dict, dict]] = [(result, r) for result in results for r in result.get("runs") or []
                                         if (r["model"], r["mode"]) == (model, mode)]
        lines += [f"## {model}{' without the GPU' if mode == 'cpu' else ''}", "",
                  "| Machine | CPU | RAM | GPU | VRAM | On GPU | tok/s | First token | Level |", "|---|---|---|---|---|---|---|---|---|"]
        for result, r in rows:
            gpu: dict = (result["machine"]["gpus"] or [{}])[0]
            typical: dict = (r.get("scenarios") or {}).get("typical") or {}
            share: float | None = r.get("gpu_share")
            lines.append(f"| {result.get('label')} | {result['machine']['cpu'].get('name') or '?'} | {size(result['machine'].get('ram'))} "
                         f"| {gpu.get('name') or 'none'} | {size(gpu.get('vram'))} | {'?' if share is None else f'{share:.0%}'} "
                         f"| {number(typical.get('tok_s'))} | {number(typical.get('ttft'))} s | {r.get('level') or BELOW} |")
        lines.append("")
        for level, reached in (("Minimum", ("minimum", "recommended")), ("Recommended", ("recommended",))):
            passing: list[tuple[dict, dict]] = [row for row in rows if row[1].get("level") in reached]
            if not passing:
                lines.append(f"**{level}**: no machine measured reaches it.")
                continue
            result, r = min(passing, key=lambda row: (((row[0]["machine"]["gpus"] or [{}])[0].get("vram") or 0), row[0]["machine"].get("ram") or 0))
            gpu = (result["machine"]["gpus"] or [{}])[0]
            lines.append(f"**{level}**: reached by {result.get('label')}, the weakest one to: {result['machine']['cpu'].get('name') or '?'}, "
                         f"{size(result['machine'].get('ram'))} of RAM, {gpu.get('name') or 'no GPU'}"
                         f"{', ' + size(gpu.get('vram')) + ' of VRAM' if gpu.get('vram') else ''}.")
        needs: list[dict] = [memory_needs(result)[model] for result in results if mode == "default" and model in memory_needs(result)]
        if needs:
            need: dict = max(needs, key=lambda n: n["total"])
            lines.append(f"\nMemory, measured: at least {size(need['total'])} of RAM and VRAM together; to fit whole on a GPU, "
                         f"{size(need['vram'])} of VRAM and {size(need['ram'])} of RAM.")
        lines.append("")
    if len(results) < 3:
        lines.append(f"Measured on {len(results)} machine(s): this tells which levels they reach, not where the line between two levels is. "
                     "Run the benchmark on more machines, the weakest ones above all.")
    return "\n".join(lines)

def load_settings() -> dict:
    """ The settings of Louis next to the script, its defaults when copied alone """
    path: str = os.path.join(HERE, "src", "config", "settings.py")
    try:
        spec = importlib.util.spec_from_file_location("louis_settings", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {**DEFAULTS, **{key: module.settings[key] for key in DEFAULTS if key in module.settings}}
    except Exception:
        return dict(DEFAULTS)

def main() -> int:
    config: dict = load_settings()
    chat_model: str = f"{config['chat.model.name']}:{config['chat.model.parameters']}"
    parser = argparse.ArgumentParser(description="Measures this machine with the models of Louis, and tells the requirements it meets")
    parser.add_argument("--models", nargs="+", default=[chat_model, OTHER_MODEL], help=f"the models to measure (default: {chat_model} {OTHER_MODEL})")
    parser.add_argument("--repeat", type=int, default=3, help="requests per measure, their median is kept (default: 3)")
    parser.add_argument("--context", type=int, default=config["chat.context"], help="num_ctx of the models (default: chat.context)")
    parser.add_argument("--cpu", action="store_true", help="measure each model again without the GPU")
    parser.add_argument("--pull", action="store_true", help="download the missing models instead of leaving them out")
    parser.add_argument("--uri", default=config["chat.uri"], help="the address of Ollama (default: chat.uri)")
    parser.add_argument("--label", default=socket.gethostname(), help="the name of this machine in the results (default: its hostname)")
    parser.add_argument("--out", default="benchmark-results", help="the folder of the results (default: benchmark-results)")
    parser.add_argument("--specs-only", action="store_true", help="tell what the machine is, and measure nothing")
    parser.add_argument("--requirements", nargs="+", metavar="RESULT", help="no measure: the requirements told by these result files or folders")
    args: argparse.Namespace = parser.parse_args()

    if args.requirements:
        results: list[dict] = []
        for path in expand(args.requirements):
            with open(path, encoding="utf-8") as file:
                results.append(json.load(file))
        if not results:
            sys.stderr.write("No result file found.\n")
            return 1
        print(requirements(results))
        return 0

    client: Ollama = Ollama(args.uri)
    machine: dict = machine_spec()
    try:
        machine["ollama"] = client.get("/api/version").get("version")
    except OllamaError:
        machine["ollama"] = None
    show_machine(machine)
    if args.specs_only:
        return 0
    if machine["ollama"] is None:
        sys.stderr.write(f"\nOllama does not answer at {args.uri}: start it (ollama serve), or install it from https://ollama.com/download\n")
        return 1
    if not re.search(r"//(localhost|127\.0\.0\.1|\[::1\])\b", args.uri):
        print(f"Warning   Ollama runs at {args.uri}: the specs above are not those of the machine measured")
    if busy := [m.get("name") for m in client.loaded()]:
        print(f"Warning   already loaded, and may take the memory from the models measured: {', '.join(busy)}")

    installed: set[str] = {m.get("name") for m in client.get("/api/tags").get("models") or []}
    runs: list[dict] = []
    prompts: Prompts = Prompts()
    for model in dict.fromkeys(args.models):
        name: str | None = find_model(model, installed)
        if name is None and args.pull:
            print(f"\nDownloading {model}...", file=sys.stderr, flush=True)
            try:
                client.post("/api/pull", {"model": model}, None)
                installed.add(model)
                name = model
            except OllamaError as e:
                runs.append({"model": model, "mode": "default", "error": f"download failed: {e}"})
                continue
        if name is None:
            runs.append({"model": model, "mode": "default", "error": f"not installed (ollama pull {model}, or --pull)"})
            continue
        for cpu in (False, True) if args.cpu else (False,):
            print(f"\n{name}{' without the GPU' if cpu else ''}", file=sys.stderr, flush=True)
            runs.append(bench_model(client, prompts, name, args.context, config["chat.options"], args.repeat, cpu))

    sizes: dict[str, int] = {m.get("name"): m.get("size", 0) for m in client.get("/api/tags").get("models") or []}
    for r in runs:
        r["disk"] = sizes.get(r["model"])
    result: dict = {
        "version": 1, "date": datetime.now().isoformat(timespec="seconds"), "label": args.label, "machine": machine,
        "settings": {"context": args.context, "repeat": args.repeat, "written": WRITTEN, "levels": LEVELS},
        "runs": runs, "companions": bench_companions(client, installed, config),
    }
    show_results(result)
    print("\n" + requirements([result]))

    os.makedirs(args.out, exist_ok=True)
    path: str = os.path.join(args.out, f"{re.sub(r'[^A-Za-z0-9._-]', '_', args.label)}-{datetime.now():%Y%m%d-%H%M%S}.json")
    with open(path, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    print(f"\nResults written to {path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
