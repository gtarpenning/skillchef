.PHONY: test lint typecheck check build release verify-uvx

test:
	uv run pytest -q

lint:
	uv run --extra dev ruff check

typecheck:
	uv run --extra dev ty check

check: test lint typecheck

build:
	uv build --clear

release: check build
	@TOKEN=$$(python3 -c 'import configparser, pathlib; cfg = configparser.RawConfigParser(); cfg.read(pathlib.Path.home() / ".pypirc"); print(cfg.get("pypi", "password", fallback=""), end="")' 2>/dev/null); \
	test -n "$$TOKEN" || { echo "PyPI token not found in ~/.pypirc [pypi].password"; exit 1; }; \
	uv publish --token "$$TOKEN"

verify-uvx:
	@test -n "$$VERSION" || (echo "VERSION is required, e.g. make verify-uvx VERSION=0.2.7" && exit 1)
	uvx --from skillchef==$$VERSION skillchef --help
