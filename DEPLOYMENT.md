# Deployment Guide

## API deployment

Recommended production command:

`uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1`

Use a reverse proxy in front of FastAPI to terminate TLS and forward requests securely.

Minimum production expectations:

- HTTPS enabled at the proxy level
- persistent `.env` mounted outside version control
- `requirements.txt` installed in the active virtual environment
- filesystem write access for encrypted consent storage under `data/privacy/`
- filesystem write access for rotating GDPR logs under `logs/privacy/`

Optional production improvements:

- set `REDIS_URL` to share LLM usage quotas across replicas
- pin proxy hostnames to `deltaplant.ai` and `www.deltaplant.ai`
- monitor outbound access to NASA POWER and Copernicus Data Space

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

## Runtime artifacts and retention

- PDFs are not persisted as files and expire after 60 minutes.
- consent snapshots are encrypted and retained for 36 months.
- GDPR audit logs rotate daily and keep 30 days of history.

## Operational checks

After deployment, verify:

1. `GET /api/health` returns `status=ok`.
2. the root page at `https://deltaplant.ai/` loads the NASA monitor.
3. legal pages open correctly.
4. drawing a polygon and running `/api/nisar/area-analysis` returns a JSON payload.
5. voice and LLM remain unavailable until consent is granted.