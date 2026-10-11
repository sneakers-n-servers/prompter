"""A pretty prompt_toolkit console: batman or pure prompt, F5 cycles colour styles.

To reuse: copy this file and ``themes.py``, subclass :class:`Backend` (only
``run`` is required) and call ``asyncio.run(Console(MyBackend()).run())``.
``local.py`` is a complete backend that drives the local ``/bin/sh``.
"""

from __future__ import annotations

import re
import time
from collections.abc import AsyncGenerator, Callable, Collection, Iterable, Mapping
from datetime import datetime
from pathlib import Path

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import FormattedText, StyleAndTextTuples
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import CompleteStyle

from prompter.themes import STYLES, build_style

Writer = Callable[[str], None]


class Backend:
    """What the console needs from whatever executes commands.

    Override ``run``; set the attributes if you can. Anything left at its
    default disables the corresponding bit of UI rather than guessing.
    """

    host = "?"
    sep = "/"  # path separator; "\\" on Windows
    cwd = ""  # shown in the prompt and toolbar
    home: str | None = None  # abbreviated to ^^ in the prompt
    env: Mapping[str, str] = {}  # offered for $NAME completion
    # Known command names; a dict's values are shown as descriptions in the menu.
    # Read on every redraw, so this must be a plain attribute, never a property doing I/O.
    commands: Collection[str] | None = None

    async def run(self, line: str, stdout: Writer, stderr: Writer) -> int:
        """Execute ``line``, streaming output to the writers; return the exit status."""
        raise NotImplementedError

    async def complete_path(self, prefix: str, only_dirs: bool) -> list[str]:
        """Completions for a path-like word; directories should end with ``sep``."""
        return []


# -- prompt layouts --------------------------------------------------------------


def tilde(path: str, home: str | None, sep: str) -> str:
    if home and (path == home or path.startswith(home.rstrip(sep) + sep)):
        return "~" + path[len(home.rstrip(sep)) :]
    return path


def short_path(path: str, home: str | None, sep: str) -> str:
    """fish's ``prompt_pwd``: ``/home/me/dev/prompter`` -> ``~/d/prompter``."""
    parts = tilde(path, home, sep).split(sep)
    if len(parts) > 2:
        parts[1:-1] = [p[: 2 if p.startswith(".") else 1] for p in parts[1:-1]]
    return sep.join(parts)


def styled_path(path: str, sep: str) -> StyleAndTextTuples:
    """``~`` becomes amber ``^^``, separators blue, basename amber."""
    out: StyleAndTextTuples = []
    parts = path.split(sep)
    for i, part in enumerate(parts):
        if i:
            out.append(("class:path.sep", sep))
        if part == "~":
            out.append(("class:path.home", "^^"))
        elif i == len(parts) - 1:
            out.append(("class:path.base", part))
        else:
            out.append(("", part))
    return out


