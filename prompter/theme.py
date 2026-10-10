"""Look and feel: colours, the prompt itself, and syntax highlighting."""

from __future__ import annotations

import contextlib
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath

from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import FormattedText, StyleAndTextTuples
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.styles import Style

from prompter.state import ShellState

# Port of oh-my-fish/theme-batman (MIT, Jorge Bucaran et al.), minus the git bits.
FST = "#ffaa00"  # amber
SND = "#3366ff"  # blue
TRD = "#ff0066"  # pink
DIM = "#666666"
ARROWS_OK = ("#333333", "#666666", "#aaaaaa")
ARROWS_ERR = ("#660000", "#990000", "#cc0000")

STYLE = Style.from_dict(
    {
        "path.home": f"{FST} bold",
        "path.sep": f"{SND} bold",
        "path.base": f"{FST} bold",
        **{f"arrow.ok.{i}": f"{c} bold" for i, c in enumerate(ARROWS_OK)},
        **{f"arrow.err.{i}": f"{c} bold" for i, c in enumerate(ARROWS_ERR)},
        "rprompt.dim": DIM,
        "rprompt.fst": f"{FST} bold",
        "rprompt.trd": f"{TRD} bold",
        "stderr": "#cc0000",
        "auto-suggestion": DIM,
        "bottom-toolbar": f"bg:#1c1c1c {DIM} noreverse",
        "bottom-toolbar.key": f"bg:#1c1c1c {FST} bold",
        "bottom-toolbar.host": f"bg:#1c1c1c {FST} bold",
        "bottom-toolbar.sep": f"bg:#1c1c1c {SND}",
        "completion-menu": "bg:#1c1c1c #aaaaaa",
        "completion-menu.completion.current": f"bg:{FST} #000000 bold",
        "completion-menu.meta.completion": f"bg:#262626 {DIM}",
        "completion-menu.meta.completion.current": f"bg:{FST} #333333",
        "scrollbar.background": "bg:#262626",
        "scrollbar.button": f"bg:{DIM}",
        "lexer.command.valid": f"{FST} bold",
        "lexer.command.invalid": f"{TRD} bold",
        "lexer.assignment": SND,
        "lexer.option": SND,
        "lexer.string": "#aaaaaa",
        "lexer.operator": f"{TRD} bold",
        "lexer.variable": f"{SND} bold",
        "lexer.comment": f"{DIM} italic",
    }
)


def abbreviate_path(path: str, home: str | None = None, windows: bool = False) -> str:
    """fish's ``prompt_pwd`` for either OS: ``~/d/prompter``, ``C:\\U\\M\\dev``."""
    flavour = PureWindowsPath if windows else PurePosixPath
    sep = "\\" if windows else "/"
    pure = flavour(path)
    parts = list(pure.parts)
    if home:
        with contextlib.suppress(ValueError):
            parts = ["~", *pure.relative_to(flavour(home)).parts]
    if not parts:
        return path
    anchor, rest = parts[0], parts[1:]
    if anchor == pure.anchor:
        anchor = anchor.rstrip("\\/")  # "" for a POSIX root, "C:" for a drive
    if not rest:
        return anchor if anchor == "~" else anchor + sep
    head = [p[:1] if not p.startswith(".") else p[:2] for p in rest[:-1]]
    return sep.join([anchor, *head, rest[-1]])


def format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m{secs:02d}s"


def _styled_path(pwd: str, sep: str) -> StyleAndTextTuples:
    """``~`` becomes amber ``^^``, separators blue, basename amber."""
    out: StyleAndTextTuples = []
    components = pwd.split(sep)
    for i, component in enumerate(components):
        if i:
            out.append(("class:path.sep", sep))
        if component == "~":
            out.append(("class:path.home", "^^"))
        elif i == len(components) - 1:
            out.append(("class:path.base", component))
        elif component:
            out.append(("", component))
    return out


def build_prompt(state: ShellState) -> FormattedText:
    backend = state.backend
    pwd = abbreviate_path(backend.cwd, backend.home, backend.windows)
    kind = "err" if state.last_status else "ok"
    arrows: StyleAndTextTuples = [(f"class:arrow.{kind}.{i}", ">") for i in range(3)]
    return FormattedText([*_styled_path(pwd, "\\" if backend.windows else "/"), *arrows, ("", " ")])


def build_rprompt(state: ShellState) -> FormattedText:
    out: StyleAndTextTuples = []
    if state.last_status:
        out += [
            ("class:rprompt.dim", "("),
            ("class:rprompt.trd", str(state.last_status)),
            ("class:rprompt.dim", ") "),
        ]
    if state.backend.env.get("SSH_CONNECTION"):
        out += [("class:rprompt.trd", ":"), ("class:rprompt.dim", f"{state.backend.host} ")]
    hh, mm, ss = datetime.now().strftime("%H %M %S").split()
    out += [
        ("class:rprompt.dim", hh),
        ("class:rprompt.fst", ":"),
        ("class:rprompt.dim", mm),
        ("class:rprompt.fst", ":"),
        ("class:rprompt.dim", ss),
    ]
    return FormattedText(out)


def build_toolbar(state: ShellState) -> FormattedText:
    sep = ("class:bottom-toolbar.sep", "  ·  ")
    fragments: StyleAndTextTuples = [("class:bottom-toolbar.host", f" {state.backend.host}")]
    if state.backend.cwd:
        fragments += [sep, ("", state.backend.cwd)]
    fragments += [
        sep,
        ("", f"took {format_duration(state.last_duration)}"),
        sep,
        ("class:bottom-toolbar.key", "Tab"),
        ("", " complete  "),
        ("class:bottom-toolbar.key", "^D"),
        ("", " quit "),
    ]
    return FormattedText(fragments)


_TOKEN_RE = re.compile(
    r"""
    (?P<comment>(?<!\S)\#.*$)
  | (?P<string>"(?:\\.|[^"\\])*"?|'[^']*'?)
  | (?P<operator>\|\||&&|\$\(|[|;&()`]|\d*(?:>>|>|<))
  | (?P<variable>\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|\$[?$!#@*0-9])
  | (?P<space>\s+)
  | (?P<word>[^\s|;&<>()"'`$]+)
    """,
    re.VERBOSE,
)

_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


class ShellLexer(Lexer):
    """fish-style highlighting: known commands green, unknown ones red."""

    def __init__(self, is_command: Callable[[str], bool | None]) -> None:
        self._is_command = is_command

    def lex_document(self, document: Document) -> Callable[[int], StyleAndTextTuples]:
        lines = document.lines

        def get_line(lineno: int) -> StyleAndTextTuples:
            return self._lex_line(lines[lineno])

        return get_line

    def _lex_line(self, line: str) -> StyleAndTextTuples:
        tokens: StyleAndTextTuples = []
        expect_command = True
        for match in _TOKEN_RE.finditer(line):
            kind = match.lastgroup or "word"
            text = match.group()
            style = ""
            if kind == "word":
                if expect_command and _ASSIGNMENT_RE.match(text):
                    style = "class:lexer.assignment"
                elif expect_command:
                    known = self._is_command(text)
                    if known is not None:
                        style = f"class:lexer.command.{'valid' if known else 'invalid'}"
                    expect_command = False
                elif text.startswith("-"):
                    style = "class:lexer.option"
            elif kind == "operator":
                style = "class:lexer.operator"
                expect_command = text != ")"
            elif kind == "space":
                pass
            else:
                style = f"class:lexer.{kind}"
                if kind in ("string", "variable") and expect_command:
                    expect_command = False
            tokens.append((style, text))
        return tokens
