from __future__ import annotations

from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText

from prompter.theme import STYLE


def write_stdout(text: str) -> None:
    # Plain print so escape sequences emitted by children pass through untouched.
    print(text, end="", flush=True)


def write_stderr(text: str) -> None:
    print_formatted_text(FormattedText([("class:stderr", text)]), end="", flush=True, style=STYLE)


def error(message: str) -> None:
    write_stderr(f"prompter: {message}\n")
