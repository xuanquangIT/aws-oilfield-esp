# Security Policy

## Supported Versions

This repository is maintained as an active open-source AWS data engineering capstone. Only the latest commit on the `main` branch receives security updates.

| Version / Branch | Supported          |
| ---------------- | ------------------ |
| `main`           | :white_check_mark: |
| Older commits    | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability or potential credential leak within this repository, please report it privately:

- **Primary Contact:** Vu Xuan Quang
- **Email:** [vuxuanquang04@gmail.com](mailto:vuxuanquang04@gmail.com)
- **Subject:** `[SECURITY] aws-oilfield-esp Vulnerability Report`

Please include:
1. A description of the issue and the potential impact.
2. Steps to reproduce or proof-of-concept code.
3. Any suggested mitigation or fix.

Please do not open a public GitHub issue for sensitive security vulnerabilities until they have been reviewed and addressed. We will acknowledge receipt of your report within 48 hours and provide updates until resolution.

## Core Security & Privacy Principles

1. **Zero Secret Exposure**:
   - **Never** commit AWS access keys, secret keys, session tokens, passwords, private certificates, or `.env` files.
   - All infrastructure code uses IAM roles and standard AWS credential provider chains.
   - Offline tests enforce negative security checks preventing secrets from leaking into API responses or logs.

2. **Synthetic Data Only**:
   - All oilfield data, downhole telemetry, and well logs in this repository are **100% synthetic** generated for educational and demonstration purposes.
   - Never commit proprietary or real field production data to this repository.

3. **Disposable Architecture & Principle of Least Privilege**:
   - Workload roles are strictly scoped to minimal required IAM actions with explicit deny gates for destructive or cross-stack permissions.
   - Realtime streaming stacks are designed to be spun up for controlled demos and immediately torn down to minimize exposure and cost.

4. **Local-First Dashboard Security**:
   - The surveillance dashboard server binds strictly to the loopback interface (`127.0.0.1`).
   - Browser client code never interacts with the AWS SDK or receives AWS credentials; all access is brokered through the server-side API.
