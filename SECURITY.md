# Security Policy

## Supported Versions

Security fixes are applied to the latest code on `main` and the latest published release.

## Reporting a Vulnerability

- Do not open a public GitHub issue for security bugs.
- If GitHub private vulnerability reporting is enabled for this repository, use that first.
- Otherwise, contact the maintainer privately through the contact method listed on the repository profile or package metadata.

Include:

- What you found
- How to reproduce it
- Whether tokens, grades, or student data can be exposed
- Any suggested mitigation

## Scope

High-priority issues include:

- Token exposure
- Unsafe filesystem writes
- Unexpected network destinations
- Student data leakage in logs or artifacts
- Supply-chain compromise in release automation

## Out of Scope

- Cosmetic issues with no security impact
- Requests to support insecure deployment patterns
