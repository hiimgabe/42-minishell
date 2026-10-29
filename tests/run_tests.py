#!/usr/bin/env python3
"""Black-box Minishell tests; Python 3.8+ standard library, POSIX only."""

import argparse
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile


PROMPT = b"\x1b[0;34mminishell \x1b[0m"
ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Case:
    name: str
    commands: str
    stdout: str = ""
    status: int = 0
    error: bool = False
    files: dict = field(default_factory=dict)
    # Zero-based input-line indices read at the heredoc prompt.
    heredoc: tuple = ()
    eof: bool = False
    reference: bool = True


CASES = [
    Case("echo/basic", "echo hello world", "hello world\n"),
    Case("echo/empty", "echo", "\n"),
    Case("echo/no-newline", "echo -n hello", "hello"),
    Case("echo/repeated-n", "echo -nnn -n hello", "hello"),
    Case("echo/non-option", "echo -nx hello", "-nx hello\n"),
    Case("echo/prompt-like-output", "echo 'minishell text'", "minishell text\n"),
    Case("quotes/single", "echo 'hello   world'", "hello   world\n"),
    Case("quotes/double", 'echo "hello   world"', "hello   world\n"),
    Case("quotes/literal-variable", "echo '$MINITEST'", "$MINITEST\n"),
    Case("quotes/operators", "echo 'a | b > c'", "a | b > c\n"),
    Case("quotes/external-spaces", "printf '[%s]' 'hello world'", "[hello world]"),
    Case("quotes/empty-argument", "printf '[%s]' '' end", "[][end]"),
    Case("expansion/inherited", 'echo "$MINITEST"', "inherited\n"),
    Case("expansion/undefined", 'echo "x$MISSING"', "x\n"),
    Case("expansion/underscore", 'echo "$MINI_TEST"', "underscore\n"),
    Case("env/export", "export MESSAGE=hello\necho $MESSAGE", "hello\n"),
    Case("env/replace", "export MESSAGE=one\nexport MESSAGE=two\necho $MESSAGE", "two\n"),
    Case("env/export-quoted", 'export MESSAGE="hello world"\necho "$MESSAGE"', "hello world\n"),
    Case("env/unset", 'export MESSAGE=hello\nunset MESSAGE\necho "x$MESSAGE"', "x\n"),
    Case("env/unset-missing", "unset MISSING\necho alive", "alive\n"),
    Case("env/unset-exact-name", "export ITEM=one ITEMLONG=two\nunset ITEM\necho $ITEMLONG", "two\n"),
    Case("env/list", "env | grep ^MINITEST=", "MINITEST=inherited\n"),
    Case("env/child-inherits", "export MESSAGE=hello\nenv | grep ^MESSAGE=", "MESSAGE=hello\n"),
    Case("env/export-list", "export MESSAGE=hello\nexport | grep MESSAGE", 'declare -x MESSAGE="hello"\n'),
    Case("env/invalid-name", "export 1BAD=value\necho $?", "1\n", error=True),
    Case("env/leading-underscore", "export _ITEM=hello\necho $_ITEM", "hello\n"),
    Case("directory/pwd", "pwd", "@ROOT@\n"),
    Case("directory/relative", "cd subdir\npwd", "@ROOT@/subdir\n"),
    Case("directory/home", "cd\npwd", "@ROOT@/home\n"),
    Case("directory/previous", "cd subdir\ncd -\npwd", "@ROOT@\n@ROOT@\n"),
    Case("directory/missing", "cd missing-directory\necho $?", "1\n", error=True),
    Case("directory/too-many-args", "cd subdir home\npwd", "@ROOT@\n", error=True),
    Case("directory/redirected-builtin", "cd subdir > out.txt\npwd", "@ROOT@/subdir\n", files={"out.txt": ""}),
    Case("external/path-lookup", "printf hello", "hello"),
    Case("external/absolute-path", "/bin/echo hello", "hello\n"),
    Case("external/relative-path", "./helper", "helper-ok\n"),
    Case("status/success", "true\necho $?", "0\n"),
    Case("status/failure", "false\necho $?", "1\n"),
    Case("status/unknown-command", "minishell_missing_command_xyz\necho $?", "127\n", error=True),
    Case("status/not-executable", "./not-executable\necho $?", "126\n", error=True),
    Case("status/exit-code", "exit 42", status=42),
    Case("status/bare-exit", "false\nexit", status=1),
    Case("status/exit-negative", "exit -1", status=255),
    Case("status/exit-wrap", "exit 256", status=0),
    Case("status/exit-nonnumeric", "exit nope", status=2, error=True),
    Case("status/exit-too-many", "exit 1 2\necho alive", "alive\n", error=True),
    Case("pipes/two-commands", "echo hello | cat", "hello\n"),
    Case("pipes/three-commands", "echo hello | cat | cat", "hello\n"),
    Case("pipes/transform", "echo hello | tr a-z A-Z", "HELLO\n"),
    Case("pipes/last-status-failure", "true | false\necho $?", "1\n"),
    Case("pipes/last-status-success", "false | true\necho $?", "0\n"),
    Case("pipes/builtin-isolation", "cd subdir | cat\npwd", "@ROOT@\n"),
    Case("redirect/output", "echo hello > out.txt", files={"out.txt": "hello\n"}),
    Case("redirect/truncate", "echo first > out.txt\necho second > out.txt", files={"out.txt": "second\n"}),
    Case("redirect/append", "echo first > out.txt\necho second >> out.txt", files={"out.txt": "first\nsecond\n"}),
    Case("redirect/input", "cat < input.txt", "alpha\nbeta\n"),
    Case("redirect/input-output", "cat < input.txt > out.txt", files={"out.txt": "alpha\nbeta\n"}),
    Case("redirect/pipe-output", "echo hello | cat > out.txt", files={"out.txt": "hello\n"}),
    Case("redirect/restore-stdout", "echo hidden > out.txt\necho visible", "visible\n", files={"out.txt": "hidden\n"}),
    Case("redirect/missing-input", "cat < missing.txt\necho $?", "1\n", error=True),
    Case("redirect/multiple-outputs", "echo hello > first.txt > last.txt", files={"first.txt": "", "last.txt": "hello\n"}),
    Case("heredoc/basic", "cat << END\nhello\nEND", "hello\n", heredoc=(1, 2)),
    Case("heredoc/expand", "cat << END\n$MINITEST\nEND", "inherited\n", heredoc=(1, 2)),
    Case("heredoc/quoted-delimiter", "cat << 'END'\n$MINITEST\nEND", "$MINITEST\n", heredoc=(1, 2)),
    # Bash reading a script exits or continues incomplete syntax across lines.
    # Minishell's line-at-a-time parser should diagnose it and accept a new line.
    Case("syntax/missing-target", "echo hello >\necho $?", "2\n", error=True, reference=False),
    Case("syntax/trailing-pipe", "echo hello |\necho $?", "2\n", error=True, reference=False),
    Case("syntax/leading-pipe", "| cat\necho $?", "2\n", error=True, reference=False),
    Case("syntax/unclosed-quote", "echo 'unfinished\necho $?", "2\n", error=True, reference=False),
    Case("input/blank-lines", "\n   \necho alive", "alive\n"),
    Case("input/eof", "", eof=True),
]


