# Security Policy

## Reporting a vulnerability

If you discover a security issue, please **do not open a public issue**.
Instead, report it privately via
[GitHub Security Advisories](https://github.com/Dung205789/Spec2Ship/security/advisories/new)
or by email to the maintainer. You will receive an acknowledgement within a
reasonable timeframe.

## Security model & hardening

Spec2Ship executes commands and applies AI-generated patches against
**untrusted, user-uploaded codebases**. Several safeguards are built in:

- **Workspace isolation** — each run operates on an isolated copy under
  `data/run_workspaces/<run_id>/` (`ISOLATE_WORKSPACES=true`).
- **Upload limits** — archive size, extracted size, file count, and per-file
  size are bounded (`WORKSPACE_*` settings) to mitigate zip-bomb / path-traversal
  attacks.
- **Command timeouts** — every shell, git, and test command runs under an
  explicit timeout (`*_SECONDS` settings).
- **Human-in-the-loop gate** — no patch is applied until a human explicitly
  approves the proposed diff.

## Deployment notes

- Change the default `POSTGRES_*` credentials before any non-local deployment.
- `.env` is **git-ignored**; never commit real secrets.
- The worker mounts the Docker socket for benchmark sandboxing — run it on a
  trusted host only.
