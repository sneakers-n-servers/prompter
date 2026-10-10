"""``FakeBackend`` is the minimum a custom backend needs: a pretend Windows appliance."""

import pytest

from prompter.console import Backend, Writer


class FakeBackend(Backend):
    host = "appliance"
    sep = "\\"
    cwd = r"C:\Users\Mike\dev\prompter"
    home = r"C:\Users\Mike"

    def __init__(self) -> None:
        self.env = {"HOME": self.home, "HOSTNAME": self.host}
        self.commands = {"deploy": "push a release", "status": "health check", "show": ""}
        self.ran: list[str] = []
        self.status = 0

    async def run(self, line: str, stdout: Writer, stderr: Writer) -> int:
        self.ran.append(line)
        stdout(f"ran {line}\n")
        if self.status:
            stderr("failed\n")
        return self.status


@pytest.fixture
def fake() -> FakeBackend:
    return FakeBackend()
