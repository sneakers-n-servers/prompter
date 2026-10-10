import asyncio

from prompt_toolkit.completion import CompleteEvent, Completion
from prompt_toolkit.document import Document

from prompter.completion import ShellCompleter, _current_command
from prompter.local import LocalShell


async def _collect(completer: ShellCompleter, text: str) -> list[Completion]:
    doc = Document(text, len(text))
    return [c async for c in completer.get_completions_async(doc, CompleteEvent())]


def _complete(backend, text: str) -> list[str]:
    completions = asyncio.run(_collect(ShellCompleter(backend), text))
    # Report the last word as it would read after accepting each completion.
    return [(text[: len(text) + c.start_position] + c.text).split()[-1] for c in completions]


def _local(tmp_path) -> LocalShell:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in ("frobnicate", "frob", "other"):
        exe = bindir / name
        exe.write_text("#!/bin/sh\n")
        exe.chmod(0o755)
    (bindir / "not-exec").write_text("")
    workdir = tmp_path / "work"
    (workdir / "sub").mkdir(parents=True)
    (workdir / "file.txt").write_text("")
    env = {"PATH": str(bindir), "HOME": str(tmp_path), "HOMEBREW": "x", "SHELL": "sh"}
    shell = LocalShell(cwd=workdir, env=env)
    shell.refresh()
    shell.wait_for_index()
    return shell


def test_current_command():
    assert _current_command("") is None
    assert _current_command("ls -l ") == "ls"
    assert _current_command("ls | grep ") == "grep"
    assert _current_command("a && b; ") is None
    assert _current_command("echo $(cat ") == "cat"


def test_completes_commands_from_path(tmp_path):
    shell = _local(tmp_path)
    assert _complete(shell, "fro") == ["frob", "frobnicate"]
    assert "not-exec" not in _complete(shell, "not")


def test_completes_builtins(tmp_path):
    shell = _local(tmp_path)
    assert _complete(shell, "ex") == ["exit", "export"]
    assert _complete(shell, "reh") == ["rehash"]


def test_completes_paths_for_arguments(tmp_path):
    shell = _local(tmp_path)
    assert _complete(shell, "cat ") == ["file.txt", "sub/"]
    assert _complete(shell, "cd ") == ["sub/"]
    assert _complete(shell, "ls | wc f") == ["file.txt"]


def test_completes_environment_variables(tmp_path):
    shell = _local(tmp_path)
    assert _complete(shell, "echo $HO") == ["$HOME", "$HOMEBREW"]
    assert _complete(shell, "echo ${HO") == ["${HOME}", "${HOMEBREW}"]


def test_custom_backend_drives_completion(fake_backend):
    assert _complete(fake_backend, "") == ["deploy", "exit", "quit", "show", "status"]
    completions = asyncio.run(_collect(ShellCompleter(fake_backend), "dep"))
    assert completions[0].display_meta_text == "push a release"
    # No filesystem on this backend: nothing is offered for arguments.
    assert _complete(fake_backend, "deploy ") == []
    assert _complete(fake_backend, "echo $H") == ["$HOME"]
