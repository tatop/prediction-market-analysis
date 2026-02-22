# Repository Guidelines

## Project Structure & Module Organization
Core code lives in `src/`:
- `src/indexers/` contains data collectors for `kalshi`, `polymarket`, and `alpaca` (clients, models, indexers).
- `src/analysis/` contains analysis modules by domain (`kalshi`, `polymarket`, `alpaca`, `comparison`).
- `src/common/` contains shared abstractions (for example base `Analysis`/`Indexer` classes, storage, chart interfaces, utilities).

Tests are in `tests/` (`test_*.py`). Documentation is in `docs/` (`ANALYSIS.md`, `SCHEMAS.md`). Runtime artifacts are generated in `data/` and `output/` and should not be committed.

## Build, Test, and Development Commands
- `uv sync --group dev`: install runtime + dev dependencies.
- `make setup`: install tooling helpers and download/extract the sample dataset.
- `make index`: run interactive indexer selection (`uv run main.py index`).
- `make analyze`: run interactive analysis selection (`uv run main.py analyze`).
- `uv run main.py analyze alpaca_bar_metrics`: run one analysis directly.
- `make lint`: run Ruff lint and formatting checks.
- `make format`: auto-fix lint issues and format code.
- `make test`: run the full pytest suite (`uv run pytest tests/ -v`).

## Coding Style & Naming Conventions
Use Python 3.9+ with 4-space indentation, type hints, and concise docstrings. Ruff is the source of truth for style (`line-length = 120`; import sorting enabled). Use:
- snake_case for modules, functions, and variables.
- PascalCase for classes (analysis classes typically end with `Analysis`).
- UPPER_SNAKE_CASE for constants.

## Testing Guidelines
Use `pytest` for all tests. Name files `tests/test_*.py` and tests `test_*`. Add or update tests for any behavior change, especially new analyses/indexers and bug fixes. Mark expensive tests with `@pytest.mark.slow` where appropriate. For focused runs, use `uv run pytest tests/test_analysis_run.py -k Alpaca`.

## Commit & Pull Request Guidelines
Recent history uses short, imperative commit subjects, often with Conventional Commit prefixes (`feat:`, `fix:`, `chore:`, `refactor:`). PR titles are CI-validated and must match:
`<type>(<scope>): <description>` or `<type>: <description>`.

Use `.github/PULL_REQUEST_TEMPLATE.md` and complete all sections:
- `What changed? Why?`
- `Notes to reviewers`
- `How has it been tested?`

Link related issues and include screenshots when output visuals change.

## Security & Configuration Tips
Keep secrets in `.env` only; start from `.env.example`. Common keys include `POLYGON_RPC`, `ALPACA_API_KEY`, and `ALPACA_SECRET_KEY`. Never commit credentials, generated datasets, or archives (`*.tar.zst`).
