from asyncio import run
from functools import partial
from pathlib import Path

from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import CompleteStyle, PromptSession

from prompter.backend import Backend
from prompter.completion import ShellCompleter
from prompter.local import LocalShell
from prompter.shell import execute
from prompter.state import ExitShell, ShellState
from prompter.theme import STYLE, ShellLexer, build_prompt, build_rprompt, build_toolbar


async def start_shell(backend: Backend) -> None:
    state = ShellState(backend)
    backend.refresh()
    session: PromptSession[str] = PromptSession(
        message=partial(build_prompt, state),
        rprompt=partial(build_rprompt, state),
        bottom_toolbar=partial(build_toolbar, state),
        style=STYLE,
        lexer=ShellLexer(backend.is_command),
        completer=ShellCompleter(backend),
        complete_style=CompleteStyle.MULTI_COLUMN,
        complete_while_typing=False,
        history=FileHistory(Path.home() / ".prompter-history"),
        auto_suggest=AutoSuggestFromHistory(),
        refresh_interval=1.0,
    )

    try:
        while True:
            try:
                line: str = (await session.prompt_async()).strip()
            except KeyboardInterrupt:
                continue
            except EOFError:
                return
            if not line or line.startswith("#"):
                continue
            try:
                await execute(state, line)
            except ExitShell:
                return
    finally:
        await backend.close()


async def _main() -> None:
    with patch_stdout(raw=True):
        await start_shell(LocalShell())
    print("Bye.")


def main() -> None:
    run(_main())


if __name__ == "__main__":
    main()