def took(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{int(seconds) // 60}m{int(seconds) % 60:02d}s"


def batman_prompt(c: Console) -> StyleAndTextTuples:
    """oh-my-fish/theme-batman: ``^^/d/prompter>>> ``, arrows fade to red on failure."""
    b = c.backend
    path = styled_path(short_path(b.cwd, b.home, b.sep), b.sep) if b.cwd else []
    kind = "err" if c.status else "ok"
    return [*path, *[(f"class:arrow.{kind}.{i}", ">") for i in range(3)], ("", " ")]


def batman_rprompt(c: Console) -> StyleAndTextTuples:
    out: StyleAndTextTuples = []
    if c.status:
        out += [("class:dim", "("), ("class:trd", str(c.status)), ("class:dim", ") ")]
    hh, mm, ss = datetime.now().strftime("%H %M %S").split()
    out += [("class:dim", hh), ("class:fst", ":"), ("class:dim", mm), ("class:fst", ":")]
    return [*out, ("class:dim", ss)]


def human_time(seconds: float) -> str:
    """pure's format: ``3s``, ``1m 3s``, ``2h 5s`` (zero units are skipped)."""
    s = int(seconds)
    parts = [(s // 3600, "h"), (s // 60 % 60, "m"), (s % 60, "s")]
    return " ".join(f"{n}{unit}" for n, unit in parts if n or unit == "s")


def pure_prompt(c: Console) -> StyleAndTextTuples:
    """sindresorhus/pure: blank line; user@host (SSH only), path, time (>5s); then ``❯``."""
    b = c.backend
    out: StyleAndTextTuples = [("", "\n")]
    if b.env.get("SSH_CONNECTION"):
        out.append(("class:host", f"{b.env.get('USER', '')}@{b.host} "))
    out.append(("class:path", tilde(b.cwd, b.home, b.sep)))
    if c.took > 5:
        out.append(("class:took", f" {human_time(c.took)}"))
    return [*out, ("", "\n"), ("class:arrow.err" if c.status else "class:arrow.ok", "❯ ")]


def pure_rprompt(c: Console) -> StyleAndTextTuples:
    return [("class:status", f"✘ {c.status}")] if c.status else []


Layout = Callable[["Console"], StyleAndTextTuples]
PROMPTS: dict[str, tuple[Layout, Layout]] = {  # must match PROMPT_RULES in themes.py
    "batman": (batman_prompt, batman_rprompt),
    "pure": (pure_prompt, pure_rprompt),
}


# -- syntax highlighting --------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""(?P<comment>(?<!\S)\#.*$)
      | (?P<string>"(?:\\.|[^"\\])*"?|'[^']*'?)
      | (?P<operator>\|\||&&|\$\(|[|;&()`]|\d*(?:>>|>|<))
      | (?P<variable>\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|\$[?$!#@*0-9])
      | (?P<space>\s+)
      | (?P<word>[^\s|;&<>()"'`$]+)""",
    re.VERBOSE,
)


class ShellLexer(Lexer):
    """fish-style: known commands amber, unknown pink, nothing coloured while unknown."""

    def __init__(self, is_command: Callable[[str], bool | None]) -> None:
        self.is_command = is_command

    def lex_document(self, document: Document) -> Callable[[int], StyleAndTextTuples]:
        return lambda lineno: self.lex_line(document.lines[lineno])

    def lex_line(self, line: str) -> StyleAndTextTuples:
        tokens: StyleAndTextTuples = []
        expect_command = True
        for match in _TOKEN_RE.finditer(line):
            kind, text, style = match.lastgroup, match.group(), ""
            if kind == "word" and expect_command and "=" not in text:
                known = self.is_command(text)
                if known is not None:
                    style = f"class:lexer.command.{'valid' if known else 'invalid'}"
                expect_command = False
            elif kind == "word" and text.startswith("-"):
                style = "class:lexer.option"
            elif kind == "operator":
                style, expect_command = "class:lexer.operator", text != ")"
            elif kind not in ("word", "space"):
                style = f"class:lexer.{kind}"
                expect_command = expect_command and kind == "comment"
            tokens.append((style, text))
        return tokens


# -- completion -----------------------------------------------------------------

_BOUNDARY_RE = re.compile(r"\|\||&&|\$\(|[|;&(`]")  # what starts a new simple command


class ShellCompleter(Completer):
    def __init__(self, backend: Backend, extra_commands: Collection[str] = ()) -> None:
        self.backend = backend
        self.extra = extra_commands

    def get_completions(self, document: Document, event: CompleteEvent) -> Iterable[Completion]:
        return []  # everything goes through get_completions_async

    async def get_completions_async(
        self, document: Document, event: CompleteEvent
    ) -> AsyncGenerator[Completion, None]:
        text = document.text_before_cursor
        word = document.get_word_before_cursor(WORD=True)
        before = _BOUNDARY_RE.split(text[: len(text) - len(word)])[-1].split()
        start = -len(word)

        if word.startswith("$"):
            braced = word.startswith("${")
            for name in sorted(self.backend.env):
                if name.startswith(word[2 if braced else 1 :]):
                    yield Completion("${" + name + "}" if braced else "$" + name, start, name)
        elif not before and not any(c in word for c in "/\\"):
            commands = self.backend.commands or ()
            for name in sorted({*self.extra, *commands}):
                if name.startswith(word):
                    meta = commands.get(name) if isinstance(commands, Mapping) else None
                    yield Completion(name, start, display_meta=meta or None)
        else:
            for path in await self.backend.complete_path(word, only_dirs=before[0] == "cd"):
                yield Completion(path, start)


# -- the console ----------------------------------------------------------------


class Console:
    EXIT = frozenset({"exit", "quit"})
    HISTORY = Path.home() / ".prompter-history"

    def __init__(
        self,
        backend: Backend,
        prompt: str = "batman",
        style: str = "batman",
        history: Path | None = HISTORY,
    ):
        self.backend = backend
        self.prompt_name, self.style = prompt, style
        self.status = 0
        self.took = 0.0
        self.prompt, self.rprompt = PROMPTS[prompt]
        keys = KeyBindings()
        keys.add("f5")(self.next_style)
        self.session: PromptSession[str] = PromptSession(
            message=lambda: FormattedText(self.prompt(self)),
            rprompt=lambda: FormattedText(self.rprompt(self)),
            bottom_toolbar=self.toolbar,
            style=build_style(prompt, self.style),
            key_bindings=keys,
            lexer=ShellLexer(self.is_command),
            completer=ShellCompleter(backend, self.EXIT),
            complete_style=CompleteStyle.MULTI_COLUMN,
            complete_while_typing=False,
            history=FileHistory(history) if history else None,
            auto_suggest=AutoSuggestFromHistory(),
            refresh_interval=1.0,  # keeps the clock ticking
        )

    def next_style(self, event: KeyPressEvent | None = None) -> None:
        names = list(STYLES)
        self.style = names[(names.index(self.style) + 1) % len(names)]
        self.session.style = build_style(self.prompt_name, self.style)

    def is_command(self, name: str) -> bool | None:
        if name in self.EXIT:
            return True
        if self.backend.commands is None or any(c in name for c in "/\\"):
            return None
        return name in self.backend.commands

    def toolbar(self) -> FormattedText:
        sep = ("class:bottom-toolbar.sep", "  ·  ")
        out: StyleAndTextTuples = [("class:bottom-toolbar.key", f" {self.backend.host}")]
        if self.backend.cwd:
            out += [sep, ("", self.backend.cwd)]
        out += [sep, ("", f"took {took(self.took)}"), sep]
        out += [("class:bottom-toolbar.key", "F5"), ("", " next style  ")]
        return FormattedText([*out, ("class:bottom-toolbar.key", "^D"), ("", " quit ")])

    @staticmethod
    def stdout(text: str) -> None:
        print(text, end="", flush=True)

    def stderr(self, text: str) -> None:
        fragments = FormattedText([("class:stderr", text)])
        print_formatted_text(fragments, end="", style=self.session.style)

    async def execute(self, line: str) -> int:
        start = time.perf_counter()
        try:
            self.status = await self.backend.run(line, self.stdout, self.stderr)
        except Exception as exc:  # a misbehaving backend should not take the console down
            self.stderr(f"{type(exc).__name__}: {exc}\n")
            self.status = 1
        finally:
            self.took = time.perf_counter() - start
        return self.status

    async def run(self) -> None:
        with patch_stdout(raw=True):
            while True:
                try:
                    line = (await self.session.prompt_async()).strip()
                except KeyboardInterrupt:
                    continue
                except EOFError:
                    return
                words = line.split()
                if words and words[0] in self.EXIT:
                    return
                if words and not line.startswith("#"):
                    await self.execute(line)
