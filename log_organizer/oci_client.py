import configparser
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import oci
from oci.logging import LoggingManagementClient
from oci.loggingsearch import LogSearchClient
from oci.loggingsearch.models import SearchLogsDetails
from oci.pagination import list_call_get_all_results
from oci.exceptions import ServiceError


class OciProviderError(Exception):
    pass


CLI_TIMEOUT_SECONDS = 30


def _expand_path(path: str | None) -> str:
    return str(Path(path or "~/.oci/config").expanduser())


def cli_path() -> str | None:
    found = shutil.which("oci")
    if found:
        return found
    windows_default = Path(r"C:\Program Files (x86)\Oracle\oci_cli\oci.exe")
    if windows_default.exists():
        return str(windows_default)
    return None


def sdk_config(settings: dict[str, Any]) -> dict[str, Any]:
    config = oci.config.from_file(_expand_path(settings.get("config_file")), settings.get("profile") or "DEFAULT")
    if settings.get("region"):
        config["region"] = settings["region"]
    oci.config.validate_config(config)
    return config


def _profiles_from_parser(parser: configparser.ConfigParser) -> list[dict[str, str]]:
    profiles: list[dict[str, str]] = []
    if parser.defaults():
        profiles.append({"name": parser.default_section, "region": parser.defaults().get("region", "")})

    for name in parser.sections():
        profile = parser[name]
        profiles.append({"name": name, "region": profile.get("region", "")})

    return profiles


def list_config_profiles(config_file: str | None) -> list[dict[str, str]]:
    """Return locally configured OCI profiles without loading credentials."""
    path = Path(_expand_path(config_file))
    if not path.is_file():
        raise OciProviderError(f"OCI config file was not found: {path}")

    parser = configparser.ConfigParser(interpolation=None)
    try:
        with path.open("r", encoding="utf-8") as file:
            parser.read_file(file)
    except (OSError, configparser.Error) as exc:
        raise OciProviderError(f"Could not read OCI config file: {exc}") from exc

    profiles = _profiles_from_parser(parser)
    if not profiles:
        raise OciProviderError(f"No OCI profiles were found in: {path}")
    return profiles


def provider_sequence(settings: dict[str, Any]) -> list[str]:
    mode = (settings.get("provider_mode") or "auto").lower()
    if mode == "sdk":
        return ["sdk"]
    if mode == "cli":
        return ["cli"]
    return ["sdk", "cli"]


def _normalize_from_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": data.get("id", ""),
        "name": data.get("display_name") or data.get("displayName") or data.get("name") or "",
        "description": data.get("description") or "",
        "log_type": data.get("log_type") or data.get("logType") or "",
        "is_enabled": data.get("is_enabled", data.get("isEnabled", True)),
        "lifecycle_state": data.get("lifecycle_state") or data.get("lifecycleState") or "",
        "raw": data,
    }


def normalize_log_group(item: Any) -> dict[str, Any]:
    data = item if isinstance(item, dict) else oci.util.to_dict(item)
    return _normalize_from_dict(data)


def normalize_log(item: Any) -> dict[str, Any]:
    data = item if isinstance(item, dict) else oci.util.to_dict(item)
    return _normalize_from_dict(data)


def _cli_base_args(settings: dict[str, Any]) -> list[str]:
    executable = cli_path()
    if not executable:
        raise OciProviderError("OCI CLI is not available on PATH.")

    args = [executable]
    if settings.get("config_file"):
        args.extend(["--config-file", _expand_path(settings.get("config_file"))])
    if settings.get("profile"):
        args.extend(["--profile", settings["profile"]])
    if settings.get("region"):
        args.extend(["--region", settings["region"]])
    return args


