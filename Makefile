# Compute4Me developer tasks. See CONTRIBUTING.md for the full workflow.

IMAGE ?= ghcr.io/premity/compute4me:dev

.PHONY: dev test lint types image e2e

# Sync deps (creates .venv) and install pre-commit hooks.
dev:
	uv sync
	uv run pre-commit install

# CI default: skip tests needing real Docker/GPU. Run `uv run pytest` for the full set.
test:
	uv run pytest -m "not requires_docker and not requires_gpu"

# Mirror the ci-lint gate.
lint:
	uv run ruff check .
	uv run ruff format --check .

# Mirror the ci-types gate.
types:
	uv run mypy --strict src/

# Build the single serve/worker image.
image:
	docker build -t $(IMAGE) .

# End-to-end smoke test: Master + 2 fake Workers + a tiny Search Job (lands with T17).
e2e:
	uv run pytest -m "integration" tests/integration/
