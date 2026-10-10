import asyncio

import pytest

from prompter.local import LocalShell
from prompter.shell import execute
from prompter.state import ExitShell, ShellState


def run(state: ShellState, line: str) -> int:
    return asyncio.run(execute(state, line))


@pytest.fixture
def stderr(monkeypatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr("prompter.shell.write_stderr", captured.append)
    return captured


def test_exit_status_is_recorded(tmp_path):
    state = ShellState(LocalShell(cwd=tmp_path))
    assert run(state, "true") == 0
    assert run(state, "false") == 1
    assert state.last_status == 1
    assert run(state, "sh -c 'kill -TERM $$'") == 143


def test_cd_and_env_flow_to_children(tmp_path, capsys, stderr):
    shell = LocalShell(cwd=tmp_path)
    state = ShellState(shell)
    (tmp_path / "inner").mkdir()
    assert run(state, "cd inner") == 0
    assert shell.cwd == str((tmp_path / "inner").resolve())
    assert run(state, "export GREETING=hi") == 0
    assert run(state, 'echo "$GREETING" && pwd') == 0
    out = capsys.readouterr().out
    assert "hi" in out and shell.cwd in out
    assert run(state, "cd nowhere") == 1
    assert "no such directory" in "".join(stderr)
    assert run(state, "cd -") == 0
    assert shell.cwd == str(tmp_path.resolve())


def test_exit_is_shell_level_for_any_backend(tmp_path, fake_backend):
    with pytest.raises(ExitShell):
        run(ShellState(LocalShell(cwd=tmp_path)), "exit")
    with pytest.raises(ExitShell):
        run(ShellState(fake_backend), "quit")
    assert fake_backend.ran == []


def test_custom_backend_output_and_status(fake_backend, capsys, stderr):
    state = ShellState(fake_backend)
    assert run(state, "deploy now") == 0
    fake_backend.status = 4
    assert run(state, "status") == 4
    assert state.last_status == 4
    assert fake_backend.ran == ["deploy now", "status"]
    assert "ran deploy now" in capsys.readouterr().out
    assert stderr == ["failed\n"]
