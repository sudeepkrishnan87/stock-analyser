# Harness.io pipeline scaffold

This is a **learning scaffold**, not a drop-in replacement for `.github/workflows/deploy.yml`. That GitHub Actions workflow keeps running the live deploys until you've manually verified this pipeline end-to-end in your own Harness account. Don't delete or disable the GitHub Action based on this scaffold existing.

## Why this exists side by side with GitHub Actions

| | `.github/workflows/deploy.yml` (current, live) | `.harness/pipeline.yaml` (this scaffold) |
|---|---|---|
| Trigger | push to `main` | Harness Trigger (webhook), not yet configured |
| Pre-deploy verification | none — straight to SSH deploy | new: compile-check backend, build frontend, grep for leaked-secret pattern |
| Deploy mechanism | `appleboy/ssh-action` from a GitHub-hosted runner | Harness `ShellScript` step run by a Harness Delegate |
| Secrets | GitHub Actions secrets (`EC2_HOST`, `EC2_SSH_KEY`) | Harness secrets (`ec2_host`, `ec2_ssh_key`) — same values, different store |
| Rollback | none (matches current reality) | none yet — same gap, carried over deliberately rather than silently fixed |

The deploy step itself is intentionally almost line-for-line the same shell script as the GitHub Action — the point of this scaffold is to learn Harness's pipeline/stage/step model and its secrets/delegate mechanics using a deploy flow you already understand, not to redesign the deploy process at the same time.

## One-time Harness account setup required before this pipeline can run

1. **Create an Organization and Project** in the Harness UI, then replace `projectIdentifier`/`orgIdentifier` in `pipeline.yaml` (currently `<+input>` placeholders — Harness will prompt for these values at pipeline creation if you import the YAML as-is, which is fine for a first run).

2. **Install a Harness Delegate** somewhere that can reach your EC2 instance over SSH — simplest option for a single personal project: install the Delegate directly on the EC2 box itself (Harness → Project Setup → Delegates → Install → Docker/Helm/Kubernetes instructions), so `ssh ubuntu@<host>` in the deploy step is really just `ssh` to itself, or install it on any machine with SSH access to the box (e.g. your Mac, running continuously, which is less realistic for a "hands-off" pipeline).

3. **Create a GitHub connector** (Connectors → New Connector → GitHub) authorized against `sudeepkrishnan87/stock-analyser`, and put its identifier into `codebase.connectorRef` in `pipeline.yaml`.

4. **Create two secrets** (Project Setup → Secrets → New Secret Text/File):
   - `ec2_host` — your EC2 Elastic IP or domain (same value as the `EC2_HOST` GitHub secret)
   - `ec2_ssh_key` — contents of your `.pem` file (same value as the `EC2_SSH_KEY` GitHub secret)

   These are referenced in the pipeline as `<+secrets.getValue("ec2_host")>` / `<+secrets.getValue("ec2_ssh_key")>`.

5. **Import `pipeline.yaml`** via Harness's Git Experience (Pipelines → New Pipeline → Import From Git, pointing at this repo/branch/path) so the pipeline definition stays version-controlled here rather than only living in the Harness UI — this is the standard "pipeline as code" pattern Harness calls Git Experience / GitOps for pipelines.

6. **Add a Trigger** (Triggers → New Trigger → Webhook → Git Push) scoped to `main`, mirroring the GitHub Action's `on: push: branches: [main]`, once you're confident in a few manual runs.

## Running it for the first time

Trigger the pipeline **manually** first (Pipelines → Run), not via an automated trigger — confirm the Build and Verify stage passes, then confirm the deploy stage's SSH step reaches the box and the script runs (watch it complete the same `git pull → build → up → health curl` sequence you already know from the GitHub Actions logs). Only wire up the automated push trigger once you've watched at least one full manual run succeed.

## Extending this scaffold

- Adding a real secret scanner (gitleaks/trufflehog) as a step instead of the current grep heuristic is a natural next step — the current check only catches the exact shape of secret that leaked before (see `docs/SECURITY.md`), not secrets in general.
- Adding automated tests as a Build and Verify step once any exist (there are currently no automated tests in this repo — see `docs/SECURITY.md` / `CLAUDE.md` for the current state of things).
- A rollback step (re-deploy the previous image tag if the health check fails) is the most valuable near-term addition, since neither this pipeline nor the current GitHub Action has one today.
