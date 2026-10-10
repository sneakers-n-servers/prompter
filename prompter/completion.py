"""Tab completion driven entirely by what the backend knows."""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator, Iterable
from typing import Literal

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from prompter.backend import Backend
from prompter.shell import SHELL_BUILTINS

# Anything after one of these starts a new simple command.
_COMMAND_BOUNDARY_RE = re.compile(r"\|\||&&|\$\(|[|;&(`]")

Kind = Literal["command", "variable", "directory", "path"]


def _current_command(before_word: str) -> str | None:
    """Name of the command the cursor's word is an argument to, if any."""
    segment = _COMMAND_BOUNDARY_RE.split(before_word)[-1].split()
    return segment[0] if segment else None


class ShellCompleter(Completer):
    def __init__(self, backend: Backend) -> None:
        self._backend = backend

    def _classify(self, document: Document) -> tuple[Kind, str]:
        text = document.text_before_cursor
        word = document.get_word_before_cursor(WORD=True)
        before_word = text[: len(text) - len(word)]
        if word.startswith("$"):
            return "variable", word
        command = _current_command(before_word)
        if command is None and not any(sep in word for sep in "/\\"):
            return "command", word
        if command == "cd":
            return "directory", word
        return "path", word

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        # Synchronous fallback: paths need I/O and are only offered asynchronously.
        kind, word = self._classify(document)
        if kind == "command":
            yield from self._commands(word)
        elif kind == "variable":
            yield from self._environment(word)

    async def get_completions_async(
        self, document: Document, complete_event: CompleteEvent
    ) -> AsyncGenerator[Completion, None]:
        kind, word = self._classify(document)
        if kind in ("directory", "path"):
            entries = await self._backend.complete_path(word, kind == "directory")
            for entry in entries or ():
                yield Completion(
                    entry.text,
                    start_position=-len(word),
                    display_meta="dir" if entry.is_dir else None,
                )
        else:
            for completion in self.get_completions(document, complete_event):
                yield completion

    def _commands(self, prefix: str) -> Iterable[Completion]:
        known = self._backend.commands()
        names = SHELL_BUILTINS if known is None else SHELL_BUILTINS | known
        for name in sorted(names):
            if name.startswith(prefix):
                meta = "shell" if name in SHELL_BUILTINS else self._backend.describe(name)
                yield Completion(name, start_position=-len(prefix), display_meta=meta)

    def _environment(self, word: str) -> Iterable[Completion]:
        braced = word.startswith("${")
        prefix = word[2:] if braced else word[1:]
        for name in sorted(self._backend.env):
            if name.startswith(prefix):
                completion = "${" + name + "}" if braced else "$" + name
                yield Completion(
                    completion,
                    start_position=-len(word),
                    display=name,
                    display_meta="variable",
                )
