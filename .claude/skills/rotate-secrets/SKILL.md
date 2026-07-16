---
name: rotate-secrets
description: This skill should be used when the user asks to "rotate a secret", "rotate the API key", "the API_SECRET_KEY leaked", "change the Zerodha password/TOTP", "update a secret in production", or any request to change a credential that's stored in AWS SSM Parameter Store and used by the live deployment.
version: 0.1.0
---

# Rotate a production secret

Jarvis has no `.env` file on the EC2 server — every secret is read from AWS SSM Parameter Store at runtime (`backend/config.py:_aws_param`, `deploy/add-secrets.sh`) via the instance's IAM role. Locally, `.env` takes priority over SSM. Rotating a secret means updating it in **three places**, in this order, or the app will end up authenticated with a stale value in at least one environment.

This skill only prepares commands and instructions — running `aws ssm put-parameter` against production and SSHing into the EC2 box are actions with real blast radius (an active trading system). Confirm with the user before running anything beyond generating the new value; give them the commands to run themselves unless they've explicitly asked for hands-off execution.

## Procedure

1. **Generate the new value.**
   - `API_SECRET_KEY`: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
   - Broker keys/secrets (`KITE_API_KEY`, `KITE_API_SECRET`, `FYERS_APP_ID`, `FYERS_SECRET`): regenerated from the broker's developer console, not locally generatable.
   - `ZERODHA_TOTP_SECRET`: regenerated via Zerodha → My Profile → Security → External TOTP → Reset TOTP (this **invalidates the old seed immediately** — the scheduled 08:30 auto-login (`services/auto_auth_service.py`) will fail until the new seed is in SSM, so do this right before updating SSM, not hours ahead).

2. **Update local `backend/.env`** with the new value (this file is gitignored — never put a real secret in `backend/.env.example`, only placeholders; that exact mistake is what caused the incident documented in `docs/SECURITY.md`).

3. **Push to AWS SSM Parameter Store:**
   ```bash
   aws ssm put-parameter --region eu-north-1 --name /stockbot/<NAME> \
     --value "<new_value>" --type SecureString --overwrite --no-cli-pager
   ```
   Or re-run the full sync script after updating `.env`: `./deploy/add-secrets.sh` (uploads every secret from local `.env`, skipping empty values — safe to re-run, but confirm the user wants *all* current `.env` values pushed, not just the one being rotated, since it's an all-or-nothing script).

4. **Restart the API container so it re-reads SSM** (secrets are read once via class-level attributes at import time, `config.py:40-98` — a running process will not pick up the new value without a restart):
   ```bash
   ssh -i ~/Downloads/stockbot-key.pem ubuntu@<EC2_IP> "cd /opt/stockbot && sudo docker compose restart api"
   ```

5. **If rotating `API_SECRET_KEY` specifically**, the frontend's stored key in `localStorage['jarvis_api_key']` (`frontend/src/api/client.ts`) is now stale — log out via the UI (clears localStorage) and log back in with the new key. Every other client/script holding the old `X-API-Key` header will start getting 401s the moment the container restarts — this is the intended effect of rotation, not a bug to work around.

6. **If the old value was ever committed to git** (check with `git log -p -- <file> | grep <old_value_prefix>` before assuming it wasn't), treat it as permanently burned even after rotation, and separately consider whether `git filter-repo` history rewriting is warranted — that's a distinct, more destructive decision (breaks all existing clones/forks of a public repo) that always needs explicit user sign-off, never do it as a routine part of rotation.

## Verification

After restart, confirm with the user's new key:
```bash
curl -s https://<domain>/api/health   # public, no key needed — confirms container is up
curl -s -H "X-API-Key: <new_key>" https://<domain>/api/auth/status   # confirms new key works
```
A 401 on the second call after using the new key means the SSM push or container restart didn't actually take — check `docker compose logs api` on the EC2 box before assuming the rotation succeeded.
