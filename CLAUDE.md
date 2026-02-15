# AWS: Claude Guide

S3 management toolkit. Four-phase resumable migration (scan → restore → sync → verify), bucket policy hardening, duplicate detection, cost analysis. Source at root, shared CI assets in `ci_tools/`, configs in `ci_shared.mk` + `shared-tool-config.toml`, tests in `tests/`, docs in `docs/`.

## Quick Commands
- Run CI/automation with `make check` or `python -m ci_tools.ci --model gpt-5-codex` (delegates to `scripts/ci.sh` through `ci_shared.mk`).
- Tests: `pytest tests/ --cov=. --cov-fail-under=80 --cov-report=term -W error` (serial only). Coverage guard enforces the same threshold.
- Formatting/type/lint: `make format`, `make type`, `make lint`, `make test`. Prefer dry-run CLIs (`python migrate_v2.py status`, `python block_s3.py --all`, `python apply_block.py --all --dry-run`) when exercising workflows.

## Code Hygiene
- Avoid adding fallbacks, duplicate code, or backward-compatibility shims (backward compatibility is not required); call out and fix fail-fast gaps or dead code when encountered.
- Prefer config JSON files over new environment variables; only add ENV when required and document it.

## Duplicate Code Rule
- Search before adding helpers (`rg "def <name>" .`), particularly `aws_utils.py`, `migration_state_v2.py`, and shared CLI modules.
- If duplicates appear, centralize the best version, import it from callers, and document the delegation.

## CI Pipeline (exact order)
- `codespell` → `vulture` → `deptry` → `gitleaks` → `bandit_wrapper` → `safety scan` (skipped with `CI_AUTOMATION`) → `ruff --fix` → `pyright --warnings` → `pylint` → `pytest` → `coverage_guard` → `compileall`.
- Limits: classes ≤100 lines; functions ≤80; modules ≤400; cyclomatic ≤10 / cognitive ≤15; inheritance depth ≤2; ≤15 public / 25 total methods; ≤5 instantiations in `__init__`/`__post_init__`; `unused_module_guard --strict`; documentation guard expects README/CLAUDE/docs hierarchy.
- Policy guard reminders: banned tokens (`legacy`, `fallback`, `default`, `catch_all`, `failover`, `backup`, `compat`, `backwards`, `deprecated`, `legacy_mode`, `old_api`, `legacy_flag`, TODO/FIXME/HACK/WORKAROUND), no broad/empty exception handlers, no literal fallbacks in `.get`/`setdefault`/ternaries/`os.getenv`/`if x is None`, and no `time.sleep`/`subprocess.*`/`requests.*` inside source.
- Prep: `tool_config_guard --sync` runs up front; PYTHONPATH is set to include `ci_shared`.

## Do/Don't
- Do fix root causes—never bypass checks (`# noqa`, `# pylint: disable`, `# type: ignore`, `policy_guard: allow-*`, or threshold changes are off-limits).
- Do keep secrets and generated artifacts out of git; rely on `.gitleaks.toml`/`ci_tools/config/*` for sanctioned patterns.
- Do keep required docs current (`README.md`, `CLAUDE.md`, `docs/README.md`, package READMEs) and leave user edits intact.
