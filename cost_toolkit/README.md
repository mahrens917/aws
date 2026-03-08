# Cost Toolkit (~/aws/cost_toolkit)

A consolidated home for every non-embedding artifact from `~/aws_cost`, now vendored directly into the primary `~/aws` workspace. The goal is to keep EBS/S3 migration, billing, auditing, cleanup, and RDS rescue scripts close to your existing S3 tooling without dragging along the old virtualenv or embedding experiments.

## Layout

```
cost_toolkit/
├── overview/                 # High-level cost+opportunity report (CLI entry: overview/cli.py)
├── requirements.txt          # Python dependencies for the toolkit
├── setup_environment.sh      # Optional helper to create venv locally
├── config/requirements.txt   # Historical dep list (kept for reference)
├── docs/
│   ├── README.md             # Doc index + usage pointers
│   ├── S3_SNAPSHOT_EXPORT_GUIDE.md
│   ├── export_logs/          # Saved manual export command batches
│   └── runbooks/             # Detailed playbooks + environment notes
├── scripts/
│   ├── aws_utils.py          # Shared credential helpers
│   ├── audit/                # Fleet-wide auditing scripts
│   ├── billing/              # Cost Explorer reports (+ shell runners)
│   ├── cleanup/              # Safe teardown helpers per service
│   ├── management/           # EBS + S3 standardization utilities
│   ├── migration/            # Snapshot/export orchestrators
│   ├── optimization/         # Snapshot → S3 workflows
│   ├── setup/                # Route53 + VM Import helper scripts
│   └── rds/                  # One-off RDS remediation scripts
```

Every module still keeps its original relative imports, so running a script from the repository root works exactly like it did in `~/aws_cost` (e.g., `python cost_toolkit/scripts/audit/aws_s3_audit.py`).

## Quick Start

1. **Dependencies** – Reuse the main repo environment or install the extras:
   ```bash
   pip install -r cost_toolkit/requirements.txt
   ```
   The heavier embedding stack stays behind in `~/aws_cost`, so this list is mostly boto3 + sentence-transformers for snapshot tooling.

2. **Credentials** – Prefer your existing `config_local.py` / AWS profiles. All scripts now call `aws_utils.setup_aws_credentials()`, which loads credentials from `~/.env` (or from the path you set via `AWS_ENV_FILE`) before touching AWS.

3. **Cost Overview** – Generate a service-level spend summary plus optimization hints:
   ```bash
   python -m cost_toolkit.overview.cli
   ```

4. **Billing Reports** – Use the Cost Explorer pullers:
   ```bash
   python cost_toolkit/scripts/billing/aws_billing_report.py
   bash cost_toolkit/scripts/billing/run_billing_report.sh
   ```

5. **Audits + Cleanup** – Run selective modules before you kick off bucket migrations:
   ```bash
   python cost_toolkit/scripts/audit/aws_s3_audit.py
   python cost_toolkit/scripts/cleanup/aws_vpc_cleanup.py
   ```

6. **Migration & Snapshot Offload** – The semi-manual snapshot exports plus their docs now live under `scripts/optimization/` and `docs/runbooks/`.

## RDS Rescue Scripts

The ad-hoc RDS helpers (`enable_rds_public_access.py`, `fix_default_subnet_group.py`, etc.) now live under `scripts/rds/`. They import from the shared `aws_utils` module via a relative path and expect to run from repository root:
```bash
python cost_toolkit/scripts/rds/enable_rds_public_access.py
```
Update instance IDs, subnet IDs, and especially passwords before use—these files contain historic values that were valid only for the original recovery session.

## Documentation Set

- `docs/README.md` links to every runbook, including ROO setup, domain fix notes, and the manual export guide.
- `docs/runbooks/*.md` house the longer-form procedures (Route53 fixes, Roo environment setup, environment bootstrap notes, etc.).
- `docs/export_logs/manual_export_commands_*.txt` preserves the exact CLI batches generated during July 2025 exports so you can replay or audit them later.

## Safety & Next Steps

- **Hardcoded credentials** – `scripts/cleanup/aws_cleanup_script.py` and a few RDS helpers still embed historical keys. Strip or replace them with profile-based auth before reuse in a shared environment.
- **Secrets in SQL helpers** – `scripts/rds/explore_aurora_data.py` and `explore_user_data.py` include passwords/hosts from the original restoration. Treat them as placeholders and rotate before running.
- **Testing** – Add import smoke tests (pytest) to ensure these modules stay loadable as you modernize them. Start with the logic-heavy utilities (billing report formatters, audit calculators).
- **Integration** – When you wire these scripts into automation, call them via `python -m cost_toolkit...` or add thin wrappers in `Makefile` to keep usage consistent with the rest of the repo.

Everything from the old `~/aws_cost` directory—except the embedding server, its requirements, and the disposable `venv/`—now lives here. Keep `~/aws_cost` around if you still need the embedding prototype; otherwise all cost-focused work happens inside this toolkit.
