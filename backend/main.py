from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from log_organizer.formatter_core import FormatOptions, format_records, load_records_from_payload
from log_organizer.oci_client import OciProviderError, build_search_query, check_connection, list_config_profiles, list_log_groups, list_logs, search_logs
from log_organizer.session_store import SessionNotFoundError, SessionResultNotFoundError, session_store
from log_organizer.settings_store import load_settings, save_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    session_store.cleanup_orphaned_temp_dirs()
    yield
    for session_id in list(session_store.sessions):
        session_store.close_session(session_id)


app = FastAPI(title="OCI Log Organizer", version="1.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


ProviderMode = Literal["auto", "sdk", "cli"]
OutputFormat = Literal["text", "jsonl"]
RevisionScope = Literal["workload", "global"]
RunMode = Literal["manual", "live"]
LiveDecision = Literal["switch", "keep"]
MAX_CONCURRENT_LOG_SEARCHES = 3


class SettingsModel(BaseModel):
    config_file: str = "~/.oci/config"
    profile: str = "DEFAULT"
    region: str = ""
    compartment_id: str = ""
    region_options: list[str] = Field(default_factory=list)
    compartment_id_options: list[str] = Field(default_factory=list)
    oci_context_history: dict[str, dict[str, Any]] = Field(default_factory=dict)
    provider_mode: ProviderMode = "auto"
    output_format: OutputFormat = "text"
    sort_by_timestamp: bool = True
    merge_partial_oci_logs: bool = True
    remove_timestamp_from_message: bool = True
    filter_latest_revision: bool = True
    latest_revision_scope: RevisionScope = "workload"
    default_time_minutes: int = 5
    selected_log_group_id: str = ""
    selected_log_group_name: str = ""
    include_raw_in_zip: bool = False
    theme: str = "frosted-light"
    theme_style: str = "classic"
    theme_selection_by_style: dict[str, str] = Field(default_factory=dict)
    sidebar_collapsed: bool = False


class LogSelection(BaseModel):
    id: str
    name: str


class LogLookupRequest(BaseModel):
    log_group_id: str
    settings: SettingsModel | None = None


class FetchFormatRequest(BaseModel):
    session_id: str
    settings: SettingsModel | None = None
    log_group_id: str
    log_group_name: str = ""
    logs: list[LogSelection] = Field(default_factory=list)
    start_time: str
    end_time: str
    mode: RunMode = "manual"
    live_decision: LiveDecision | None = None


class ExportZipRequest(BaseModel):
    session_id: str
    result_ids: list[str] = Field(default_factory=list)


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def runtime_settings(settings: SettingsModel | None = None) -> dict[str, Any]:
    saved = load_settings()
    if settings is not None:
        saved.update(model_to_dict(settings))
    return saved


def format_options_from_settings(settings: dict[str, Any]) -> FormatOptions:
    return FormatOptions(
        output_format=settings.get("output_format", "text"),
        sort_by_timestamp=bool(settings.get("sort_by_timestamp", True)),
        merge_partial_oci_logs=bool(settings.get("merge_partial_oci_logs", True)),
        remove_timestamp_from_message=bool(settings.get("remove_timestamp_from_message", True)),
        filter_latest_revision=bool(settings.get("filter_latest_revision", True)),
        latest_revision_scope=settings.get("latest_revision_scope", "workload"),
    )


def selection_identity(selection: dict[str, Any] | None) -> str:
    if not selection:
        return ""
    return str(selection.get("revision") or selection.get("image_digest") or selection.get("container_image") or "")


def revision_changes(
    current: dict[str, dict[str, Any]],
    latest: dict[str, dict[str, Any]],
    acknowledged: dict[str, str],
) -> list[dict[str, Any]]:
    changes = []
    for workload, candidate in latest.items():
        candidate_id = selection_identity(candidate)
        current_id = selection_identity(current.get(workload))
        if candidate_id and candidate_id != current_id and acknowledged.get(workload) != candidate_id:
            changes.append({"workload": workload, "current": current.get(workload, {}), "candidate": candidate})
    return changes


def session_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (SessionNotFoundError, SessionResultNotFoundError)):
        return HTTPException(status_code=404, detail="This log session has ended. Run the search again.")
    return HTTPException(status_code=500, detail=str(exc))


