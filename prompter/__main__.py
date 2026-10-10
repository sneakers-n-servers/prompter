import asyncio

from prompter.console import Console
from prompter.local import LocalShell


def main() -> None:
    asyncio.run(Console(LocalShell()).run())


if __name__ == "__main__":
    main()
