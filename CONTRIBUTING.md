# Contributing to AWS Oilfield ESP Data Platform

Thank you for your interest in contributing to the **AWS Oilfield ESP Data Platform**! This project is an enterprise-grade, cost-aware data engineering capstone demonstrating real-time and batch analytics on AWS for offshore Electrical Submersible Pump (ESP) surveillance.

We welcome contributions from the community—whether bug fixes, architectural improvements, documentation updates, or new DEA-C01 learning extensions.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Architectural Principles](#architectural-principles)
3. [Getting Started & Local Setup](#getting-started--local-setup)
4. [Development Workflow](#development-workflow)
5. [Coding & Infrastructure Standards](#coding--infrastructure-standards)
6. [Testing & Verification](#testing--verification)
7. [Commit & Pull Request Guidelines](#commit--pull-request-guidelines)
8. [Reporting Security Issues](#reporting-security-issues)

---

## Code of Conduct

All contributors and participants are expected to adhere to our [Code of Conduct](CODE_OF_CONDUCT.md). Please report any unacceptable behavior to [vuxuanquang04@gmail.com](mailto:vuxuanquang04@gmail.com).

---

## Architectural Principles

Before contributing code or infrastructure changes, please keep our core tenets in mind:

1. **Near-Zero Idle Cost**: Baseline parked cost must stay near ~$0.03/month. Any new service must have a clear teardown, lifecycle rule, or disposable boundary.
2. **Separation of Concerns**:
   - `oilfield-esp-core`: Persistent, storage, application Lambdas, Glue, Athena, and governance.
   - `oilfield-esp-realtime`: Ephemeral, disposable Kinesis stream and event source mappings. Never reference realtime from core.
3. **Reproducibility & Evidence**: Any behavior change should have offline tests. Cloud claims must be supported by verifiable evidence.
4. **Zero Secrets**: No AWS credentials, account IDs, session tokens, or private customer data in version control.

---

## Getting Started & Local Setup

### Prerequisites

- **Python 3.12**
- **Node.js 24.x** (or LTS 20+)
- **PowerShell 7+** (recommended for running automation scripts)
- **AWS CLI v2** (configured if deploying to an AWS account; not required for offline development)

### Setting Up Your Environment

1. **Clone the repository:**
   ```bash
   git clone https://github.com/xuanquangIT/aws-oilfield-esp.git
   cd aws-oilfield-esp
   ```

2. **Create and activate a virtual environment:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   *(On Linux/macOS: `source .venv/bin/activate`)*

3. **Install locked dependencies:**
   ```powershell
   pip install -r requirements-lock.txt
   npm ci
   ```

> [!NOTE]
> Only update `requirements-lock.txt` or `package-lock.json` when intentionally upgrading project dependencies from an isolated environment.

---

## Development Workflow

1. Create a feature branch off `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Make your code or documentation changes.
3. Add or update unit tests in `tests/`.
4. Validate everything locally before committing:
   ```powershell
   .\scripts\validate.ps1
   ```

---

## Coding & Infrastructure Standards

### Python Standards
- Write clean, readable code following PEP 8.
- Use explicit type hints for function signatures and data models.
- All incoming telemetry must validate against schemas in `src/contract.py`.
- Handle failures defensively (e.g. exponential backoff, DLQ handling, conditional writes).

### AWS CDK & Infrastructure Standards
- Construct IDs and logical resource names must follow existing naming conventions (`f"{prefix}-core"`, `f"{prefix}-realtime"`).
- Workload IAM roles must follow least privilege with explicit denies for destructive actions.
- Tag all deployed resources with the standard cost allocation tag: `Project: oilfield-esp`.
- Log groups must have explicit retention periods (7 days maximum for dev/demo).

### Documentation Standards
- Keep documentation in sync with code changes.
- If introducing an architectural change, document the decision in `docs/adr/`.
- Run `python scripts/check-docs.py` to ensure all local markdown links and asset paths resolve.

---

## Testing & Verification

The project enforces offline validation so you can develop and test without incurring AWS charges or needing active credentials:

```powershell
.\scripts\validate.ps1
```

This single command executes:
1. **Unit & Integration Tests**: `pytest -q` (validating contract schemas, anomaly detection cooldowns, idempotent state writes, and API handlers).
2. **Documentation Integrity**: `python scripts/check-docs.py` (verifying all relative Markdown links and checking for unresolved markers).
3. **Script Syntax & Behavior**: `tests/test_scripts.ps1` (verifying PowerShell script syntax, error trapping, and teardown paths).
4. **CDK Template Synthesis**: `cdk synth --quiet --no-lookups --no-telemetry` (confirming CloudFormation templates synthesize without errors).

To run specific tests quickly:
```powershell
pytest tests/test_anomaly_detector.py -v
pytest tests/test_dashboard.py -v
```

To test the surveillance dashboard locally in fixture mode:
```powershell
.\scripts\dashboard.ps1 -Mode fixture -FixtureState normal
```

---

## Commit & Pull Request Guidelines

### Commit Messages
We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

- `feat:` A new feature or capability
- `fix:` A bug fix
- `docs:` Documentation changes only
- `test:` Adding or refactoring tests
- `refactor:` Code refactoring with no behavior change
- `chore:` Dependency updates, tooling, or build configuration

*Example:* `feat(anomaly): add cooldown period for high temperature alarms`

### Pull Request Checklist

When submitting a PR:
- [ ] Fill out the PR template completely.
- [ ] Ensure all tests pass locally with `.\scripts\validate.ps1`.
- [ ] Verify that no secrets, credentials, or private data are committed.
- [ ] Keep pull requests focused on a single topic or issue.

---

## Reporting Security Issues

Please **do not** open public GitHub issues for security vulnerabilities or credential disclosures. Follow the instructions in [SECURITY.md](SECURITY.md) to contact the maintainer privately.
