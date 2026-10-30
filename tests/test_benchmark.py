##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of benchmark.py: the levels, the requirements, and a whole run against a scripted Ollama
##
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import sys
import threading
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import benchmark
from benchmark import BELOW, Ollama, OllamaError, Prompts, bench_model, level_of, requirements

def timed(tok_s, ttft, long_ttft=None):
    """ A run whose measures are these """
    return {"scenarios": {"typical": {"tok_s": tok_s, "ttft": ttft}, "long": {"ttft": long_ttft if long_ttft is not None else ttft}}}

class FakeOllama(BaseHTTPRequestHandler):
    """ Answers as Ollama does, and keeps the requests it was sent """
    chats: list = []
    refuse: str | None = None

    def log_message(self, *args):
        pass

    def __send(self, code: int, *chunks: dict):
        self.send_response(code)
        self.end_headers()
        for chunk in chunks:
            self.wfile.write((json.dumps(chunk) + "\n").encode())

    def do_GET(self):
        self.__send(200, {"models": [{"name": "fake:1b", "model": "fake:1b", "size": 8 * 2 ** 30, "size_vram": 6 * 2 ** 30}]})

    def do_POST(self):
        body: dict = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/show":
            self.__send(200, {"details": {"quantization_level": "Q4_K_M"}, "capabilities": ["completion", "thinking"]})
        elif self.path != "/api/chat":
            self.__send(200, {})
        elif FakeOllama.refuse:
            self.__send(500, {"error": FakeOllama.refuse})
        else:
            FakeOllama.chats.append(body)
            self.__send(200, {"message": {"content": "Hello"}},
                        {"done": True, "message": {}, "load_duration": 2 * 10 ** 9, "prompt_eval_count": len(body["messages"][0]["content"]) // 4,
                         "prompt_eval_duration": 10 ** 9, "eval_count": 100, "eval_duration": 2 * 10 ** 9})

class LevelTests(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(level_of(timed(50, 2))[0], "recommended")
        self.assertEqual(level_of(timed(50, 2, 40))[0], "minimum")
        self.assertEqual(level_of(timed(15, 20))[0], "minimum")
        self.assertEqual(level_of(timed(2.5, 34))[0], BELOW)

    def test_a_measure_missing_meets_no_limit(self):
        level, missed = level_of({"scenarios": {"typical": {"error": "out of memory"}}})
        self.assertEqual(level, BELOW)
        self.assertEqual(len(missed), 2)
        self.assertEqual(level_of({"error": "not installed"})[0], BELOW)

class PromptTests(unittest.TestCase):
    def test_each_prompt_starts_with_something_new(self):
        """ Ollama would not evaluate again a start it has just read: the prefill would look instant """
        prompts: Prompts = Prompts()
        first, second = prompts.make(100)[0], prompts.make(100)[0]
        self.assertNotEqual(first[:50], second[:50])

    def test_the_size_follows_what_ollama_counted(self):
        prompts: Prompts = Prompts()
        chars: int = prompts.make(1000)[1]
        prompts.learn(chars, 500)
        self.assertEqual(prompts.make(1000)[1], chars * 2)

class RunTests(unittest.TestCase):
    def setUp(self):
        FakeOllama.chats, FakeOllama.refuse = [], None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.client: Ollama = Ollama(f"http://127.0.0.1:{self.server.server_address[1]}")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def bench(self, cpu=False) -> dict:
        return bench_model(self.client, Prompts(), "fake:1b", 12288, {"temperature": 0.6}, 2, cpu)

    def test_a_whole_run(self):
        result: dict = self.bench()
        self.assertEqual(result["level"], "recommended")
        self.assertEqual(result["load_s"], 2.0)
        self.assertEqual(result["gpu_share"], 0.75)
        typical: dict = result["scenarios"]["typical"]
        self.assertEqual(typical["tok_s"], 50.0)
        self.assertEqual(typical["runs"], 2)
        # The right size from the first measure on: the models are compared on the same prompts
        self.assertAlmostEqual(typical["tokens"], 3200, delta=50)
        # The thinking off, on a model that has it, and the same context on every request: a new one reloads the model
        self.assertTrue(all(chat["think"] is False for chat in FakeOllama.chats))
        self.assertEqual({chat["options"]["num_ctx"] for chat in FakeOllama.chats}, {12288})
        # The full context stays in what the window of Louis leaves it: a longer prompt would be cut by Ollama
        self.assertLessEqual(result["scenarios"]["full"]["tokens"], 12288)

    def test_without_the_gpu(self):
        self.assertEqual(self.bench(cpu=True)["mode"], "cpu")
        self.assertTrue(all(chat["options"]["num_gpu"] == 0 for chat in FakeOllama.chats))

    def test_a_model_ollama_refuses_is_told_not_raised(self):
        FakeOllama.refuse = "model requires more system memory"
        result: dict = self.bench()
        self.assertEqual(result["error"], "model requires more system memory")

    def test_nobody_answers(self):
        self.assertRaises(OllamaError, Ollama("http://127.0.0.1:9").get, "/api/version", 0.5)

    def test_a_scenario_too_long_is_skipped(self):
        scenario: dict = benchmark.run_scenario(self.client, Prompts(), "fake:1b", 20000, {}, None, 2, prefill=10.0)
        self.assertIn("skipped", scenario)
        self.assertEqual(FakeOllama.chats, [])

class RequirementTests(unittest.TestCase):
    @staticmethod
    def machine(label: str, vram: int, ram: int, tok_s: float, ttft: float) -> dict:
        run: dict = {"model": "m:1b", "mode": "default", "memory": 7 * 2 ** 30, **timed(tok_s, ttft)}
        run["level"] = level_of(run)[0]
        return {"label": label, "machine": {"cpu": {"name": "cpu"}, "ram": ram * 2 ** 30, "gpus": [{"name": "gpu", "vram": vram * 2 ** 30}]},
                "runs": [run], "companions": []}

    def test_the_weakest_machine_of_each_level(self):
        text: str = requirements([self.machine("big", 24, 64, 80, 1), self.machine("mid", 8, 16, 40, 3),
                                  self.machine("low", 6, 16, 15, 20), self.machine("old", 0, 8, 2, 90)])
        self.assertIn("**Minimum**: reached by low", text)
        self.assertIn("**Recommended**: reached by mid", text)
        # The memory of the model, with what the system and Louis need
        self.assertIn("at least 10.0 GiB", text)

    def test_one_machine_tells_no_line(self):
        self.assertIn("Measured on 1 machine", requirements([self.machine("only", 6, 16, 15, 20)]))

    def test_no_machine_reaches_it(self):
        self.assertIn("**Minimum**: no machine measured reaches it", requirements([self.machine("old", 0, 8, 2, 90)]))

if __name__ == "__main__":
    unittest.main()
