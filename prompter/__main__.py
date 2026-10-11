import argparse
import asyncio

from prompter.console import PROMPTS, Console
from prompter.local import LocalShell
from prompter.themes import STYLES


def main() -> None:
    parser = argparse.ArgumentParser(prog="prompter")
    parser.add_argument("--prompt", choices=PROMPTS, default="batman", help="prompt layout")
    parser.add_argument("--style", choices=STYLES, default="batman", help="colours")
    args = parser.parse_args()
    asyncio.run(Console(LocalShell(), args.prompt, args.style).run())


if __name__ == "__main__":
    main()
