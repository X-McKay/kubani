validate:
    uv sync --locked
    uv run --locked ruff check .
    uv run --locked ruff format --check .
    uv run --locked pytest
    uv run --locked zetra check .
    uv run --locked python evals/run.py
    uv build --wheel
    uv run --locked python tests/packaging/check_wheel.py dist/*.whl