def clean_transcript(raw, lines, heredoc=(), eof=False):
    """Remove only exact, ordered Readline prompts and their input echoes.

    Never strip generic lines, whitespace, or ANSI codes from command output.
    Unexpected/missing echoes are harness failures, not silently ignored data.
    """
    chunks = []
    position = 0
    for index, line in enumerate(lines):
        prefix = b"> " if index in heredoc else PROMPT
        # Readline may clear a previous longer input after printing the prompt.
        echo = re.compile(re.escape(prefix) + rb"(?:\x1b\[K)?"
                          + re.escape(line.encode() + b"\n"))
        match = echo.search(raw, position)
        if match is None:
            raise ValueError("missing input echo for line %d: %r; transcript=%r"
                             % (index + 1, line, raw[:1500]))
        chunks.append(raw[position:match.start()])
        position = match.end()
    tail = raw[position:]
    if eof:
        if not tail.endswith(PROMPT + b"exit\n"):
            raise ValueError("missing EOF prompt/exit message: %r" % tail)
        tail = tail[:-len(PROMPT + b"exit\n")]
    chunks.append(tail)
    return b"".join(chunks)


def stop_group(process):
    # The shell and its pipeline children share this new process group.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def disable_core_dumps():
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run_case(case, binary, timeout, reference=False):
    with tempfile.TemporaryDirectory(prefix="minishell-test-") as directory:
        cwd = Path(directory).resolve()
        (cwd / "subdir").mkdir()
        (cwd / "home").mkdir()
        (cwd / "input.txt").write_bytes(b"alpha\nbeta\n")
        (cwd / "helper").write_bytes(b"#!/bin/sh\nprintf 'helper-ok\\n'\n")
        (cwd / "helper").chmod(0o755)
        (cwd / "not-executable").write_bytes(b"#!/bin/sh\nexit 0\n")
        (cwd / "not-executable").chmod(0o644)
        env = {
            "PATH": "/usr/bin:/bin", "HOME": str(cwd / "home"),
            "PWD": str(cwd), "OLDPWD": str(cwd), "SHLVL": "1",
            "LC_ALL": "C", "TERM": "xterm", "COLUMNS": "4096",
            "INPUTRC": "/dev/null", "MINITEST": "inherited",
            "MINI_TEST": "underscore",
        }
        lines = case.commands.split("\n") if case.commands else []
        if not case.eof and not (lines and (lines[-1] == "exit" or lines[-1].startswith("exit "))):
            lines.append("exit 0")
        script = "\n".join(lines) + ("\n" if lines else "")
        argv = [binary, "--noprofile", "--norc"] if reference else [binary]
        process = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=cwd, env=env,
            start_new_session=True, preexec_fn=disable_core_dumps,
        )
        try:
            out, err = process.communicate(script.encode(), timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_group(process)
            process.communicate()
            return ["timed out after %g seconds (shell and children killed)" % timeout]
        except BaseException:
            stop_group(process)
            process.communicate()
            raise
        finally:
            stop_group(process)

        failures = []
        if process.returncode != case.status:
            failures.append("exit status: expected %d, got %d" % (case.status, process.returncode))
        if not reference:
            try:
                out = clean_transcript(out, lines, case.heredoc, case.eof)
            except ValueError as exc:
                failures.append("transcript: " + str(exc))
        expected = case.stdout.replace("@ROOT@", str(cwd)).encode()
        if out != expected:
            failures.append("stdout: expected %r, got %r" % (expected, out[:1500]))
        if bool(err) != case.error:
            failures.append("stderr: expected %s, got %r" % (
                "a diagnostic" if case.error else "no diagnostic", err[:1500]))
        elif err and failures:
            failures.append("stderr diagnostic: %r" % err[:1500])
        for name, content in case.files.items():
            path = cwd / name
            if not path.is_file():
                failures.append("missing output file: " + name)
            elif path.read_bytes() != content.encode():
                failures.append("file %s: expected %r, got %r" % (
                    name, content.encode(), path.read_bytes()[:1500]))
        return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default=str(ROOT / "minishell"), help="Minishell executable")
    parser.add_argument("--filter", default="", help="run names containing this text")
    parser.add_argument("--list", action="store_true", help="list matching cases without running")
    parser.add_argument("--timeout", type=float, default=3.0, help="seconds per case (default: 3)")
    parser.add_argument("--reference", action="store_true", help="validate expectations against Bash instead")
    args = parser.parse_args()
    cases = [case for case in CASES if args.filter in case.name
             and (not args.reference or case.reference)]
    if not cases:
        parser.error("no tests match the filter")
    if args.list:
        print("\n".join(case.name for case in cases))
        return 0
    if os.name != "posix":
        parser.error("run inside Linux/WSL or another POSIX environment")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    binary = shutil.which("bash") if args.reference else str(Path(args.binary).resolve())
    if not binary or not os.path.isfile(binary) or not os.access(binary, os.X_OK):
        parser.error("executable not found; run make first or use --binary PATH")
    for command in ("cat", "grep", "tr", "printf", "true", "false"):
        if not shutil.which(command, path="/usr/bin:/bin"):
            parser.error("required command is missing: " + command)
    print("Testing %s (%d cases)" % (binary, len(cases)), flush=True)
    failed = 0
    try:
        for case in cases:
            failures = run_case(case, binary, args.timeout, args.reference)
            print("%s %s" % ("FAIL" if failures else "PASS", case.name), flush=True)
            for failure in failures:
                print("  " + failure, flush=True)
            failed += bool(failures)
    except OSError as exc:
        print("Test infrastructure error: %s" % exc, file=sys.stderr)
        return 2
    print("\n%d passed, %d failed, %d total" % (len(cases) - failed, failed, len(cases)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
