"""Checks that the harness preserves real output and detects failures."""

import os
import shutil
import time
import unittest

from run_tests import Case, PROMPT, clean_transcript, run_case


class TranscriptTests(unittest.TestCase):
    def test_no_newline_and_clear_sequence(self):
        raw = PROMPT + b"echo -n hello\nhello" + PROMPT + b"\x1b[Kexit 0\n"
        self.assertEqual(clean_transcript(raw, ["echo -n hello", "exit 0"]), b"hello")

    def test_preserves_whitespace_and_ansi_in_output(self):
        output = b"  minishell text\n> text\n\x1b[31mred\x1b[0m\n"
        raw = PROMPT + b"./helper\n" + output + PROMPT + b"exit 0\n"
        self.assertEqual(clean_transcript(raw, ["./helper", "exit 0"]), output)

    def test_heredoc_echoes_are_removed_once(self):
        raw = PROMPT + b"cat << END\n> hello\n> END\n> hello\n" + PROMPT + b"exit 0\n"
        self.assertEqual(clean_transcript(
            raw, ["cat << END", "hello", "END", "exit 0"], (1, 2)), b"> hello\n")

    def test_missing_echo_is_not_silently_removed(self):
        with self.assertRaises(ValueError):
            clean_transcript(PROMPT + b"echo wrong\n", ["echo right"])

    def test_eof(self):
        self.assertEqual(clean_transcript(PROMPT + b"exit\n", [], eof=True), b"")


@unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "requires POSIX and Bash")
class ExecutionTests(unittest.TestCase):
    def run_reference(self, case, timeout=2):
        return run_case(case, shutil.which("bash"), timeout, reference=True)

    def test_checks_stdout_status_and_stderr(self):
        errors = self.run_reference(Case("wrong", "echo actual\nexit 7", "expected\n", error=True))
        self.assertTrue(any("stdout:" in message for message in errors))
        self.assertTrue(any("exit status:" in message for message in errors))
        self.assertTrue(any("stderr:" in message for message in errors))

    def test_checks_files(self):
        errors = self.run_reference(Case("files", "echo actual > out.txt", files={
            "out.txt": "expected\n", "missing.txt": ""}))
        self.assertTrue(any("file out.txt:" in message for message in errors))
        self.assertTrue(any("missing output file:" in message for message in errors))

    def test_timeout_kills_children_with_open_output_pipes(self):
        start = time.monotonic()
        errors = self.run_reference(Case("hang", "sleep 10 | cat"), timeout=0.15)
        self.assertTrue(any("timed out" in message for message in errors))
        self.assertLess(time.monotonic() - start, 3)

    def test_crash_is_failure(self):
        errors = self.run_reference(Case("crash", "kill -SEGV $$"))
        self.assertTrue(any("exit status:" in message for message in errors))


if __name__ == "__main__":
    unittest.main()
