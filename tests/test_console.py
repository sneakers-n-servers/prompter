import asyncio

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from prompter.console import Console, ShellCompleter, ShellLexer, short_path, took


def text(fragments) -> str:
    return "".join(t for _, t in fragments)


def complete(backend, line: str) -> list[tuple[str, str | None]]:
    async def collect():
        doc = Document(line, len(line))
        gen = ShellCompleter(backend, Console.EXIT).get_completions_async(doc, CompleteEvent())
        return [(c.text, c.display_meta_text or None) async for c in gen]

    return asyncio.run(collect())


def test_short_path():
    assert short_path("/home/me", "/home/me", "/") == "~"
    assert short_path("/home/me/dev", "/home/me", "/") == "~/dev"
    assert short_path("/home/me/.config/nvim/lua", "/home/me", "/") == "~/.c/n/lua"
    assert short_path("/", "/home/me", "/") == "/"
    assert short_path("/usr/local/bin", None, "/") == "/u/l/bin"
    assert short_path(r"C:\Users\Mike\dev\x", r"C:\Users\Mike", "\\") == r"~\d\x"
    assert short_path("C:\\", r"C:\Users\Mike", "\\") == "C:\\"


def test_took():
    assert (took(0.0123), took(2.34), took(125)) == ("12ms", "2.3s", "2m05s")


def test_prompt_rprompt_toolbar(fake):
    console = Console(fake, history=None)
    fragments = list(console.prompt())
    assert text(fragments) == "^^\\d\\prompter>>> "
    assert ("class:path.home", "^^") in fragments
    assert ("class:path.base", "prompter") in fragments
    assert [s for s, t in fragments if t == ">"] == [f"class:arrow.ok.{i}" for i in range(3)]
    assert len(text(console.rprompt())) == 8  # HH:MM:SS

    console.status = 127
    assert all(s.startswith("class:arrow.err") for s, t in console.prompt() if t == ">")
    assert text(console.rprompt()).startswith("(127) ")
    assert text(console.toolbar()).startswith(
        " appliance  ·  C:\\Users\\Mike\\dev\\prompter  ·  took "
    )


def test_execute_records_status_and_streams_output(fake, capsys, monkeypatch):
    errors: list[str] = []
    monkeypatch.setattr(Console, "stderr", staticmethod(errors.append))
    console = Console(fake, history=None)
    assert asyncio.run(console.execute("deploy now")) == 0
    fake.status = 4
    assert asyncio.run(console.execute("status")) == 4
    assert console.status == 4 and fake.ran == ["deploy now", "status"]
    assert "ran deploy now" in capsys.readouterr().out and errors == ["failed\n"]


def test_lexer_colours_commands_only_when_known():
    known = {"ls": True, "nope": False}
    tokens = ShellLexer(lambda n: known.get(n)).lex_line(
        "ls -la | nope 'x y' $HOME && FOO=1 odd # hi"
    )
    assert ("class:lexer.command.valid", "ls") in tokens
    assert ("class:lexer.option", "-la") in tokens
    assert ("class:lexer.operator", "|") in tokens
    assert ("class:lexer.command.invalid", "nope") in tokens
    assert ("class:lexer.string", "'x y'") in tokens
    assert ("class:lexer.variable", "$HOME") in tokens
    assert ("", "FOO=1") in tokens and ("", "odd") in tokens  # unknown -> uncoloured
    assert ("class:lexer.comment", "# hi") in tokens


def test_is_command_is_unknown_without_a_command_set(fake):
    console = Console(fake, history=None)
    assert console.is_command("deploy") is True
    assert console.is_command("exit") is True
    assert console.is_command("bogus") is False
    fake.commands = None
    assert console.is_command("bogus") is None


def test_completion_from_custom_backend(fake):
    assert complete(fake, "") == [
        ("deploy", "push a release"),
        ("exit", None),
        ("quit", None),
        ("show", None),
        ("status", "health check"),
    ]
    assert complete(fake, "deploy ") == []  # no filesystem on this backend
    assert complete(fake, "echo $HO") == [("$HOME", None), ("$HOSTNAME", None)]
    assert complete(fake, "echo ${HO") == [("${HOME}", None), ("${HOSTNAME}", None)]
