# Deployment Guide

## API deployment

The repository now includes a production-oriented backend container setup:

- [Dockerfile](Dockerfile) for the NASA FastAPI service
- [render.yaml](render.yaml) for the current Render Free pilot rollout

Recommended public topology:

- static frontend on `https://deltaplant.ai/`
- FastAPI backend on `https://api.deltaplant.ai/`

That topology is important because the frontend uses cookies, CSRF, and consent state. A provider default hostname like `*.onrender.com` is a different site and will break the shared-cookie flow unless you deliberately relax the security model. The current implementation is prepared for a same-site subdomain deployment under `*.deltaplant.ai`.

Recommended production command:

`uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1`

Use a reverse proxy in front of FastAPI to terminate TLS and forward requests securely.

Minimum production expectations:

- HTTPS enabled at the proxy level
- persistent `.env` mounted outside version control
- `requirements.txt` installed in the active virtual environment
- filesystem write access for encrypted consent storage via `PRIVACY_STORAGE_PATH`
- filesystem write access for rotating GDPR logs via `PRIVACY_LOG_DIR`
- backend served from a same-site domain such as `api.deltaplant.ai`

Optional production improvements:

- set `REDIS_URL` to share LLM usage quotas across replicas
- pin proxy hostnames to `deltaplant.ai` and `www.deltaplant.ai`
- monitor outbound access to NASA POWER and Copernicus Data Space

## Render deployment

The quickest supported path from this repository is Render via [render.yaml](render.yaml).

Current repository default:

- Render plan: `Free`
- no persistent disk attached during the one-month public test window
- same-site backend still served from `https://api.deltaplant.ai`

Planned post-test upgrade path:

- move the Render web service to `Starter`
- re-enable the `disk:` block in [render.yaml](render.yaml)
- keep `PRIVACY_STORAGE_PATH` and `PRIVACY_LOG_DIR` on `/var/lib/deltaplant`

To print the exact cutover bundle from the local `.env`, including the DNS target and all Render env keys, run:

`/home/proctor81/Desktop/DELTA-PLANT/.venv/bin/python tools/render_cutover_bundle.py`

Add `--reveal-secrets` only when you want the command to print the real secret values from the local environment instead of masked placeholders.

Suggested sequence:

1. Create a new Render Blueprint from this repository.
2. Provision the web service defined in [render.yaml](render.yaml).
3. Set the required secret env vars in Render:
	`EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD`, `COPERNICUS_USERNAME`, `COPERNICUS_PASSWORD`, `SECRET_KEY`, and optionally `REDIS_URL`.
4. Attach the custom domain `api.deltaplant.ai` to that Render service.
5. Create the DNS record for `api.deltaplant.ai` in the `deltaplant.ai` zone.
6. Keep `COOKIE_DOMAIN=.deltaplant.ai` and `COOKIE_SAMESITE=strict` so the frontend and backend remain same-site.

Expected Render default hostname after service creation:

- `proctor81-deltaplant-nasa-api.onrender.com`

Exact DNS record to create in Aruba for the subdomain:

- type: `CNAME`
- host/name: `api`
- target/value: `proctor81-deltaplant-nasa-api.onrender.com`
- ttl: default Aruba value or `3600`

The frontend is already prepared to probe `https://api.deltaplant.ai` by default and will fall back to browser demo mode until the subdomain becomes reachable.

## GitHub Pages deployment

The website is deployed through `.github/workflows/deploy-landing-page.yml`.

Published output now includes:

- root hero page from `website/nasa-monitor.html`
- legal pages from `website/privacy-policy.html`, `website/cookie-policy.html`, and `website/terms-of-service.html`
- consent helper scripts from `website/components/`
- Raspberry Pi landing page under `website/Raspberrypi/`

To publish website changes:

1. Commit updates touching the `website/` folder or the Pages workflow.
2. Push to `main`.
3. Wait for the Pages action to publish the `site-dist/` bundle to `gh-pages`.

The public NASA monitor now defaults to `https://api.deltaplant.ai` as its backend target. Until that host is live, it automatically stays in browser demo mode.

## Runtime artifacts and retention

- PDFs are not persisted as files and expire after 60 minutes.
- consent snapshots are encrypted and retained for 36 months.
- GDPR audit logs rotate daily and keep 30 days of history.
- during the temporary `Free` pilot, consent and privacy logs live on ephemeral container storage and are not durable across restarts, redeploys, or idle spin-down events.

## Operational checks

After deployment, verify:

1. `GET /api/health` returns `status=ok`.
2. the root page at `https://deltaplant.ai/` loads the NASA monitor.
3. legal pages open correctly.
4. `https://api.deltaplant.ai/api/health` responds over HTTPS.
5. drawing a polygon on `https://deltaplant.ai/` and running `/api/nisar/area-analysis` returns a JSON payload from the live backend instead of the browser demo fallback.
6. voice and LLM remain unavailable until consent is granted.