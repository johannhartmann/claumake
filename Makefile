SHELL := /bin/bash

.PHONY: help setup lint type fmt test build clean

help:
	@echo "Dev targets: setup lint type fmt test build clean"

setup:
	@which uv >/dev/null 2>&1 && \
	  uv pip install -e .[dev,actions] || \
	  pip install -e .[dev,actions]

lint:
	ruff check .

type:
	mypy claumake

fmt:
	ruff format .
	ruff check --fix .

test:
	pytest -q

build:
	python -m build

clean:
	git clean -xfd -e node_modules -e .venv -e venv -e .tox

