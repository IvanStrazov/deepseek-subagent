"""Offline tests for scripts/ds.py: a fake DeepSeek server on localhost (stdlib only)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "ds.py"
SECRET = "sk-test-0123456789abcdef"


class Fake(BaseHTTPRequestHandler):
    """Plays a scripted model: the first reply of a conversation asks for a tool, the next one answers."""
    script = []
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.seen.append({"auth": self.headers.get("Authorization"), "body": body})
        msgs = body["messages"]
        tool_results = [m["content"] for m in msgs if m["role"] == "tool"]
        step = Fake.script[min(len(tool_results), len(Fake.script) - 1)] if body.get("tools") else {"content": "plain answer"}
        if callable(step):
            step = step(tool_results)
        out = {"choices": [{"message": {"role": "assistant", **step}}],
               "usage": {"prompt_tokens": 1000, "prompt_cache_hit_tokens": 600, "completion_tokens": 100}}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def tool(name, **args):
    return {"content": "", "tool_calls": [{"id": f"c-{name}", "type": "function",
                                           "function": {"name": name, "arguments": json.dumps(args)}}]}


class DsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.work = self.tmp / "work"
        self.work.mkdir()
        (self.work / "a.txt").write_text("hello from a\n", encoding="utf-8")
        (self.tmp / "outside.txt").write_text("secret outside\n", encoding="utf-8")
        envf = self.tmp / "keys.env"
        envf.write_text(f"DEEPSEEK_API_KEY={SECRET}\n", encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
        self.env.update(DEEPSEEK_SUBAGENT_DIR=str(self.tmp / "conf"), PYTHONIOENCODING="utf-8",
                        DEEPSEEK_BASE_URL=f"http://127.0.0.1:{self.srv.server_port}")
        self.envf = envf
        Fake.seen = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ds(self, *args, ok=True):
        r = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=str(self.work), env=self.env,
                           capture_output=True, text=True, encoding="utf-8")
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def test_setup_never_prints_key(self):
        r = self.ds("status", ok=False)
        self.assertIn("NOT FOUND", r.stdout)
        r = self.ds("setup", "--key-file", str(self.envf))
        self.assertIn("key: found", r.stdout)
        self.assertNotIn(SECRET, r.stdout + r.stderr)
        self.assertNotIn(SECRET, (self.tmp / "conf" / "config.json").read_text(encoding="utf-8"))

    def test_run_reads_file_and_reports_cost(self):
        self.ds("setup", "--key-file", str(self.envf))
        Fake.script = [tool("read_file", path="a.txt"), lambda res: {"content": "file says: " + res[-1].split("\t")[1]}]
        r = self.ds("run", "what is in a.txt?")
        self.assertIn("file says: hello from a", r.stdout)
        # 2 calls x (400 miss * 0.30 + 600 hit * 0.006 + 100 out * 1.20) / 1e6
        self.assertIn("= $0.0005 peak", r.stdout)
        self.assertEqual(Fake.seen[0]["auth"], f"Bearer {SECRET}")
        self.assertIn("1 task(s)", self.ds("usage").stdout)

    def test_confined_and_read_only_by_default(self):
        self.ds("setup", "--key-file", str(self.envf))
        Fake.script = [tool("read_file", path="../outside.txt"), tool("write_file", path="x.txt", content="x"),
                       lambda res: {"content": " || ".join(res)}]
        out = self.ds("run", "try to escape").stdout
        self.assertIn("outside the allowed folder", out)
        self.assertIn("unknown or disabled tool: write_file", out)
        self.assertNotIn("secret outside", out)
        self.assertFalse((self.work / "x.txt").exists())
        tools = [t["function"]["name"] for t in Fake.seen[0]["body"]["tools"]]
        self.assertEqual(sorted(tools), ["grep", "list_files", "read_file"])

    def test_write_and_bash_when_allowed_with_deny_list(self):
        self.ds("setup", "--key-file", str(self.envf))
        Fake.script = [tool("write_file", path="out/r.md", content="done"),
                       tool("bash", command="git push origin main"),
                       tool("bash", command="echo hi"), lambda res: {"content": " || ".join(res)}]
        out = self.ds("run", "write it", "--write", "--bash").stdout
        self.assertEqual((self.work / "out" / "r.md").read_text(encoding="utf-8"), "done")
        self.assertIn("refused: command not allowed", out)
        self.assertIn("hi", out)
        self.assertIn("files written: out/r.md", out.replace("\\", "/"))

    def test_ask_and_batch(self):
        self.env["DEEPSEEK_API_KEY"] = SECRET
        r = self.ds("ask", "summarize", "--file", "a.txt")
        self.assertIn("plain answer", r.stdout)
        self.assertIn("hello from a", Fake.seen[-1]["body"]["messages"][0]["content"])
        Fake.script = [{"content": "batch done"}]
        tasks = self.tmp / "tasks.jsonl"
        tasks.write_text("\n".join(json.dumps({"id": f"t{i}", "task": "go", "dir": str(self.work)}) for i in range(3)),
                         encoding="utf-8")
        r = self.ds("batch", str(tasks), "--workers", "3")
        self.assertIn("3 task(s)", r.stdout)
        self.assertEqual(len(list((self.tmp / "tasks").glob("t*.md"))), 3)
        self.assertNotIn("FAIL", r.stdout)
        tasks.write_text(json.dumps({"id": "../evil", "task": "go"}) + "\n" + json.dumps({"task": "no id"}),
                         encoding="utf-8")
        self.ds("batch", str(tasks))
        self.assertFalse((self.tmp / "evil.md").exists())          # ids never leave --out
        self.assertTrue((self.tmp / "tasks" / "evil.md").is_file())
        self.assertTrue((self.tmp / "tasks" / "task2.md").is_file())  # stable fallback id


if __name__ == "__main__":
    unittest.main()
