Run the full quality check suite on the codebase. Execute these commands and report results:

1. `ruff check .` — Lint
2. `bandit -r backend/ -c pyproject.toml -ll -q` — Security scan (medium+ severity only)
3. `python -m pytest tests/ -x -q` — Tests (stop on first failure)
4. `python -m mypy backend/ --config-file pyproject.toml` — Type checking (focus on real bugs, not missing stubs)
5. `cd frontend && npx tsc --noEmit` — TypeScript type check

Report results concisely. If everything passes, say so. If anything fails, show the specific failures and offer to fix them.
