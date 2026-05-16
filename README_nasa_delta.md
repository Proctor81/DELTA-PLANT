# NASA DeltaPlant Module

NASA DeltaPlant extends the DELTA Plant repository with a web-first agronomic monitoring stack that fuses:

- NASA POWER daily climate indicators
- Copernicus Sentinel-1 SAR acquisitions
- SAR preprocessing and decomposition products
- Procedural agronomic diagnosis
- Optional consent-gated LLM narratives
- Runtime-only PDF delivery and optional voice synthesis

## Main entrypoints

- FastAPI app: `api/main.py`
- Core orchestration: `nasa_delta_plant/orchestrator_node.py`
- Area diagnosis and crop wizard: `nasa_delta_plant/area_diagnosis.py`
- Privacy and consent services: `nasa_delta_plant/privacy/`
- Public hero page: `website/nasa-monitor.html`

## Environment variables

The NASA module uses the project root `.env` and `.env.example`.

Required keys:

- `EARTHDATA_USERNAME`
- `EARTHDATA_PASSWORD`
- `EARTHDATA_BASE_URL`
- `COPERNICUS_USERNAME`
- `COPERNICUS_PASSWORD`
- `COPERNICUS_BASE_URL`
- `NASA_POWER_BASE_URL`
- `SECRET_KEY`
- `JWT_ALGORITHM`
- `PDF_TEMP_DIR`

Optional runtime keys:

- `REDIS_URL` for distributed LLM quota tracking
- existing DELTA voice and Hugging Face keys already used elsewhere in the repository

## API surface

Core analysis endpoints:

- `POST /api/nisar/area-analysis`
- `POST /api/nisar/crop-question`
- `POST /api/nisar/voice`
- `GET /api/nisar/pdf/{token}`

Privacy endpoints:

- `POST /api/privacy/consent`
- `GET /api/privacy/consent-status`
- `GET /api/privacy/export/{user_token}`
- `DELETE /api/privacy/delete/{user_token}`

Cookie endpoints:

- `GET /api/cookies/preferences`
- `POST /api/cookies/accept-all`
- `POST /api/cookies/reject-all`

## Security model

- JWT session cookie issued automatically by FastAPI middleware
- CSRF cookie required for state-changing privacy and cookie routes
- SameSite strict cookies
- prompt-injection stripping and text sanitization before analysis / LLM submission
- encrypted consent storage via Fernet
- rotating GDPR audit logs retained for 30 days
- runtime-only PDF tokens with 60 minute expiry

## Website publishing

GitHub Pages is driven by `.github/workflows/deploy-landing-page.yml`.

The workflow now publishes:

- `website/nasa-monitor.html` as the root `index.html`
- `website/nasa-monitor.html` also as `/nasa-monitor.html`
- `website/Raspberrypi/index.html`
- legal pages and `website/components/*.js`

The public site now defaults to `https://api.deltaplant.ai` as the backend base for the NASA monitor. If that host is not yet reachable, the website stays usable in browser demo mode and automatically switches to the live backend once the subdomain comes online.

## Backend deployment path

Repository-side deployment assets now included:

- [Dockerfile](Dockerfile) for the FastAPI service
- [render.yaml](render.yaml) for a Render Blueprint deployment

Recommended live topology:

- `https://deltaplant.ai/` for the GitHub Pages frontend
- `https://api.deltaplant.ai/` for the FastAPI backend

This same-site subdomain layout matters because the frontend relies on shared cookies for CSRF and consent state. A provider default hostname on another registrable domain is not enough for the secure cookie model used by the current implementation.

## Notes on SAR processing

- Sentinel-1 is the primary SAR source in the current implementation.
- Earthdata support is prepared for future NISAR-oriented upgrades.
- SAFE parsing expects `tifffile` to be available.
- Ordinary kriging uses `pykrige` when available and falls back to inverse-distance weighting.

## Local run

1. Install dependencies from `requirements.txt` in the project virtual environment.
2. Ensure `.env` contains the NASA and Copernicus credentials.
3. Start the API:

   `uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload`

4. Open the website locally or via GitHub Pages and use the root monitor page.