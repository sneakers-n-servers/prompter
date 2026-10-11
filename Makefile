.PHONY: all
.PHONY: run
.PHONY: mypy
.PHONY: lint
.PHONY: format
.PHONY: clean
.PHONY: venv

mkfile_path := $(abspath $(lastword $(MAKEFILE_LIST)))
mkfile_dir := $(dir $(mkfile_path))
ROOT := $(realpath $(mkfile_dir))

include $(ROOT)/config.mk

UV := VIRTUAL_ENV=$(VENV_DIR) $(VENV_DIR)/bin/uv
UV_DONE := $(VENV_DIR)/.uv.done

all: $(UV_DONE) config.mk

$(UV_DONE): $(VENV)
	$(UV) run --active sync
	$(TOUCH) $@

run: $(UV_DONE)
	$(UV) run --active prompter $(ARGS)

mypy: $(UV_DONE)
	$(UV) run --active mypy prompter

lint: $(UV_DONE)
	$(UV) run --active ruff check prompter

format: $(UV_DONE)
	$(UV) run --active ruff format prompter

test: $(UV_DONE)
	$(UV) run --active pytest -v tests

upgrade: $(UV_DONE)
	$(UV) run --active uv lock --upgrade
	$(UV) sync --active

clean:
	$(RM) $(VENV)