def oci_context(settings: dict[str, Any]) -> dict[str, str]:
    return {
        "profile": str(settings.get("profile", "")),
        "region": str(settings.get("region", "")),
        "compartment_id": str(settings.get("compartment_id", "")),
    }


def load_log_groups_for_settings(settings: dict[str, Any]) -> dict[str, Any]:
    if not settings.get("compartment_id"):
        raise HTTPException(status_code=400, detail="Compartment OCID is required.")
    try:
        result = list_log_groups(settings)
        result["connection_context"] = oci_context(settings)
        return result
    except OciProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def load_logs_for_settings(settings: dict[str, Any], log_group_id: str) -> dict[str, Any]:
    if not log_group_id:
        raise HTTPException(status_code=400, detail="Log group OCID is required.")
    try:
        result = list_logs(settings, log_group_id)
        result["connection_context"] = oci_context(settings)
        return result
    except OciProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    return load_settings()


@app.put("/api/settings")
def put_settings(settings: SettingsModel) -> dict[str, Any]:
    return save_settings(model_to_dict(settings))


@app.get("/api/oci/config-profiles")
def get_config_profiles(config_file: str | None = None) -> dict[str, Any]:
    selected_path = config_file if config_file is not None else load_settings().get("config_file")
    try:
        return {"profiles": list_config_profiles(selected_path)}
    except OciProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/oci/check")
def post_oci_check(settings: SettingsModel | None = None) -> dict[str, Any]:
    return check_connection(runtime_settings(settings), include_log_groups=True)


@app.get("/api/oci/log-groups")
def get_log_groups(compartment_id: str | None = None) -> dict[str, Any]:
    settings = runtime_settings()
    if compartment_id:
        settings["compartment_id"] = compartment_id
    return load_log_groups_for_settings(settings)


@app.post("/api/oci/log-groups")
def post_log_groups(settings: SettingsModel) -> dict[str, Any]:
    return load_log_groups_for_settings(runtime_settings(settings))


@app.get("/api/oci/logs")
def get_logs(log_group_id: str) -> dict[str, Any]:
    return load_logs_for_settings(runtime_settings(), log_group_id)


@app.post("/api/oci/logs")
def post_logs(request: LogLookupRequest) -> dict[str, Any]:
    return load_logs_for_settings(runtime_settings(request.settings), request.log_group_id)


@app.post("/api/sessions")
def create_session() -> dict[str, str]:
    session = session_store.create_session()
    return {"session_id": session.session_id}


@app.post("/api/sessions/{session_id}/heartbeat")
def heartbeat(session_id: str) -> dict[str, str]:
    try:
        session_store.touch(session_id)
    except Exception as exc:
        raise session_error(exc) from exc
    return {"status": "ok"}


@app.post("/api/sessions/{session_id}/close")
def close_session(session_id: str) -> dict[str, str]:
    session_store.close_session(session_id)
    return {"status": "closed"}


@app.delete("/api/sessions/{session_id}/results")
def clear_session_results(session_id: str) -> dict[str, str]:
    try:
        session_store.clear_results(session_id)
    except Exception as exc:
        raise session_error(exc) from exc
    return {"status": "cleared"}


@app.get("/api/sessions/{session_id}/results/{result_id}/lines")
def get_result_lines(
    session_id: str,
    result_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=500),
    query: str = "",
) -> dict[str, Any]:
    try:
        return session_store.paged_lines(session_id, result_id, offset, limit, query)
    except Exception as exc:
        raise session_error(exc) from exc


@app.get("/api/sessions/{session_id}/results/{result_id}/content")
def get_result_content(session_id: str, result_id: str) -> PlainTextResponse:
    try:
        content = session_store.get_content(session_id, result_id)
    except Exception as exc:
        raise session_error(exc) from exc
    return PlainTextResponse(content)


