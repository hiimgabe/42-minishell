# Minishell

A small Unix-style shell written in C for the 42 school Minishell project. It implements an interactive command loop, builtins, external command execution, pipelines, redirections, and environment variable expansion.

The project explores process creation, file descriptors, inter-process communication, signals, parsing, and memory management. It uses GNU Readline for terminal input and the included Libft for utility functions.

## Build and run

### Requirements

- A Unix/POSIX environment with a terminal.
- A C compiler available as `cc`.
- `make` and `ar`.
- GNU Readline headers and library, including `readline/readline.h` and `readline/history.h`.

The code depends on Unix APIs such as `fork`, `execve`, `pipe`, and `dup2`. On Windows, use a Linux environment such as WSL; the supplied Makefile does not target native Windows.

From the project directory:

```sh
make
./minishell
```

The build compiles the bundled Libft, creates object files under `objs/`, and links the `minishell` executable with `-lreadline`. Compiler flags are `-Wall -Werror -Wextra -g`.

Start the executable without arguments. Command strings passed with `-c` and script filenames are not supported.

### Make targets

| Command | Purpose |
| --- | --- |
| `make` / `make all` | Build Libft and the shell. |
| `make clean` | Remove shell and Libft object files, including `objs/`. |
| `make fclean` | Also remove `minishell` and `includes/LIBFT/libft.a`. |
| `make re` | Remove build outputs and rebuild. |
| `make test` | Build the shell and run the automated behavior tests. |
| `make test-harness` | Check the Python test runner itself. |

If compilation cannot find the Readline headers or the linker cannot find `-lreadline`, ensure the Readline development files are installed and visible to the compiler and linker.

## Features

- Interactive `minishell` prompt with Readline editing and in-memory command history.
- External commands resolved through `PATH`, plus executable paths such as `/bin/ls` or `./program`.
- Seven builtins: `echo`, `cd`, `pwd`, `export`, `unset`, `env`, and `exit`.
- Pipelines using `|`.
- Input redirection with `<`, output redirection with `>`, and append redirection with `>>`.
- Heredocs using `<<`, with a secondary `> ` prompt.
- Single- and double-quote handling, environment expansion through `$NAME`, and status expansion through `$?`.
- Syntax checks for unclosed quotes and malformed pipe or redirection expressions.
- Signal handling for the prompt, child processes, and heredoc input.

These features describe the implementation's scope; compatibility limitations are listed below.

## Builtins

| Builtin | Usage | Behavior |
| --- | --- | --- |
| `echo` | `echo [-n] [text ...]` | Print arguments; `-n` suppresses the trailing newline. |
| `cd` | `cd [directory]` | Change directory; no argument uses `HOME`, and `cd -` uses `OLDPWD`. |
| `pwd` | `pwd` | Print the current working directory. |
| `export` | `export [NAME=value ...]` | Add or replace environment entries; no arguments prints a sorted export listing. |
| `unset` | `unset NAME [...]` | Remove environment entries. |
| `env` | `env` | Print entries containing `=`; command arguments are not supported. |
| `exit` | `exit [status]` | Leave the shell, optionally with a numeric status. |

The shell keeps its own copy of the inherited environment and passes it to external commands. Standalone state-changing builtins run in the shell process when there are no redirections. Commands in pipelines run in child processes.

## Usage examples

Enter the following commands inside Minishell, one line at a time.

### Commands and environment

```sh
pwd
ls -l
export MESSAGE=hello
echo "$MESSAGE"
echo '$MESSAGE'
unset MESSAGE
cd /tmp
cd -
```

Double-quoted variables are expanded; single-quoted variables remain literal.

### Pipelines and files

```sh
ls | wc -l
echo hello > minishell-demo.txt
echo again >> minishell-demo.txt
cat < minishell-demo.txt
```

The redirection examples create or overwrite `minishell-demo.txt` in the current directory, then append to it.

### Heredocs

```sh
cat << EOF
Hello from minishell
EOF
```

Enter the delimiter on its own line to finish input. An unquoted delimiter allows variable expansion in the heredoc body; quoting the delimiter, as in `cat << 'EOF'`, disables that expansion.

### Exit status

```sh
ls /a-directory-that-does-not-exist
echo $?
exit 0
```

`$?` exposes the stored status of the preceding command. The execution code collects child statuses with `waitpid` and uses `128 + signal number` for children terminated by a signal.

### Keyboard controls