def _run_cli(args: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, check=False, timeout=CLI_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise OciProviderError(f"OCI CLI timed out after {CLI_TIMEOUT_SECONDS} seconds.") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"OCI CLI exited with {completed.returncode}."
        raise OciProviderError(detail)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise OciProviderError(f"OCI CLI returned non-JSON output: {exc}") from exc


def _sdk_list_log_groups(settings: dict[str, Any]) -> list[dict[str, Any]]:
    client = LoggingManagementClient(sdk_config(settings))
    response = list_call_get_all_results(client.list_log_groups, settings["compartment_id"])
    return [normalize_log_group(item) for item in response.data]


def _cli_list_log_groups(settings: dict[str, Any]) -> list[dict[str, Any]]:
    args = _cli_base_args(settings) + [
        "logging",
        "log-group",
        "list",
        "--compartment-id",
        settings["compartment_id"],
        "--all",
    ]
    payload = _run_cli(args)
    return [normalize_log_group(item) for item in payload.get("data", [])]


def list_log_groups(settings: dict[str, Any]) -> dict[str, Any]:
    return _with_fallback(settings, _sdk_list_log_groups, _cli_list_log_groups)


def _sdk_list_logs(settings: dict[str, Any], log_group_id: str) -> list[dict[str, Any]]:
    client = LoggingManagementClient(sdk_config(settings))
    response = list_call_get_all_results(client.list_logs, log_group_id)
    return [normalize_log(item) for item in response.data]


def _cli_list_logs(settings: dict[str, Any], log_group_id: str) -> list[dict[str, Any]]:
    args = _cli_base_args(settings) + [
        "logging",
        "log",
        "list",
        "--log-group-id",
        log_group_id,
        "--all",
    ]
    payload = _run_cli(args)
    return [normalize_log(item) for item in payload.get("data", [])]


def list_logs(settings: dict[str, Any], log_group_id: str) -> dict[str, Any]:
    return _with_fallback(settings, lambda s: _sdk_list_logs(s, log_group_id), lambda s: _cli_list_logs(s, log_group_id))


def build_search_query(compartment_id: str, log_group_id: str, log_id: str, search_query: str | None = None) -> str:
    if search_query and search_query.strip():
        return search_query.strip()
    return f'search "{compartment_id}/{log_group_id}/{log_id}"'


def _parse_time(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _sdk_search_logs(settings: dict[str, Any], search_query: str, start_time: str, end_time: str) -> dict[str, Any]:
    client = LogSearchClient(sdk_config(settings))
    details = SearchLogsDetails(
        time_start=_parse_time(start_time),
        time_end=_parse_time(end_time),
        search_query=search_query,
        is_return_field_info=False,
    )

    results = []
    page = None
    while True:
        kwargs: dict[str, Any] = {"limit": 1000}
        if page:
            kwargs["page"] = page
        response = client.search_logs(details, **kwargs)
        data = oci.util.to_dict(response.data)
        results.extend(data.get("results", []))
        page = response.headers.get("opc-next-page")
        if not page:
            break

    return {"results": results}


def _cli_search_logs(settings: dict[str, Any], search_query: str, start_time: str, end_time: str) -> dict[str, Any]:
    args = _cli_base_args(settings) + [
        "logging-search",
        "search-logs",
        "--search-query",
        search_query,
        "--time-start",
        start_time,
        "--time-end",
        end_time,
        "--all",
    ]
    payload = _run_cli(args)
    data = payload.get("data", payload)
    if isinstance(data, dict) and "results" in data:
        return {"results": data["results"]}
    return {"results": []}


def search_logs(settings: dict[str, Any], search_query: str, start_time: str, end_time: str) -> dict[str, Any]:
    return _with_fallback(
        settings,
        lambda s: _sdk_search_logs(s, search_query, start_time, end_time),
        lambda s: _cli_search_logs(s, search_query, start_time, end_time),
    )


def _with_fallback(settings: dict[str, Any], sdk_call: Any, cli_call: Any) -> dict[str, Any]:
    errors = []
    for provider in provider_sequence(settings):
        try:
            data = sdk_call(settings) if provider == "sdk" else cli_call(settings)
            return {"provider": provider, "data": data, "errors": errors}
        except Exception as exc:
            errors.append({"provider": provider, "message": str(exc)})
            if provider == "sdk" and isinstance(exc, ServiceError):
                # Both SDK and CLI would send the same OCI request. Retrying an OCI
                # authorization/not-found response only adds latency and noise.
                break

    raise OciProviderError("All OCI providers failed: " + " | ".join(f"{e['provider']}: {e['message']}" for e in errors))


def check_connection(settings: dict[str, Any], include_log_groups: bool = False) -> dict[str, Any]:
    sdk_ready = False
    sdk_error = ""
    try:
        sdk_config(settings)
        sdk_ready = True
    except Exception as exc:
        sdk_error = str(exc)

    cli_ready = bool(cli_path())
    result = {
        "sdk_ready": sdk_ready,
        "sdk_error": sdk_error,
        "cli_ready": cli_ready,
        "cli_path": cli_path() or "",
        "provider_mode": settings.get("provider_mode", "auto"),
        "remote_ok": None,
        "remote_error": "",
    }

    if settings.get("compartment_id"):
        try:
            groups_result = list_log_groups(settings)
            result["remote_ok"] = True
            if include_log_groups:
                result["log_groups"] = groups_result["data"]
                result["provider"] = groups_result["provider"]
        except Exception as exc:
            result["remote_ok"] = False
            result["remote_error"] = str(exc)

    return result
