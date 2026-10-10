"""Run one line of input against the backend and record the outcome."""

from __future__ import annotations

import time

from prompter.output import write_stderr, write_stdout
from prompter.state import ExitShell, ShellState

# Handled here so they work the same against every backend.
SHELL_BUILTINS = frozenset({"exit", "quit"})


async def execute(state: ShellState, line: str) -> int:
    if line.split()[0] in SHELL_BUILTINS:
        raise ExitShell
    start = time.perf_counter()
    try:
        status = await state.backend.run(line, write_stdout, write_stderr)
    finally:
        state.last_duration = time.perf_counter() - start
    state.last_status = status
    return status
