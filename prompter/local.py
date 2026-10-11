"""Reference backend: each line runs in a fresh local ``/bin/sh``.

``cd`` and ``export`` are builtins because they must outlive the subprocess.
``$PATH`` is scanned once in a background thread; ``rehash`` rescans.
"""

from __future__ import annotations

import asyncio
import codecs
import os
import shlex
import signal
import socket
import threading
from collections.abc import Callable, Mapping
from pathlib import Path

from prompter.console import Backend, Writer

Builtin = Callable[[list[str], Writer], int]


class LocalShell(Backend):
    host = socket.gethostname().split(".")[0]
    home: str
    env: dict[str, str]

    def __init__(self, cwd: str | None = None, env: Mapping[str, str] | None = None) -> None:
        self.cwd = cwd or os.getcwd()
        self.env = dict(os.environ if env is None else env)
        self.home = self.env.get("HOME") or str(Path.home())
        self.builtins: dict[str, Builtin] = {
            "cd": self.cd,
            "export": self.export,
            "rehash": self.rehash,
        }
        self.rehash()

    # -- commands -------------------------------------------------------------

    def rehash(self, *_: object) -> int:
        self.scanner = threading.Thread(target=self._scan_path, daemon=True)
        self.scanner.start()
        return 0

    def _scan_path(self) -> None:
        names = set(self.builtins)
        for directory in self.env.get("PATH", os.defpath).split(os.pathsep):
            try:
                with os.scandir(directory or ".") as entries:
                    names |= {e.name for e in entries if os.access(e.path, os.X_OK) and e.is_file()}
            except OSError:
                continue
            self.commands = frozenset(names)  # publish incrementally; slow dirs (WSL) come last
        self.commands = frozenset(names)

    # -- paths ----------------------------------------------------------------

    def expand(self, path: str) -> str:
        return self.home + path[1:] if path == "~" or path.startswith("~/") else path

    async def complete_path(self, prefix: str, only_dirs: bool) -> list[str]:
        return await asyncio.to_thread(self._complete_path, prefix, only_dirs)

    def _complete_path(self, prefix: str, only_dirs: bool) -> list[str]:
        head, partial = os.path.split(self.expand(prefix))
        try:
            with os.scandir(os.path.join(self.cwd, head)) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            return []
        typed = prefix[: len(prefix) - len(partial)]
        return [
            typed + e.name + ("/" if e.is_dir() else "")
            for e in entries
            if e.name.startswith(partial)
            and (partial or not e.name.startswith("."))
            and (e.is_dir() or not only_dirs)
        ]

    # -- execution ------------------------------------------------------------

    async def run(self, line: str, stdout: Writer, stderr: Writer) -> int:
        try:
            words = shlex.split(line)
        except ValueError:
            words = line.split()
        if words and words[0] in self.builtins:
            return self.builtins[words[0]](words[1:], stderr)

        proc = await asyncio.create_subprocess_shell(
            line, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd, env=self.env, executable="/bin/sh",
        )  # fmt: skip
        # Ctrl-C reaches the child via the foreground process group; just don't let it kill us.
        previous = signal.signal(signal.SIGINT, lambda *_: None)
        try:
            await asyncio.gather(
                _pump(proc.stdout, stdout), _pump(proc.stderr, stderr), proc.wait()
            )
        finally:
            signal.signal(signal.SIGINT, previous)
        code = proc.returncode or 0
        return 128 - code if code < 0 else code

    # -- builtins -------------------------------------------------------------

    def cd(self, args: list[str], stderr: Writer) -> int:
        target = (
            self.env.get("OLDPWD", self.cwd)
            if args == ["-"]
            else self.expand(args[0] if args else "~")
        )
        destination = os.path.realpath(os.path.join(self.cwd, target))
        if not os.path.isdir(destination):
            stderr(f"cd: no such directory: {target}\n")
            return 1
        self.env["OLDPWD"], self.cwd, self.env["PWD"] = self.cwd, destination, destination
        return 0

    def export(self, args: list[str], stderr: Writer) -> int:
        for arg in args:
            key, has_value, value = arg.partition("=")
            if has_value:
                self.env[key] = value
        return 0


async def _pump(stream: asyncio.StreamReader | None, write: Writer) -> None:
    decode = codecs.getincrementaldecoder("utf-8")(errors="replace").decode
    while stream and (chunk := await stream.read(4096)):
        write(decode(chunk))
    write(decode(b"", final=True))
