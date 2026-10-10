import asyncio

from prompter.console import Console
from prompter.local import LocalShell
from tests.test_console import complete


def shell(tmp_path, **env) -> LocalShell:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in ("frob", "frobnicate"):
        (bindir / name).write_text("#!/bin/sh\n")
        (bindir / name).chmod(0o755)
    (bindir / "not-exec").write_text("")
    work = tmp_path / "work"
    (work / "sub").mkdir(parents=True)
    (work / "file.txt").write_text("")
    (work / ".hidden").write_text("")
    s = LocalShell(cwd=str(work), env={"PATH": str(bindir), "HOME": str(tmp_path), **env})
    s.scanner.join()
    return s


def test_commands_scanned_in_background(tmp_path):
    s = shell(tmp_path)
    assert s.commands == {"frob", "frobnicate", "cd", "export", "rehash"}
    assert complete(s, "fro") == [("frob", None), ("frobnicate", None)]


def test_path_completion(tmp_path):
    s = shell(tmp_path)
    assert complete(s, "cat ") == [("file.txt", None), ("sub/", None)]
    assert complete(s, "cd ") == [("sub/", None)]
    assert complete(s, "ls | wc f") == [("file.txt", None)]
    assert complete(s, "cat .") == [(".hidden", None)]
    assert complete(s, "cat ~/w") == [("~/work/", None)]
    assert complete(s, "cat nope/x") == []


def test_run_status_cd_and_env(tmp_path, capsys):
    s = shell(tmp_path)
    console = Console(s, history=None)
    run = lambda line: asyncio.run(console.execute(line))  # noqa: E731
    errors: list[str] = []
    console.stderr = errors.append  # type: ignore[method-assign]

    assert run("true") == 0
    assert run("false") == 1 and console.status == 1
    assert run("/bin/sh -c 'kill -TERM $$'") == 143
    assert run("cd sub") == 0 and s.cwd == str(tmp_path / "work" / "sub")
    assert run("export GREETING=hi") == 0
    assert run('echo "$GREETING" && pwd') == 0
    out = capsys.readouterr().out
    assert "hi\n" in out and s.cwd in out
    assert run("cd nowhere") == 1 and "no such directory" in errors[-1]
    assert run("cd -") == 0 and s.cwd == str(tmp_path / "work")
    assert run("cd") == 0 and s.cwd == str(tmp_path)