@app.get("/api/sessions/{session_id}/results/{result_id}/download", response_model=None)
def download_result(session_id: str, result_id: str) -> FileResponse | PlainTextResponse:
    try:
        path, content, filename = session_store.get_download_source(session_id, result_id)
    except Exception as exc:
        raise session_error(exc) from exc
    if path is not None and path.exists():
        return FileResponse(path, filename=filename)
    return PlainTextResponse(content or "", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.post("/api/logs/fetch-format")
def post_fetch_format(request: FetchFormatRequest) -> dict[str, Any]:
    if not request.logs:
        raise HTTPException(status_code=400, detail="Select at least one log.")
    try:
        session_store.touch(request.session_id)
        if request.mode == "manual":
            session_store.clear_results(request.session_id)
    except Exception as exc:
        raise session_error(exc) from exc

    settings = runtime_settings(request.settings)
    options = format_options_from_settings(settings)
    results = []
    all_changes = []

    def fetch_selected_log(selected_log: LogSelection) -> dict[str, Any]:
        query = build_search_query(settings.get("compartment_id", ""), request.log_group_id, selected_log.id)
        return search_logs(settings, query, request.start_time, request.end_time)

    worker_count = min(MAX_CONCURRENT_LOG_SEARCHES, len(request.logs))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        fetches = [(selected_log, executor.submit(fetch_selected_log, selected_log)) for selected_log in request.logs]

        for selected_log, fetch in fetches:
            try:
                fetched = fetch.result()
                incoming_records = load_records_from_payload(fetched["data"])
                existing = session_store.find_result_by_log(request.session_id, selected_log.id)
                is_live_update = request.mode == "live" and existing is not None
                current_records = session_store.get_records(request.session_id, existing.result_id) if existing else []
                records, added_count = (
                    session_store.merge_records(current_records, incoming_records)
                    if request.mode == "live"
                    else (incoming_records, len(incoming_records))
                )

                latest_format = format_records(records, options)
                latest_selections = latest_format.stats.selections
                locks = existing.revision_locks if existing else {}
                acknowledged = existing.acknowledged_revisions if existing else {}

                if request.mode == "live" and options.filter_latest_revision:
                    if request.live_decision == "switch":
                        locks = latest_selections
                        acknowledged = {}
                    elif request.live_decision == "keep":
                        for change in revision_changes(locks, latest_selections, acknowledged):
                            acknowledged[change["workload"]] = selection_identity(change["candidate"])
                    elif not locks:
                        locks = latest_selections
                else:
                    locks = {}
                    acknowledged = {}

                formatted = format_records(records, replace(options, selection_overrides=locks) if locks else options)
                stored = session_store.store_result(
                    request.session_id,
                    log_id=selected_log.id,
                    log_name=selected_log.name,
                    output_format=options.output_format,
                    provider=fetched["provider"],
                    provider_errors=fetched.get("errors", []),
                    stats={**formatted.stats.__dict__, "live_added_count": added_count if is_live_update else None},
                    raw_records=records,
                    formatted_content=formatted.content,
                    revision_locks=locks,
                    acknowledged_revisions=acknowledged,
                )
                results.append(session_store.result_summary(stored))

                if request.mode == "live" and options.filter_latest_revision and not request.live_decision:
                    changes = revision_changes(locks, latest_selections, acknowledged)
                    if changes:
                        all_changes.append({"result_id": stored.result_id, "log_name": stored.log_name, "changes": changes})
            except Exception as exc:
                results.append({"status": "error", "log_id": selected_log.id, "log_name": selected_log.name, "message": str(exc)})

    return {"results": results, "revision_changes": all_changes}


@app.post("/api/files/export-zip")
def post_export_zip(request: ExportZipRequest, background_tasks: BackgroundTasks) -> FileResponse:
    if not request.result_ids:
        raise HTTPException(status_code=400, detail="No formatted files are available to export.")
    try:
        path = session_store.create_zip(request.session_id, request.result_ids)
    except Exception as exc:
        raise session_error(exc) from exc
    background_tasks.add_task(Path.unlink, path, missing_ok=True)
    return FileResponse(path, filename="formatted_logs.zip", media_type="application/zip", background=background_tasks)
