from prompter.local import LocalShell
from prompter.state import ShellState
from prompter.theme import (
    ShellLexer,
    abbreviate_path,
    build_prompt,
    build_rprompt,
    build_toolbar,
    format_duration,
)


def test_abbreviate_path_fish_style():
    home = "/home/me"
    assert abbreviate_path(home, home) == "~"
    assert abbreviate_path("/home/me/dev", home) == "~/dev"
    assert abbreviate_path("/home/me/dev/prompter", home) == "~/d/prompter"
    assert abbreviate_path("/home/me/.config/nvim/lua", home) == "~/.c/n/lua"
    assert abbreviate_path("/", home) == "/"
    assert abbreviate_path("/usr/local/bin", home) == "/u/l/bin"
    assert abbreviate_path("/usr/local/bin") == "/u/l/bin"
    assert abbreviate_path("", None) == ""


def test_abbreviate_path_windows():
    home = r"C:\Users\Mike"
    assert abbreviate_path(home, home, windows=True) == "~"
    assert abbreviate_path(r"C:\Users\Mike\dev\prompter", home, windows=True) == r"~\d\prompter"
    assert abbreviate_path("C:\\", home, windows=True) == "C:\\"
    assert abbreviate_path(r"D:\Program Files\Git\bin", home, windows=True) == r"D:\P\G\bin"
    assert abbreviate_path(r"\\srv\share\x", home, windows=True) == r"\\srv\share\x"


def test_format_duration():
    assert format_duration(0.0123) == "12ms"
    assert format_duration(2.34) == "2.3s"
    assert format_duration(125) == "2m05s"


def _text(fragments) -> str:
    return "".join(t for _, t in fragments)


def test_prompt_is_single_line_batman_style(tmp_path):
    shell = LocalShell(cwd="/home/me/dev/prompter", env={"HOME": "/home/me"})
    state = ShellState(shell)
    fragments = list(build_prompt(state))
    assert _text(fragments) == "^^/d/prompter>>> "
    assert "\n" not in _text(fragments)
    assert ("class:path.home", "^^") in fragments
    assert ("class:path.sep", "/") in fragments
    assert ("class:path.base", "prompter") in fragments
    assert [s for s, _ in fragments if s.startswith("class:arrow")] == [
        "class:arrow.ok.0",
        "class:arrow.ok.1",
        "class:arrow.ok.2",
    ]

    state.last_status = 127
    assert all(s.startswith("class:arrow.err") for s, t in build_prompt(state) if t == ">")

    root = ShellState(LocalShell(cwd="/", env={"HOME": "/home/me"}))
    assert _text(build_prompt(root)) == "/>>> "


def test_prompt_and_toolbar_for_windows_backend(fake_backend):
    state = ShellState(fake_backend)
    fragments = list(build_prompt(state))
    assert _text(fragments) == "^^\\d\\prompter>>> "
    assert ("class:path.sep", "\\") in fragments
    toolbar = list(build_toolbar(state))
    assert ("class:bottom-toolbar.host", " appliance") in toolbar
    assert ("", r"C:\Users\Mike\dev\prompter") in toolbar


def test_rprompt_shows_status_host_and_time():
    shell = LocalShell(cwd="/", env={"HOME": "/x"})
    state = ShellState(shell)
    text = _text(build_rprompt(state))
    assert "(" not in text and len(text) == 8  # HH:MM:SS only

    state.last_status = 2
    shell.env["SSH_CONNECTION"] = "1.2.3.4 1 5.6.7.8 22"
    fragments = list(build_rprompt(state))
    assert ("class:rprompt.trd", "2") in fragments
    assert _text(fragments).startswith(f"(2) :{shell.host} ")


def _lex(line: str) -> list[tuple[str, str]]:
    return ShellLexer(lambda name: name in {"ls", "grep"})._lex_line(line)


def test_lexer_marks_known_and_unknown_commands():
    tokens = _lex("ls -la | nope 'x y' $HOME # hi")
    assert ("class:lexer.command.valid", "ls") in tokens
    assert ("class:lexer.option", "-la") in tokens
    assert ("class:lexer.operator", "|") in tokens
    assert ("class:lexer.command.invalid", "nope") in tokens
    assert ("class:lexer.string", "'x y'") in tokens
    assert ("class:lexer.variable", "$HOME") in tokens
    assert ("class:lexer.comment", "# hi") in tokens


def test_lexer_assignment_prefix_and_subshell():
    tokens = _lex("FOO=1 grep $(ls)")
    assert ("class:lexer.assignment", "FOO=1") in tokens
    assert ("class:lexer.command.valid", "grep") in tokens
    assert ("class:lexer.command.valid", "ls") in tokens
