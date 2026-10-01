"""Smoke tests for tokw."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

TOKW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tokw.py")


def run_tokw(*args):
    return subprocess.run(
        [sys.executable, TOKW, *args],
        capture_output=True, text=True,
    )


class TokwSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relpath, data, binary=False):
        full = os.path.join(self.dir, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        mode = "wb" if binary else "w"
        kw = {} if binary else {"encoding": "utf-8"}
        with open(full, mode, **kw) as f:
            f.write(data)
        return full

    def test_ascii_estimate_is_quarter_of_chars(self):
        # 400 ASCII chars ~= 100 tokens
        f = self.write("a.txt", "x" * 400)
        out = run_tokw("--json", f)
        self.assertEqual(out.returncode, 0)
        payload = json.loads(out.stdout)
        self.assertEqual(payload["files"][0]["est_tokens"], 100)

    def test_cjk_chars_count_about_one_each(self):
        # 100 CJK chars ~= 100 tokens
        f = self.write("c.txt", "中" * 100)
        out = run_tokw("--json", f)
        self.assertEqual(out.returncode, 0)
        payload = json.loads(out.stdout)
        self.assertEqual(payload["files"][0]["est_tokens"], 100)

    def test_recursive_walk_skips_git_and_node_modules(self):
        self.write("keep/main.py", "print('hi')")
        self.write(".git/objects/blob", "x" * 4000)
        self.write("node_modules/pkg/index.js", "y" * 4000)
        self.write("sub/__pycache__/cached.pyc", "z" * 4000)
        out = run_tokw("--json", "-r", self.dir)
        self.assertEqual(out.returncode, 0)
        payload = json.loads(out.stdout)
        paths = [f["path"] for f in payload["files"]]
        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0].endswith(os.path.join("keep", "main.py")))

    def test_binary_file_is_skipped(self):
        self.write("data.bin", b"\x89PNG\x00\x01\x02\xff" * 100, binary=True)
        self.write("note.txt", "hello")
        out = run_tokw("--json", "-r", self.dir)
        self.assertEqual(out.returncode, 0)
        payload = json.loads(out.stdout)
        self.assertEqual(len(payload["files"]), 1)
        self.assertTrue(payload["files"][0]["path"].endswith("note.txt"))

    def test_latin1_not_decoded_as_utf16(self):
        # Regression: even-length latin-1 bytes used to "decode" as UTF-16
        # into garbage CJK, inflating the estimate. Must decode as latin-1.
        raw = "café naïve résumé!".encode("latin-1")
        self.assertEqual(len(raw) % 2, 0)
        self.write("latin1.txt", raw, binary=True)
        out = run_tokw("--json", self.dir + "/latin1.txt")
        self.assertEqual(out.returncode, 0)
        payload = json.loads(out.stdout)
        self.assertEqual(payload["files"][0]["chars"], len(raw.decode("latin-1")))
        self.assertEqual(payload["files"][0]["est_tokens"], 4)

    def test_json_output_is_valid(self):
        f = self.write("j.txt", "hello world")
        out = run_tokw("--json", f)
        self.assertEqual(out.returncode, 0)
        payload = json.loads(out.stdout)
        self.assertIn("budget", payload)
        self.assertIn("total_est_tokens", payload)
        self.assertIn("files", payload)
        self.assertIn("chars", payload["files"][0])
        self.assertIn("est_tokens", payload["files"][0])

    def test_budget_warning_appears(self):
        # 400 tokens > 10% of a 100-token budget
        f = self.write("big.txt", "x" * 1600)
        out = run_tokw(f, "--budget", "100")
        self.assertEqual(out.returncode, 0)
        self.assertIn("over 10% of budget", out.stdout)

    def test_exit_2_on_unreadable_path(self):
        out = run_tokw(os.path.join(self.dir, "does-not-exist.txt"))
        self.assertEqual(out.returncode, 2)

    def test_ext_filter(self):
        self.write("a.py", "x" * 100)
        self.write("b.md", "y" * 100)
        self.write("c.log", "z" * 100)
        out = run_tokw("--json", "-r", self.dir, "--ext", ".py,.md")
        self.assertEqual(out.returncode, 0)
        payload = json.loads(out.stdout)
        exts = {os.path.splitext(f["path"])[1] for f in payload["files"]}
        self.assertEqual(exts, {".py", ".md"})


if __name__ == "__main__":
    unittest.main()
