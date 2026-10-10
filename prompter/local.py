"""Reference backend: run commands through the local ``/bin/sh``."""

from __future__ import annotations

import asyncio
import os
import shlex
import signal
import socket
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from time import monotonic

from prompter.backend import Backend, PathEntry, Writer

_CHUNK = 4096


def _scan_directory(directory: str) -> frozenset[str]:
    names: set[str] = set()
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_file() and os.access(entry.path, os.X_OK):
                    names.add(entry.name)
    except OSError:
        pass
    return frozenset(names)


class CommandIndex:
    """Executables on ``$PATH``, maintained by a background thread.

    Scanning must never happen on the render path: on WSL a single Windows
    directory under ``/mnt/c`` takes well over a second to list. Directories
    are rescanned only when their mtime changes, and results are published
    incrementally so fast local directories show up immediately.
    """

    REFRESH_INTERVAL = 5.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._dirs: dict[str, tuple[float, frozenset[str]]] = {}
        self._names: frozenset[str] = frozenset()
        self._path: str | None = None
        self._refreshed_at = -self.REFRESH_INTERVAL
        self._thread: threading.Thread | None = None
        self.ready = False

    def names(self, path: str) -> frozenset[str]:
        """Current snapshot; may be incomplete until :attr:`ready` is set."""
        self.refresh(path)
        return self._names

    def refresh(self, path: str, force: bool = False) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            fresh = path == self._path and monotonic() - self._refreshed_at < self.REFRESH_INTERVAL
            if fresh and not force:
                return
            self._thread = threading.Thread(
                target=self._refresh, args=(path, force), daemon=True, name="prompter-path"
            )
            self._thread.start()

    def wait(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def _refresh(self, path: str, force: bool) -> None:
        directories = [d or "." for d in path.split(os.pathsep)]
        for directory in directories:
            try:
                mtime = os.stat(directory).st_mtime
            except OSError:
                self._dirs.pop(directory, None)
                continue
            cached = self._dirs.get(directory)
            if cached is not None and cached[0] == mtime and not force:
                continue
            self._dirs[directory] = (mtime, _scan_directory(directory))
            self._publish(directories)
        for stale in set(self._dirs) - set(directories):
            del self._dirs[stale]
        self._publish(directories)
        with self._lock:
            self._path = path
            self._refreshed_at = monotonic()
            self.ready = True

    def _publish(self, directories: list[str]) -> None:
        names: set[str] = set()
        for directory in directories:
            if (cached := self._dirs.get(directory)) is not None:
                names |= cached[1]
        self._names = frozenset(names)


Builtin = Callable[["LocalShell", list[str]], int]


class LocalShell(Backend):
    """Each line runs in a fresh ``/bin/sh``; cwd and environment persist here.

    Things that cannot be subprocesses (``cd``, ``export``...) are builtins.
    """

    host = socket.gethostname().split(".")[0]
    windows = False

    def __init__(
        self,
        cwd: str | os.PathLike[str] | None = None,
        env: Mapping[str, str] | None = None,
        stderr: Writer | None = None,
    ) -> None:
        self._cwd = Path(cwd) if cwd is not None else Path.cwd()
        self._env = dict(os.environ if env is None else env)
        self._error = stderr or (lambda text: None)
        self._index = CommandIndex()
        self._builtins: dict[str, Builtin] = {
            "cd": LocalShell._cd,
            "export": LocalShell._export,
            "unset": LocalShell._unset,
            "rehash": LocalShell._rehash,
        }

    @property
    def cwd(self) -> str:
        return str(self._cwd)

    @property
    def home(self) -> str | None:
        return self._env.get("HOME") or str(Path.home())

    @property
    def env(self) -> Mapping[str, str]:
        return self._env

    @property
    def path(self) -> str:
        return self._env.get("PATH", os.defpath)

    # -- commands -----------------------------------------------------------

    def commands(self) -> frozenset[str] | None:
        return self._index.names(self.path) | frozenset(self._builtins)

    def is_command(self, name: str) -> bool | None:
        if name in self._builtins or name in self._index.names(self.path):
            return True
        if "/" in name:
            candidate = self._cwd / self._expanduser(name)
            return candidate.is_file() and os.access(candidate, os.X_OK)
        return False if self._index.ready else None

    def describe(self, command: str) -> str | None:
        return "builtin" if command in self._builtins else None

    def refresh(self) -> None:
        self._index.refresh(self.path)

    def wait_for_index(self, timeout: float | None = None) -> None:
        self._index.wait(timeout)

    # -- paths --------------------------------------------------------------

    async def complete_path(self, prefix: str, only_directories: bool) -> list[PathEntry]:
        return await asyncio.to_thread(self._complete_path, prefix, only_directories)

    def _expanduser(self, path: str) -> str:
        if path == "~" or path.startswith("~/"):
            return (self.home or "~") + path[1:]
        return path

    def _complete_path(self, prefix: str, only_directories: bool) -> list[PathEntry]:
        directory, partial = os.path.split(self._expanduser(prefix))
        head = prefix[: len(prefix) - len(partial)]
        try:
            with os.scandir(self._cwd / directory if directory else self._cwd) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            return []
        results: list[PathEntry] = []
        for entry in entries:
            if not entry.name.startswith(partial):
                continue
            if not partial and entry.name.startswith("."):
                continue
            is_dir = entry.is_dir()
            if only_directories and not is_dir:
                continue
            results.append(PathEntry(head + entry.name + ("/" if is_dir else ""), is_dir))
        return results

    # -- execution ----------------------------------------------------------

    async def run(self, line: str, stdout: Writer, stderr: Writer) -> int:
        try:
            words = shlex.split(line)
        except ValueError:
            words = line.split()
        if words and words[0] in self._builtins:
            self._error = stderr
            return self._builtins[words[0]](self, words[1:])
        return await self._run_in_sh(line, stdout, stderr)

    async def _run_in_sh(self, line: str, stdout: Writer, stderr: Writer) -> int:
        proc = await asyncio.create_subprocess_shell(
            line,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._cwd,
            env=self._env,
            executable="/bin/sh",
        )
        # The terminal delivers Ctrl-C to the whole foreground process group, so
        # the child already receives it; we only stop it from killing the shell.
        previous = signal.signal(signal.SIGINT, lambda *_: None)
        try:
            await asyncio.gather(
                _pump(proc.stdout, stdout),
                _pump(proc.stderr, stderr),
                proc.wait(),
            )
        finally:
            signal.signal(signal.SIGINT, previous)

        returncode = proc.returncode or 0
        return 128 - returncode if returncode < 0 else returncode

    # -- builtins -----------------------------------------------------------

    def _cd(self, args: list[str]) -> int:
        if len(args) > 1:
            self._error("cd: too many arguments\n")
            return 1
        target = args[0] if args else "~"
        if target == "-":
            target = self._env.get("OLDPWD", str(self._cwd))
        destination = (self._cwd / self._expanduser(target)).resolve()
        if not destination.is_dir():
            self._error(f"cd: no such directory: {target}\n")
            return 1
        self._env["OLDPWD"] = str(self._cwd)
        self._cwd = destination
        self._env["PWD"] = str(destination)
        return 0

    def _export(self, args: list[str]) -> int:
        if not args:
            for key, value in sorted(self._env.items()):
                print(f"{key}={value}")
            return 0
        for arg in args:
            key, sep, value = arg.partition("=")
            if sep:
                self._env[key] = value
            elif key not in self._env:
                self._error(f"export: {key} is not set\n")
                return 1
        return 0

    def _unset(self, args: list[str]) -> int:
        for key in args:
            self._env.pop(key, None)
        return 0

    def _rehash(self, args: list[str]) -> int:
        self._index.refresh(self.path, force=True)
        return 0


async def _pump(stream: asyncio.StreamReader | None, write: Writer) -> None:
    if stream is None:
        return
    while chunk := await stream.read(_CHUNK):
        write(chunk.decode(errors="replace"))
