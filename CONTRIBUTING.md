# Contributing

Start from PROJECT-STATUS.md and the next delivery-plan milestone. Documents and code comments are English. Preserve unrelated changes and keep generated data/secrets out of source control.

Install locked dependencies, run scripts/validate.ps1 and review synthesized changes before any AWS deployment. Refresh requirements-lock.txt from an isolated Python 3.12 environment only when intentionally upgrading dependencies; update package-lock.json with the pinned CDK CLI.

For a behavior change, include a failure/recovery test where meaningful. For new AWS resources, specify owner, lifecycle, cost, permissions and teardown. Update status, runbook and ADR with code so planned capabilities are never presented as implemented.

The directory was not initialized as Git during the review. The maintainer can create a repository when ready; no remote, commit or push was performed. CI runs offline validation after publishing and enabling GitHub Actions. Live deployment remains a separately reviewed operation.