| Input | At the interactive prompt |
| --- | --- |
| `Ctrl-C` | Clear the current input and display a fresh prompt; set status to `130`. |
| `Ctrl-\` | Ignore the quit signal. |
| `Ctrl-D` on an empty line | Handle end-of-file, print `exit`, and terminate. |

## Project layout

```text
.
|-- Makefile
|-- README.md
|-- inc/
|   `-- minishell.h       Shared structures, declarations, and system headers
|-- includes/
|   `-- LIBFT/           Bundled C utility library and its Makefile
|-- tests/
|   |-- run_tests.py     Shell behavior cases and test runner
|   `-- test_runner.py   Checks for output capture and failure detection
`-- srcs/
    |-- main.c          Initialization, environment copy, and shell startup
    |-- builtins/       Builtins and variable expansion
    |-- parser/         Readline loop, operator spacing, and token splitting
    |-- quotes/         Quote processing
    |-- execution/      Command dispatch, child creation, execve, and waiting
    |-- pipes/          Pipeline creation and descriptor routing
    |-- redirects/      File redirections and heredoc input
    |-- signals/        Prompt, execution, and heredoc signal handling
    |-- error/          Error messages and formatted error output
    |-- free/           Cleanup and exit handling
    `-- helpers/        PATH lookup, token checks, and shared utilities
```

## How a command is processed

1. `main` initializes the shell state, copies the environment, installs signal handlers, and updates `SHLVL`.
2. The parser reads a line, records nonblank input in history, and spaces operators outside quotes.
3. Input is split into tokens, checked, processed for quotes and variables, and prepared for heredocs.
4. The executor dispatches builtins or creates child processes for external commands and pipelines.
5. Pipes and redirections connect standard input and output. External programs run through `execve`.
6. The parent waits for children, records their status, restores standard descriptors as needed, and frees per-command data.

The shared `t_mini` structure holds environment entries, tokens, execution arguments, process IDs, and file descriptors. The global `g_signal` stores status and signal information.

## Scope and known limitations

This is an educational shell implementing a subset of Bash behavior.

- Logical operators (`&&`, `||`), command lists (`;`), background jobs (`&`), subshells, wildcard expansion, and command substitution are not implemented.
- Unclosed quotes produce an error instead of opening a continuation prompt.
- History is kept for the current process; no history-file loading or saving is implemented.
- External command arguments are reconstructed and split on spaces in `add_option`, so quoted arguments containing spaces may lose their original grouping.
- Variable expansion recognizes alphanumeric names but does not include underscores in its name scanner. The export validator also rejects names beginning with `_`.
- State-changing builtins executed with redirections take the child-process path, so their changes do not persist in the parent shell.
- End-of-file currently exits with status `0`.

## Automated tests

Run the suite from the project directory in Linux/WSL or another POSIX environment:

```sh
make test
```

Testing requires Python 3.8 or newer, plus the standard Unix commands `cat`, `grep`, `tr`, `printf`, `true`, and `false` in `/usr/bin` or `/bin`, and `/bin/sh` and `/bin/echo`. No Python packages need to be installed. Bash is additionally required for reference validation and the runner's execution self-tests.

The 70 behavior tests cover builtins, quotes, environment variables, directory changes, external commands, exit statuses, pipelines, file redirections, heredocs, malformed input, blank lines, and end-of-file. Each case starts a fresh shell with a controlled environment in a temporary directory. File checks compare actual contents, and output checks preserve spaces and trailing newlines. Error cases check that a diagnostic is present without requiring Bash's exact wording.

The runner feeds commands through standard input and removes the current shell's exact Readline prompts and input echoes before comparing output. Prompt changes may require updating `PROMPT` and `clean_transcript` in `tests/run_tests.py`. These are behavior tests; interactive keyboard signals, memory leaks, and full 42 evaluation coverage are not tested.

Each case has a three-second timeout. A timeout terminates the shell's process group, including pipeline children. Temporary test files are removed automatically. The runner prints `PASS` or `FAIL` for each case, shows mismatches, and returns `0` if all cases pass, `1` for test failures, or `2` for setup errors. `make test` propagates a failure as a nonzero Make exit status.

### Select tests and validate the runner

```sh
make test TEST_ARGS="--filter pipes/"
python3 -B tests/run_tests.py --list
python3 -B tests/run_tests.py --binary ./minishell --timeout 5
python3 -B tests/run_tests.py --reference
make test-harness
```

`--reference` runs the 66 shared cases against Bash to check their expected results. Four syntax-recovery cases are excluded because Minishell processes one line at a time, while Bash reading a script may terminate on a syntax error or continue an incomplete command across lines. `make test-harness` checks prompt cleanup, preservation of real output, mismatch detection, crash detection, and timeout cleanup.

The initial run on Ubuntu/WSL found **57 passing and 13 failing Minishell cases**. The failures expose existing differences in quoted arguments, undefined and underscore-containing variables, exact-name removal by `unset`, builtin execution with pipes or redirections, bare `exit`, and syntax diagnostics/statuses. These remain ordinary failing tests so future fixes can be verified; they are not skipped or marked as expected failures. The C implementation was unchanged when the suite was added.

To add a case, append a `Case` to `CASES` in `tests/run_tests.py` with a descriptive name, command lines, and expected output. Set `status` for an explicit exit code, `error=True` when stderr must contain a diagnostic, and `files` for expected file contents. Unless the case ends with `exit` or sets `eof=True`, the runner appends `exit 0`; use `echo $?` to assert the status of an earlier command. Use `@ROOT@` in expected output for the case's temporary directory. Heredoc cases must identify the zero-based input-line indices read at the secondary prompt.
