"""Colour styles and the rules that consume them.

A style is eight colours. Rules reference them as ``{role}``; ``{role:60}`` is
that colour at 60% brightness (hex colours only). Add a style and F5 cycles to it.
"""

from __future__ import annotations

from prompt_toolkit.styles import Style

STYLES: dict[str, dict[str, str]] = {
    "batman": {"green": "#33aa55", "fg": "#aaaaaa", "bg": "#1c1c1c", "grey": "#666666", "red": "#cc0000", "yellow": "#ffaa00", "blue": "#3366ff", "magenta": "#ff0066"},
    "zenburn": {"green": "#60b48a", "fg": "#dcdccc", "bg": "#3f3f3f", "grey": "#709080", "red": "#dca3a3", "yellow": "#f0dfaf", "blue": "#94bff3", "magenta": "#ec93d3"},
    "nord": {"green": "#a3be8c", "fg": "#d8dee9", "bg": "#2e3440", "grey": "#4c566a", "red": "#bf616a", "yellow": "#ebcb8b", "blue": "#81a1c1", "magenta": "#b48ead"},
    "dracula": {"green": "#50fa7b", "fg": "#f8f8f2", "bg": "#282a36", "grey": "#6272a4", "red": "#ff5555", "yellow": "#f1fa8c", "blue": "#bd93f9", "magenta": "#ff79c6"},
    "gruvbox": {"green": "#b8bb26", "fg": "#ebdbb2", "bg": "#282828", "grey": "#928374", "red": "#fb4934", "yellow": "#fabd2f", "blue": "#83a598", "magenta": "#d3869b"},
    "solarized": {"green": "#859900", "fg": "#839496", "bg": "#002b36", "grey": "#586e75", "red": "#dc322f", "yellow": "#b58900", "blue": "#268bd2", "magenta": "#d33682"},
}  # fmt: skip

# Shared by every prompt: toolbar and menu backgrounds, comments, output.
BASE_RULES = {
    "stderr": "{red}",
    "auto-suggestion": "{grey}",
    "bottom-toolbar": "bg:{bg} {grey} noreverse",
    "completion-menu": "bg:{bg} {fg}",
    "completion-menu.meta.completion": "bg:{bg:150} {grey}",
    "lexer.comment": "{grey} italic",
}

PROMPT_RULES = {
    # oh-my-fish/theme-batman: ^^/d/prompter>>>  with (code) HH:MM:SS on the right
    "batman": {
        "path.home": "{yellow} bold",
        "path.sep": "{blue} bold",
        "path.base": "{yellow} bold",
        "arrow.ok.0": "{fg:30} bold",
        "arrow.ok.1": "{fg:60} bold",
        "arrow.ok.2": "{fg} bold",
        "arrow.err.0": "{red:50} bold",
        "arrow.err.1": "{red:75} bold",
        "arrow.err.2": "{red} bold",
        "dim": "{grey}",
        "fst": "{yellow} bold",
        "trd": "{magenta} bold",
        "bottom-toolbar.key": "{yellow} bold",
        "bottom-toolbar.sep": "{blue}",
        "completion-menu.completion.current": "bg:{yellow} {bg} bold",
        "completion-menu.meta.completion.current": "bg:{yellow} {bg:150}",
        "lexer.command.valid": "{yellow} bold",
        "lexer.command.invalid": "{magenta} bold",
        "lexer.option": "{blue}",
        "lexer.variable": "{blue} bold",
        "lexer.string": "{fg}",
        "lexer.operator": "{magenta} bold",
    },
    # sindresorhus/pure: user@host path time on one line, the arrow on the next.
    # Highlighting follows zsh-syntax-highlighting, pure's usual companion.
    "pure": {
        "path": "{blue}",
        "host": "{grey}",
        "took": "{yellow}",
        "status": "{red}",
        "arrow.ok": "{magenta}",
        "arrow.err": "{red}",
        "bottom-toolbar.key": "{magenta}",
        "bottom-toolbar.sep": "{grey}",
        "completion-menu.completion.current": "bg:{magenta} {bg}",
        "completion-menu.meta.completion.current": "bg:{magenta} {bg:150}",
        "lexer.command.valid": "{green}",
        "lexer.command.invalid": "{red}",
        "lexer.option": "{fg}",
        "lexer.variable": "{blue}",
        "lexer.string": "{yellow}",
        "lexer.operator": "{magenta}",
    },
}


class _Color(str):
    """``format(c, "60")`` -> the colour at 60% brightness (ANSI names pass through)."""

    def __format__(self, spec: str) -> str:
        if not spec or not self.startswith("#"):
            return str(self)
        pct = int(spec) / 100
        return "#" + "".join(
            f"{min(255, round(int(self[i : i + 2], 16) * pct)):02x}" for i in (1, 3, 5)
        )


def build_style(prompt: str, style: str) -> Style:
    palette = {role: _Color(value) for role, value in STYLES[style].items()}
    rules = {**BASE_RULES, **PROMPT_RULES[prompt]}
    return Style.from_dict({key: rule.format(**palette) for key, rule in rules.items()})
