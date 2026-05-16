# Render Free Pilot Runbook

This document captures the temporary one-month DELTA backend pilot on Render Free
and the exact follow-up to move back to Starter.

## Current pilot mode

- backend host: `https://api.deltaplant.ai`
- Render plan: `Free`
- persistent disk: disabled during the pilot
- custom domain: verified and live

## Operational limits during the pilot

- the service can spin down after 15 minutes of inactivity
- the next request can incur a cold start
- local filesystem writes are ephemeral across restart, redeploy, or idle spin-down
- privacy consent storage and GDPR logs are therefore not durable during the pilot

## Monthly live test checks

Run these checks at least weekly during the pilot:

1. run `python3 tools/check_render_free_pilot.py` locally or trigger `.github/workflows/check-render-free-pilot.yml`
2. `https://deltaplant.ai/` shows the live backend banner instead of browser demo mode
3. polygon analysis from the public frontend completes successfully
4. PDF generation works end-to-end
5. Render does not suspend the service for bandwidth or build overages

## Switch back to Starter

When the one-month pilot ends:

1. open the Render service `proctor81-deltaplant-nasa-api`
2. change the instance type from `Free` to `Starter`
3. add a `1 GB` persistent disk mounted at `/var/lib/deltaplant`
4. confirm these env vars still point to the mounted storage:
   - `PDF_TEMP_DIR=/var/lib/deltaplant/tmp`
   - `PRIVACY_STORAGE_PATH=/var/lib/deltaplant/privacy/consents.enc`
   - `PRIVACY_LOG_DIR=/var/lib/deltaplant/logs/privacy`
5. redeploy the current `main` branch
6. verify `https://api.deltaplant.ai/api/health`
7. verify the frontend at `https://deltaplant.ai/` still reports `Live pipeline connected`

## Repository alignment after the switch

After the Render upgrade is complete:

1. restore `plan: starter` in [render.yaml](render.yaml)
2. restore the `disk:` block in [render.yaml](render.yaml)
3. update [DEPLOYMENT.md](DEPLOYMENT.md) to remove the temporary Free pilot note
4. commit and push the repository so the blueprint matches production again