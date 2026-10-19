.PHONY: install run lint build check

install:
	uv sync

run:
	uv run valutatrade-hub

lint:
	uv run ruff check .

build:
	uv build

check: lint build
