import asyncio

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from prompter.console import (
    PROMPTS,
    Console,
    ShellCompleter,
    ShellLexer,
    human_time,
    short_path,
    took,
)
from prompter.themes import PROMPT_RULES, STYLES, build_style


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


def test_batman_prompt_rprompt_toolbar(fake):
    console = Console(fake, history=None)
    fragments = console.prompt(console)
    assert text(fragments) == "^^\\d\\prompter>>> "
    assert ("class:path.home", "^^") in fragments
    assert ("class:path.base", "prompter") in fragments
    assert [s for s, t in fragments if t == ">"] == [f"class:arrow.ok.{i}" for i in range(3)]
    assert len(text(console.rprompt(console))) == 8  # HH:MM:SS

    console.status = 127
    assert all(s.startswith("class:arrow.err") for s, t in console.prompt(console) if t == ">")
    assert text(console.rprompt(console)).startswith("(127) ")
    toolbar = text(console.toolbar())
    assert toolbar.startswith(" appliance  ·  C:\\Users\\Mike\\dev\\prompter  ·  took ")
    assert "F5 next style" in toolbar and "batman" not in toolbar


def test_pure_prompt(fake):
    console = Console(fake, prompt="pure", history=None)
    fragments = console.prompt(console)
    assert text(fragments) == "\n~\\dev\\prompter\n❯ "
    assert ("class:path", "~\\dev\\prompter") in fragments
    assert ("class:arrow.ok", "❯ ") in fragments
    assert console.rprompt(console) == []

    console.status, console.took = 1, 67.5
    fake.env["SSH_CONNECTION"] = "x"
    fake.env["USER"] = "mike"
    fragments = console.prompt(console)
    assert text(fragments) == "\nmike@appliance ~\\dev\\prompter 1m 7s\n❯ "
    assert ("class:arrow.err", "❯ ") in fragments
    assert ("class:took", " 1m 7s") in fragments
    assert console.rprompt(console) == [("class:status", "✘ 1")]
    assert "exit" not in text(console.toolbar())


def test_human_time():
    assert (human_time(3), human_time(67), human_time(7205)) == ("3s", "1m 7s", "2h 5s")


def test_f5_cycles_styles(fake):
    console = Console(fake, history=None)
    seen = []
    for _ in STYLES:
        seen.append(console.style)
        before = console.session.style
        console.next_style()
        assert console.session.style is not before
    assert seen == list(STYLES) and console.style == "batman"


def test_prompts_match_prompt_rules():
    assert PROMPTS.keys() == PROMPT_RULES.keys()


def test_backend_exception_does_not_kill_console(fake, monkeypatch):
    errors: list[str] = []
    monkeypatch.setattr(Console, "stderr", lambda self, text: errors.append(text))

    async def boom(line, stdout, stderr):
        raise RuntimeError("backend is down")

    fake.run = boom
    console = Console(fake, history=None)
    assert asyncio.run(console.execute("deploy")) == 1
    assert errors == ["RuntimeError: backend is down\n"]


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("prompt", PROMPTS)
def test_every_prompt_and_style_builds(prompt, style):
    rules = build_style(prompt, style).style_rules
    classes = {name for name, _ in rules}
    assert set(PROMPT_RULES[prompt]) <= classes
    assert {"lexer.command.valid", "lexer.command.invalid", "bottom-toolbar.key"} <= classes
    assert all("{" not in value for _, value in rules)


def test_prompts_highlight_commands_differently():
    rule = lambda prompt: dict(build_style(prompt, "nord").style_rules)["lexer.command.valid"]  # noqa: E731
    assert rule("batman") == f"{STYLES['nord']['yellow']} bold"
    assert rule("pure") == STYLES["nord"]["green"]


def test_brightness_placeholders_reproduce_batman_gradient():
    rules = dict(build_style("batman", "batman").style_rules)
    assert [rules[f"arrow.ok.{i}"] for i in range(3)] == [
        "#333333 bold",
        "#666666 bold",
        "#aaaaaa bold",
    ]
    assert [rules[f"arrow.err.{i}"] for i in range(3)] == [
        "#660000 bold",
        "#990000 bold",
        "#cc0000 bold",
    ]


def test_execute_records_status_and_streams_output(fake, capsys, monkeypatch):
    errors: list[str] = []
    monkeypatch.setattr(Console, "stderr", lambda self, text: errors.append(text))
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
