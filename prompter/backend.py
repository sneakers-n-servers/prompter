"""The contract between the prompt and whatever actually executes commands.

Only :meth:`Backend.run` is required. Every other hook has a conservative
default meaning "I don't know", so the UI degrades to a plain prompt instead
of guessing from the local machine when the backend is remote or exotic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import NamedTuple

Writer = Callable[[str], None]


class PathEntry(NamedTuple):
    """One path completion. ``text`` replaces the whole word being completed."""

    text: str
    is_dir: bool


class Backend(ABC):
    host: str = "?"
    windows: bool = False

    @property
    def cwd(self) -> str:
        """Working directory as the backend would print it; shown in the prompt."""
        return ""

    @property
    def home(self) -> str | None:
        """Directory to abbreviate as ``^^`` in the prompt, if any."""
        return None

    @property
    def env(self) -> Mapping[str, str]:
        """Variables offered for ``$NAME`` completion."""
        return {}

    @abstractmethod
    async def run(self, line: str, stdout: Writer, stderr: Writer) -> int:
        """Execute ``line``, streaming output to the writers; return the exit status."""

    def commands(self) -> frozenset[str] | None:
        """Non-blocking snapshot of known command names, or ``None`` if unknown.

        Called on every redraw, so this must never do I/O. Use :meth:`refresh`
        to (re)build the set in the background.
        """
        return None

    def is_command(self, name: str) -> bool | None:
        names = self.commands()
        return None if names is None else name in names

    def describe(self, command: str) -> str | None:
        """Short description shown next to ``command`` in the completion menu."""
        return None

    async def complete_path(self, prefix: str, only_directories: bool) -> list[PathEntry] | None:
        """Path completions for ``prefix`` (``None`` if the backend has no notion of paths)."""
        return None

    def refresh(self) -> None:  # noqa: B027 - optional hook
        """Hint that cached information (such as :meth:`commands`) should be rebuilt."""

    async def close(self) -> None:  # noqa: B027 - optional hook
        """Release any resources when the shell exits."""
