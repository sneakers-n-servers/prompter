"""Shared fixtures. ``FakeBackend`` shows the minimum a custom backend needs."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from prompter.backend import Backend, PathEntry, Writer


class FakeBackend(Backend):
    """A pretend Windows appliance with a fixed command set and no filesystem access."""

    host = "appliance"
    windows = True

    def __init__(self) -> None:
        self.ran: list[str] = []
        self.status = 0
        self._cwd = r"C:\Users\Mike\dev\prompter"
        self._env: dict[str, str] = {"HOME": r"C:\Users\Mike"}

    @property
    def cwd(self) -> str:
        return self._cwd

    @property
    def home(self) -> str | None:
        return self._env.get("HOME")

    @property
    def env(self) -> Mapping[str, str]:
        return self._env

    async def run(self, line: str, stdout: Writer, stderr: Writer) -> int:
        self.ran.append(line)
        stdout(f"ran {line}\n")
        if self.status:
            stderr("failed\n")
        return self.status

    def commands(self) -> frozenset[str] | None:
        return frozenset({"deploy", "status", "show"})

    def describe(self, command: str) -> str | None:
        return {"deploy": "push a release", "status": "health check"}.get(command)

    async def complete_path(self, prefix: str, only_directories: bool) -> list[PathEntry] | None:
        return None


@pytest.fixture
def fake_backend() -> FakeBackend:
    return FakeBackend()
