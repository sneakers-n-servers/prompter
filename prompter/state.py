from __future__ import annotations

from dataclasses import dataclass

from prompter.backend import Backend


class ExitShell(Exception):
    """Raised to leave the read-eval loop."""


@dataclass
class ShellState:
    backend: Backend
    last_status: int = 0
    last_duration: float = 0.0
