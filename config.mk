ifndef ROOT
$(error Must define ROOT)
endif

PY_VERSION ?= 3.14
HOST_PYTHON := /usr/bin/python$(PY_VERSION)
VENV_DIR := $(ROOT)/prompter-venv
PYTHON := $(VENV_DIR)/bin/python3
PIP := $(VENV_DIR)/bin/pip
VENV := $(VENV_DIR)/.done

RM := rm -rf
TOUCH := touch

venv: $(VENV)

$(VENV): $(ROOT)/pyproject.toml
	$(HOST_PYTHON) -m venv $(VENV_DIR)
	$(PIP) install --upgrade pip
	$(PIP) install uv
	$(TOUCH) $@

.DEFAULT_GOAL :=