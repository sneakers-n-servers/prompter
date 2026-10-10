import asyncio
import time

from prompter.local import CommandIndex, LocalShell


def _exe(path):
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)


def test_index_scans_in_background_and_tracks_mtime(tmp_path):
    (tmp_path / "a").mkdir()
    _exe(tmp_path / "a" / "one")
    index = CommandIndex()
    path = str(tmp_path / "a")

    assert index.names(path) == frozenset()  # never blocks the caller
    index.wait()
    assert index.ready and index.names(path) == {"one"}

    time.sleep(0.01)
    _exe(tmp_path / "a" / "two")
    index.refresh(path, force=True)
    index.wait()
    assert index.names(path) == {"one", "two"}

    # A directory dropped from PATH disappears from the index.
    (tmp_path / "b").mkdir()
    _exe(tmp_path / "b" / "three")
    index.refresh(str(tmp_path / "b"), force=True)
    index.wait()
    assert index.names(str(tmp_path / "b")) == {"three"}


def test_is_command_is_unknown_until_index_ready(tmp_path):
    shell = LocalShell(cwd=tmp_path, env={"PATH": str(tmp_path)})
    assert shell.is_command("cd") is True
    assert shell.is_command("whatever") is None
    shell.refresh()
    shell.wait_for_index()
    assert shell.is_command("whatever") is False
    _exe(tmp_path / "local-script")
    assert shell.is_command("./local-script") is True


def test_complete_path(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "file.txt").write_text("")
    (tmp_path / ".hidden").write_text("")
    shell = LocalShell(cwd=tmp_path, env={"HOME": str(tmp_path)})

    def complete(prefix, dirs=False):
        return [e.text for e in asyncio.run(shell.complete_path(prefix, dirs))]

    assert complete("") == ["file.txt", "sub/"]
    assert complete("", dirs=True) == ["sub/"]
    assert complete("f") == ["file.txt"]
    assert complete(".") == [".hidden"]
    assert complete("~/s") == ["~/sub/"]
    assert complete("sub/") == []
    assert complete("nope/x") == []
