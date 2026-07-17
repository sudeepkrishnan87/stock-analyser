# Deployment — Jarvis on AWS

One-stop reference for everything between "I have a `.pem` file" and "the change is live." Written 2026-07-16 from the actual state of the running instance — not the aspirational setup docs. If reality drifts from this doc again, trust `aws ec2 describe-instances` / `docker compose ps` over anything written down, including this file.

## Current infrastructure (ground truth, verified 2026-07-16)

| | Value |
|---|---|
| EC2 instance | `i-0d7c9e38884df099e`, `t3.micro`, **ap-south-1 (Mumbai)** |
| Public IP | `13.203.141.195` — this is an **Elastic IP** (`eipalloc-04154cdf3b9b810e9`), so it survives stop/start, but not termination |
| Domain | `jarvis.mytechexp.com` → resolves to the Elastic IP above |
| SSH key pair | `stockbot-mumbai` — private key at `~/Downloads/stockbot-mumbai.pem` |
| App directory on server | `/opt/stockbot` (git clone, same repo as local) |
| Secrets | AWS SSM Parameter Store, **eu-north-1 (Stockholm)** — see mismatch note below |
| Trade book backup | S3 bucket `jarvis-tradebook-backup-233903268134`, **ap-south-1** (same region as EC2, deliberately — this is a new resource, not an old one to leave alone like the SSM mismatch). Versioned, private, 90-day noncurrent-version expiry. Written by `services/backup_service.py` after every trade-state save; restored on startup only if the local file is missing. Production-only (`ENVIRONMENT=production`) — local dev never touches it. |
| Containers | `stockbot-api`, `stockbot-frontend`, `stockbot-nginx`, `stockbot-certbot` (`docker-compose.yml`) |
| Deploy trigger | push to `main` → `.github/workflows/deploy.yml` → SSH → `git pull` → `docker compose build` → `up -d` |

### ⚠️ Known inconsistency: EC2 is in Mumbai, secrets are in Stockholm

`backend/config.py:32` does `boto3.client("ssm", region_name=os.getenv("AWS_REGION", "eu-north-1"))`. `AWS_REGION` is never set anywhere (`docker-compose.yml`, systemd unit, or the deploy scripts), so it silently defaults to `eu-north-1` regardless of where the EC2 box actually is. This **works** — SSM calls are a plain API call over the internet, not tied to instance placement — but it means:

- Checking `ap-south-1` for `/stockbot/*` parameters finds nothing and looks like a "missing secret" when it's really just the wrong region.
- `deploy/add-secrets.sh` has a comment telling you to `aws configure` with region `ap-south-1`, but hardcodes `REGION="eu-north-1"` two lines later — that comment is stale/wrong, not a typo to "fix" by changing the REGION value without also migrating the parameters.
- **Always use `--region eu-north-1` for any `aws ssm` command against this app's secrets**, even though the EC2 box itself is in `ap-south-1`, until/unless someone deliberately migrates the parameters (not done as of this doc — it's a real fix worth doing, just not done yet, since it means copying every `/stockbot/*` parameter and flipping `AWS_REGION` at the same time, not something to do casually).

## One-time setup (already done — reference only, don't re-run against the live box)

Bootstrapping a *new* box: `deploy/setup.sh` (installs Docker, AWS CLI, hardens SSH, clones the repo, gets a Let's Encrypt cert, installs the systemd unit). See that script's header comment for usage. Not needed again unless the instance is destroyed and rebuilt.

## Getting a terminal on the EC2 box

```bash
chmod 600 ~/Downloads/stockbot-mumbai.pem   # first time only, SSH refuses keys with looser perms
ssh -i ~/Downloads/stockbot-mumbai.pem ubuntu@13.203.141.195
# or, once DNS/SSH access is confirmed working:
ssh -i ~/Downloads/stockbot-mumbai.pem ubuntu@jarvis.mytechexp.com
```

Once in: the app lives at `/opt/stockbot`, containers are managed with `sudo docker compose ...` from that directory (root is required — `ubuntu` isn't in the `docker` group in every install, check with `docker compose ps` first and prefix `sudo` if it complains).

## Normal deploy flow (the 99% case)

```bash
git push origin main
```

That's it — `.github/workflows/deploy.yml` fires automatically: SSH in, `git pull`, `docker compose build api frontend`, `docker compose up -d`, wait 15s, curl `/api/health` inside the container. Watch it at `https://github.com/sudeepkrishnan87/stock-analyser/actions` or, if `gh` is installed locally, `gh run watch`.

**No test/lint gate exists in this pipeline.** A push that compiles but has a logic bug will deploy anyway. Run `python3 -m py_compile` and `npm run typecheck` yourself before pushing anything touching `backend/` or `frontend/src/` — see `.claude/skills/deploy-check` for the fuller pre-push checklist, especially for anything touching `trading_service.py`, `scheduler_service.py`, or `brokers/`.

## Manual deploy fallback (when CI fails)

CI's SSH step can fail for reasons unrelated to your code — most commonly, **the EC2 instance was stopped** (this project doesn't run the box 24/7). If a GitHub Actions run fails at the "Deploy via SSH" step, first check the instance is actually running:

```bash
aws ec2 describe-instances --region ap-south-1 --filters "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].{ID:InstanceId,IP:PublicIpAddress,State:State.Name}" --output table
```

If it's stopped, start it (Elastic IP means the address won't change) and either re-run the failed GitHub Actions job, or just do it by hand:

