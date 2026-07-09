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

## First-time application setup

No application code changes or manual edits to this repository's settings file are required. After the app is running, complete the setup in the **Settings** page:

1. Open **Settings** from the left navigation (or use **Open Settings** on the home page).
2. In **OCI Connection**, set **Config file** to the local OCI config file. The default, `~/.oci/config`, is normally correct; on Windows it resolves to `C:\Users\<your-user>\.oci\config`.
3. Select the OCI **Profile** that contains the credentials to use. The profile list is read from the selected config file; choose `DEFAULT` if that is your configured profile.
4. Confirm the **Region**. Leave it blank to use the region in the selected OCI profile, or enter an OCI region such as `ap-hyderabad-1` to override it.
5. Set **Compartment OCID** to the compartment that contains the log groups you need to browse.
6. Leave **Provider** set to **Auto** unless you specifically need to use only the OCI Python SDK or only the OCI CLI. Auto tries the SDK first and then the CLI if needed.
7. Select **Save settings**. This also checks the connection and, when successful, loads the available log groups. The **Diagnostics** section shows whether the SDK, CLI, and OCI connection are ready; correct any displayed error before continuing.

Settings are saved locally in `config/log_app_settings.json`, which is ignored by Git. The app does not copy OCI credentials or private keys into the repository.

## Fetch and export logs

Once the OCI connection is ready:

1. Open **Search Logs** and choose a log group. Use the refresh button beside the log-group selector if the list needs reloading.
2. Select one or more logs, choose a UTC time range (or a quick range), then select **Run**. Each selected log is fetched and formatted separately.
3. Review the formatted results in the terminal viewer. Use the download button for one result or the archive button to export all formatted results as a ZIP file.

The **Formatter** settings control whether output is text or JSONL, whether to retain only the latest revision, partial-log merging, timestamp ordering, and message timestamp removal. The default options are suitable for most use cases.

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
