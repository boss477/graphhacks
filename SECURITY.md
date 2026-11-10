# Security policy

## Supported versions

Security fixes go into the `master` branch.

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Report them privately through
[GitHub's private vulnerability reporting](https://github.com/boss477/graphhacks/security/advisories/new).
Include steps to reproduce, the affected commit, and the impact.

You will get an acknowledgment within a week. Once a fix ships, you will be credited in the
changelog unless you prefer to stay anonymous.

## Secrets

Slack credentials are read from `.env`, which is git-ignored. Every query is scoped to a tenant;
report any path that reads across tenants as a vulnerability.