```bash
ssh -i ~/Downloads/stockbot-mumbai.pem ubuntu@13.203.141.195 "cd /opt/stockbot && \
  git pull origin main && \
  sudo docker compose build api frontend && \
  sudo docker compose up -d && \
  sleep 15 && \
  sudo docker compose ps && \
  sudo docker compose exec -T api curl -sf http://localhost:8000/api/health"
```

Run those as separate commands (not one `&&` chain) if you want to see each step's output as it happens rather than all at once at the end.

## Pushing `.env` / secret changes to AWS

There is **no `.env` file on the EC2 box** — every secret is read from SSM Parameter Store at container startup via the instance's IAM role. Changing a value locally in `backend/.env` does nothing to production until you push it to SSM *and* restart the container.

### Bulk push (every secret in your local `.env`)

```bash
./deploy/add-secrets.sh
```

Reads `backend/.env`, pushes every non-empty value to `/stockbot/<NAME>` in SSM (`eu-north-1`), skipping anything blank. Safe to re-run any time — it's idempotent (`--overwrite`).

### Single key (e.g. rotating just `API_SECRET_KEY`)

```bash
NEW_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
# update backend/.env yourself with $NEW_KEY first, then:
aws ssm put-parameter --region eu-north-1 --name /stockbot/API_SECRET_KEY \
  --value "$NEW_KEY" --type SecureString --overwrite --no-cli-pager
```

Keep the value in a shell variable, not printed to your terminal history or pasted into chat/logs — `put-parameter`'s own output never echoes the value back, only a version number, which is what you want.

### Make the container pick it up

SSM values are read once, at process startup (`config.py` class attributes) — updating the parameter alone doesn't affect an already-running container. Either:

- Push any commit to `main` (triggers CI, which restarts containers as part of the normal deploy), or
- Restart directly without a code change:
  ```bash
  ssh -i ~/Downloads/stockbot-mumbai.pem ubuntu@13.203.141.195 "cd /opt/stockbot && sudo docker compose restart api"
  ```

If you rotated `API_SECRET_KEY` specifically, also log out and back in on the frontend afterward — the old value is cached in the browser's `localStorage` and will 401 until you paste in the new one.

## Verifying a deploy actually worked

```bash
# Public, no auth needed:
curl -s https://jarvis.mytechexp.com/api/health

# Authenticated (replace <key> — don't paste the real value into chat/shared logs):
curl -s -H "X-API-Key: <key>" https://jarvis.mytechexp.com/api/auth/status

# From inside the box, see what's actually running and since when:
ssh -i ~/Downloads/stockbot-mumbai.pem ubuntu@13.203.141.195 "cd /opt/stockbot && sudo docker compose ps"
```

`/api/health`'s `"status":"ok"` only proves the process started and the scheduler is alive — it does **not** prove your specific change works correctly (see `docs/TRADING_LOGIC.md` and `.claude/skills/deploy-check` for exercising trading-path changes specifically). For anything touching the auto-trade path, also check back after the next `job_intraday_scan` tick (every 15 min, 09:15–15:15 IST, Mon–Fri) rather than trusting a green health check alone.

## Troubleshooting quick reference

| Symptom | Likely cause | Fix |
|---|---|---|
| CI fails at "Deploy via SSH", `git pull`/build never seem to run | EC2 instance is stopped | Start it, then re-run the job or deploy manually (above) |
| `ParameterNotFound` checking SSM from `ap-south-1` | Wrong region — secrets live in `eu-north-1` | Always pass `--region eu-north-1` for `/stockbot/*` params |
| Frontend shows an auth/API-key error right after a key rotation | Browser `localStorage` still has the old key | Log out, log back in with the new key |
| `ModuleNotFoundError: No module named 'ta'` running `uvicorn` **locally** on your Mac | Wrong/base conda env active, unrelated to the Docker image | `pip install ta` in whichever env you intend to run locally, or just test via Docker instead |
| `docker compose` says "no configuration file provided" over SSH | Forgot `cd /opt/stockbot` before the command | Always `cd /opt/stockbot &&` first — SSH doesn't preserve a working directory across `-i`-only one-liners |
