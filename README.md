# OCI Log Organizer

OCI Log Organizer is a local React and FastAPI application for browsing OCI Logging log groups, selecting logs, formatting their content, and exporting results.

It is designed to use the signed-in user's standard OCI CLI configuration locally. OCI API keys, OCIDs, saved settings, logs, and exports are intentionally excluded from version control.

## Prerequisites

- Node.js 20 or later
- Python 3.11 or later
- An OCI CLI configuration and private key available on the machine that runs the app

## Run locally

```powershell
npm ci
python -m pip install -r requirements.txt
npm run dev
```

Open `http://127.0.0.1:5173`. The development command starts the React client and local API together.

Configure the OCI config-file path, profile, region, and compartment in the **Settings** page. Your choices are written only to `config/log_app_settings.json`, which is ignored by Git. Use `config/log_app_settings.example.json` as the safe template.

## Validate changes

```powershell
python -m unittest discover -s tests -v
npm run typecheck
npm run build
```

The automated checks do not call OCI services and must not require an OCI key or compartment OCID.

## Project layout

- `src/` — React UI
- `backend/` — FastAPI HTTP API
- `log_organizer/` — OCI, formatting, settings, export, and session logic
- `tests/` — backend unit tests
- `scripts/` — local development runner
- `config/log_app_settings.example.json` — non-sensitive settings template

## Git workflow

- Branch features from `Development` using names such as `feature/log-filter` or `fix/profile-loading`.
- Open pull requests into `Development`; GitHub Actions must pass before merge.
- Promote a tested `Development` change to `main` through a release pull request, then create a version tag such as `v0.1.0`.

This project is not suitable for GitHub Pages because the application requires a FastAPI backend and local OCI authentication.
