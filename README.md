# prompter

A small, pretty [prompt_toolkit](https://python-prompt-toolkit.readthedocs.io/) console
to copy into projects that need an interactive shell against some backend. Two prompts:
[batman](https://github.com/oh-my-fish/theme-batman) (fish-style abbreviated path, `>>>`
that turns red on a non-zero exit, exit code and clock on the right) and
[pure](https://github.com/sindresorhus/pure) (path on one line, `❯` on the next). Host and
timing live in a bottom toolbar. Tab completes commands,
paths and `$VARS`; known commands highlight as you type; stderr is red. **F5** cycles colour
styles (batman, zenburn, nord, dracula, gruvbox, solarized).

```
^^/d/prompter>>> ls -la                                  (127) 10:45:40
```

## Use

```sh
make run                                  # local /bin/sh backend
make run ARGS="--prompt pure"
make run ARGS="--prompt pure --style nord"
make test lint mypy
```

Styles are eight-colour dicts in [`prompter/themes.py`](prompter/themes.py); prompt rules
reference them as `{blue}` or `{red:60}` (60 % brightness). Add a dict and F5 picks it up.
