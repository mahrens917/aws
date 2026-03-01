# AWS Rules of Engagement

- Purpose: AWS S3 migration/policy tooling. Source lives at the repo root (`migration_state_v2.py`, `aws_utils.py`, CLI wrappers), with docs in `docs/`, tests in `tests/`, and shared CI assets in `ci_shared.mk` + `shared-tool-config.toml`.
- Install with `python -m pip install -e .`; keep generated artifacts (policies, DB files) out of git.

## Core Commands
- CI entry: `make check` or `python -m ci_tools.ci --model claude-sonnet-4-6` (delegates to `ci_tools/scripts/ci.sh` via `ci_shared.mk`).
- Tests: `pytest tests/ --cov=. --cov-fail-under=80 --cov-report=term -W error` (serial; no `-n`). Coverage guard enforces 80%.
- Dev helpers: `make format` (`isort --profile black .` + `black .`), `make lint` (`pylint`), `make type` (`pyright`), `make test` (`pytest`).
- Operational CLIs: `python migrate_v2.py status/reset`, `python block_s3.py --all`, `python apply_block.py --all --dry-run`—prefer dry runs when testing.

## Code Hygiene
- Avoid introducing fallbacks, duplicate code, backward-compatibility risks, fail-fast gaps, or dead code; if you encounter existing issues, highlight and fix them.
- Prefer config JSON files over adding new environment variables; only add ENV when required and document it.

## Duplicate Code Policy
- Search the repo before adding helpers (`rg "def <name>" .`), especially `aws_utils.py`, `migration_state_v2.py`, and shared CLI modules.
- If duplicates exist, centralize the best version, update callers to import it, and document the delegation.

## CI Contract (from `ci_tools/scripts/ci.sh`)
- Ordered stack: `codespell` → `vulture` → `deptry` → `gitleaks` → `bandit_wrapper` → `safety scan` (skipped when `CI_AUTOMATION` is set) → `ruff --fix` → `pyright --warnings` → `pylint` → `pytest` → `coverage_guard` → `compileall`.
- Limits: classes ≤100 lines; functions ≤80; modules ≤400; cyclomatic ≤10 / cognitive ≤15; inheritance depth ≤2; ≤15 public / 25 total methods; ≤5 instantiations in `__init__`/`__post_init__`; `unused_module_guard --strict`; documentation guard expects README/CLAUDE/docs hierarchy.
- Policy guard: bans `legacy`, `fallback`, `default`, `catch_all`, `failover`, `backup`, `compat`, `backwards`, `deprecated`, `legacy_mode`, `old_api`, `legacy_flag`, and TODO/FIXME/HACK/WORKAROUND; no broad/empty exception handlers; no literal fallbacks in `.get`/`setdefault`/ternaries/`os.getenv`/`if x is None`; blocks `time.sleep`, `subprocess.*`, and `requests.*` inside source.
- Prep: `tool_config_guard --sync` runs first; PYTHONPATH includes `ci_shared`.

## Non-Negotiables
- Fix issues instead of weakening checks (`# noqa`, `# pylint: disable`, `# type: ignore`, `policy_guard: allow-*`, or threshold changes are prohibited).
- Keep secrets and generated artifacts out of the repo; use `.gitleaks.toml`/`ci_tools/config/*` for sanctioned patterns.
- Maintain required docs (`README.md`, `CLAUDE.md`, `docs/README.md`, package READMEs) and avoid reverting user edits you didn’t make.
