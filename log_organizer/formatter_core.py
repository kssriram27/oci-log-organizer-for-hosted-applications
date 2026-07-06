import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOG_TIMESTAMP_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[,.]\d{3,6})?(?:Z|[+-]\d{2}:?\d{2})?)\s+(?P<message>.*)$"
)
REVISION_SUFFIX_RE = re.compile(r"-(?P<suffix>\d+)$")


@dataclass
class FormatOptions:
    output_format: str = "text"
    sort_by_timestamp: bool = True
    merge_partial_oci_logs: bool = True
    remove_timestamp_from_message: bool = True
    filter_latest_revision: bool = True
    latest_revision_scope: str = "workload"
    selection_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class FormatStats:
    raw_count: int
    filtered_count: int
    merged_count: int
    output_count: int
    selections: dict[str, dict[str, Any]]
    deployment_candidates: dict[str, list[dict[str, Any]]]


@dataclass
class FormatResult:
    rows: list[dict[str, Any]]
    content: str
    stats: FormatStats


def get_nested(obj: Any, path: str, default: Any = None) -> Any:
    current = obj
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def get_label(labels: Any, key: str, default: str = "") -> Any:
    if not isinstance(labels, dict):
        return default
    return labels.get(key, default)


def parse_int(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def ms_to_iso_utc(milliseconds: int | float) -> str:
    try:
        return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return ""


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None

    text = str(value).strip().replace(",", ".")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)

    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def clean_one_line(text: Any) -> str:
    return re.sub(r"[\r\n\t]+", " ", str(text)).strip()


def extract_revision_suffix(revision: Any) -> int | None:
    match = REVISION_SUFFIX_RE.search(str(revision or ""))
    if not match:
        return None
    return parse_int(match.group("suffix"))


def extract_image_digest(container_image: Any) -> str:
    image = str(container_image or "")
    if image.startswith("sha256:"):
        return image
    if "@" not in image:
        return ""
    return image.split("@", 1)[1]


def load_payload(input_path: str | Path) -> Any:
    with open(input_path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("results"), list):
        return payload["data"]["results"]
    if isinstance(payload, list):
        return payload
    return [payload]


def load_records(input_path: str | Path) -> list[dict[str, Any]]:
    return load_records_from_payload(load_payload(input_path))


def extract_raw_entry(record: dict[str, Any], index: int) -> dict[str, Any]:
    data = get_nested(record, "data", record)
    log_content = get_nested(data, "logContent", {})
    content = get_nested(log_content, "data.content", {})
    kubernetes = get_nested(content, "kubernetes", {})
    labels = get_nested(kubernetes, "labels", {})

    message = (
        get_nested(log_content, "data.message")
        or get_nested(content, "log")
        or get_nested(record, "message")
        or get_nested(record, "log")
        or ""
    )

    event_time = (
        get_nested(log_content, "time")
        or get_nested(data, "time")
        or get_nested(record, "time")
        or get_nested(data, "oracle.ingestedtime")
        or get_nested(record, "oracle.ingestedtime")
        or ""
    )

    if not event_time:
        datetime_ms = get_nested(data, "datetime") or get_nested(record, "datetime")
        if isinstance(datetime_ms, (int, float)):
            event_time = ms_to_iso_utc(datetime_ms)

    revision = (
        get_label(labels, "serving.knative.dev/revision")
        or get_label(labels, "service.istio.io/canonical-revision")
        or ""
    )
    configuration_generation = parse_int(
        get_label(labels, "serving.knative.dev/configurationGeneration")
        or get_label(labels, "ome.io/deployment-generation")
    )
    container_image = str(get_nested(kubernetes, "container_image", "") or "")
    container_name = str(get_nested(kubernetes, "container_name", "") or "")
    hosted_application_id = str(get_nested(content, "data.hostedApplicationId", "") or "")
    workload_key = (
        hosted_application_id
        or get_label(labels, "serving.knative.dev/service")
        or get_label(labels, "service.istio.io/canonical-name")
        or get_nested(kubernetes, "namespace_name")
        or get_nested(data, "source")
        or get_nested(record, "source")
        or "__default__"
    )

    return {
        "index": index,
        "message": str(message),
        "event_time": str(event_time),
        "logtag": get_nested(content, "logtag", ""),
        "workload_key": str(workload_key),
        "revision": str(revision),
        "revision_suffix": extract_revision_suffix(revision),
        "configuration_generation": configuration_generation,
        "container_image": container_image,
        "container_name": container_name,
        "image_digest": extract_image_digest(container_image),
        "pod_name": str(get_nested(kubernetes, "pod_name", "") or ""),
    }


def entry_has_deployment_metadata(entry: dict[str, Any]) -> bool:
    return bool(
        entry.get("revision")
        or entry.get("container_image")
        or entry.get("image_digest")
        or entry.get("configuration_generation") is not None
    )


def deployment_identity(entry: dict[str, Any]) -> str:
    return (
        entry.get("revision")
        or entry.get("image_digest")
        or entry.get("container_image")
        or ""
    )


def build_candidate(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "identity": deployment_identity(entry),
        "revision": entry.get("revision", ""),
        "configuration_generation": entry.get("configuration_generation"),
        "revision_suffix": entry.get("revision_suffix"),
        "container_image": entry.get("container_image", ""),
        "container_name": entry.get("container_name", ""),
        "image_digest": entry.get("image_digest", ""),
        "latest_event_time": parse_datetime(entry.get("event_time")),
        "count": 0,
        "first_index": entry.get("index", 0),
        "last_index": entry.get("index", 0),
    }


def update_candidate(candidate: dict[str, Any], entry: dict[str, Any]) -> None:
    event_time = parse_datetime(entry.get("event_time"))
    generation = entry.get("configuration_generation")
    revision_suffix = entry.get("revision_suffix")

    candidate["count"] += 1
    candidate["first_index"] = min(candidate["first_index"], entry.get("index", 0))
    candidate["last_index"] = max(candidate["last_index"], entry.get("index", 0))

    if generation is not None:
        current_generation = candidate.get("configuration_generation")
        if current_generation is None or generation > current_generation:
            candidate["configuration_generation"] = generation

    if revision_suffix is not None:
        current_suffix = candidate.get("revision_suffix")
        if current_suffix is None or revision_suffix > current_suffix:
            candidate["revision_suffix"] = revision_suffix

    if event_time is not None:
        latest_event_time = candidate.get("latest_event_time")
        if latest_event_time is None or event_time > latest_event_time:
            candidate["latest_event_time"] = event_time

    if not candidate.get("container_name") and entry.get("container_name"):
        candidate["container_name"] = entry["container_name"]


def candidate_rank(candidate: dict[str, Any]) -> tuple[Any, ...]:
    generation = candidate.get("configuration_generation")
    revision_suffix = candidate.get("revision_suffix")
    latest_event_time = candidate.get("latest_event_time") or datetime.min.replace(tzinfo=timezone.utc)

    return (
        1 if generation is not None else 0,
        generation if generation is not None else -1,
        1 if revision_suffix is not None else 0,
        revision_suffix if revision_suffix is not None else -1,
        latest_event_time,
        candidate.get("last_index", 0),
    )


def group_entries_for_latest_revision(entries: list[dict[str, Any]], options: FormatOptions) -> dict[str, list[dict[str, Any]]]:
    if options.latest_revision_scope.lower() == "global":
        return {"__global__": [entry for entry in entries if entry_has_deployment_metadata(entry)]}

    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if not entry_has_deployment_metadata(entry):
            continue
        groups.setdefault(entry.get("workload_key") or "__default__", []).append(entry)
    return groups


def select_deployment_candidates(entries: list[dict[str, Any]], options: FormatOptions) -> dict[str, list[dict[str, Any]]]:
    grouped_candidates = {}
    for workload_key, group in group_entries_for_latest_revision(entries, options).items():
        candidates = {}
        for entry in group:
            identity = deployment_identity(entry)
            if not identity:
                continue
            candidate = candidates.setdefault(identity, build_candidate(entry))
            update_candidate(candidate, entry)
        if candidates:
            grouped_candidates[workload_key] = sorted(candidates.values(), key=candidate_rank, reverse=True)
    return grouped_candidates


def select_latest_deployments(entries: list[dict[str, Any]], options: FormatOptions) -> dict[str, dict[str, Any]]:
    return {
        workload_key: candidates[0]
        for workload_key, candidates in select_deployment_candidates(entries, options).items()
        if candidates
    }


def entry_matches_selection(entry: dict[str, Any], selection: dict[str, Any] | None) -> bool:
    if not selection:
        return False
    if selection.get("revision"):
        return entry.get("revision") == selection["revision"]
    if selection.get("image_digest"):
        return entry.get("image_digest") == selection["image_digest"]
    if selection.get("container_image"):
        return entry.get("container_image") == selection["container_image"]
    return False


def json_safe_selection(selection: dict[str, Any]) -> dict[str, Any]:
    safe = dict(selection)
    latest_event_time = safe.get("latest_event_time")
    if isinstance(latest_event_time, datetime):
        safe["latest_event_time"] = latest_event_time.isoformat()
    return safe


def deployment_candidate_stats(
    candidates_by_workload: dict[str, list[dict[str, Any]]],
    selections: dict[str, dict[str, Any]],
    options: FormatOptions,
) -> dict[str, list[dict[str, Any]]]:
    stats = {}
    for workload_key, candidates in candidates_by_workload.items():
        selected_identity = deployment_identity(selections.get(workload_key, {}))
        stats[workload_key] = []
        for candidate in candidates:
            safe = json_safe_selection(candidate)
            is_current = bool(selected_identity and deployment_identity(candidate) == selected_identity)
            safe["is_current"] = is_current
            safe["is_filtered_out"] = bool(options.filter_latest_revision and not is_current)
            stats[workload_key].append(safe)
    return stats


def filter_latest_revision_entries(
    entries: list[dict[str, Any]],
    options: FormatOptions,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    candidates_by_workload = select_deployment_candidates(entries, options)
    if not options.filter_latest_revision:
        return entries, {}, deployment_candidate_stats(candidates_by_workload, {}, options)

    selections = options.selection_overrides or {
        workload_key: candidates[0]
        for workload_key, candidates in candidates_by_workload.items()
        if candidates
    }
    if not selections:
        return entries, {}, deployment_candidate_stats(candidates_by_workload, {}, options)

    filtered = []
    for entry in entries:
        if not entry_has_deployment_metadata(entry):
            filtered.append(entry)
            continue

        workload_key = "__global__" if options.latest_revision_scope.lower() == "global" else entry.get("workload_key")
        selection = selections.get(workload_key or "__default__")
        if entry_matches_selection(entry, selection):
            filtered.append(entry)

    safe_selections = {key: json_safe_selection(value) for key, value in selections.items()}
    return filtered, safe_selections, deployment_candidate_stats(candidates_by_workload, selections, options)


def input_looks_newest_first(entries: list[dict[str, Any]]) -> bool:
    times = [parse_datetime(entry["event_time"]) for entry in entries if parse_datetime(entry["event_time"])]
    if len(times) < 2:
        return False
    return times[0] > times[-1]


def merge_partial_entries(entries: list[dict[str, Any]], options: FormatOptions) -> list[dict[str, Any]]:
    if not options.merge_partial_oci_logs:
        return entries

    ordered_entries = list(reversed(entries)) if input_looks_newest_first(entries) else entries
    merged = []
    buffer = None

    for entry in ordered_entries:
        logtag = entry.get("logtag", "")
        if logtag == "P":
            if buffer is None:
                buffer = dict(entry)
            else:
                buffer["message"] += entry["message"]
            continue

        if buffer is not None:
            buffer["message"] += entry["message"]
            buffer["logtag"] = logtag or "F"
            merged.append(buffer)
            buffer = None
            continue

        merged.append(entry)

    if buffer is not None:
        merged.append(buffer)

    return merged


def extract_timestamp_and_message(entry: dict[str, Any], options: FormatOptions) -> dict[str, Any]:
    raw_message = clean_one_line(entry["message"])
    match = LOG_TIMESTAMP_RE.match(raw_message)

    if match:
        timestamp = match.group("timestamp")
        message = match.group("message") if options.remove_timestamp_from_message else raw_message
    else:
        timestamp = entry["event_time"]
        message = raw_message

    return {
        "timestamp": clean_one_line(timestamp),
        "message": clean_one_line(message),
        "sort_time": parse_datetime(timestamp) or parse_datetime(entry["event_time"]),
    }


def rows_to_content(rows: list[dict[str, Any]], output_format: str) -> str:
    lines = []
    for row in rows:
        if output_format == "jsonl":
            lines.append(
                json.dumps(
                    {
                        "timestamp": row["timestamp"],
                        "message": row["message"],
                    },
                    ensure_ascii=False,
                )
            )
        else:
            lines.append(f"{row['timestamp']} | {row['message']}")
    return "\n".join(lines) + ("\n" if lines else "")


def format_records(records: list[dict[str, Any]], options: FormatOptions | None = None) -> FormatResult:
    options = options or FormatOptions()
    entries = [extract_raw_entry(record, index) for index, record in enumerate(records)]

    raw_count = len(entries)
    entries, selections, deployment_candidates = filter_latest_revision_entries(entries, options)
    filtered_count = len(entries)
    entries = merge_partial_entries(entries, options)
    merged_count = len(entries)

    rows = [
        extract_timestamp_and_message(entry, options)
        for entry in entries
        if clean_one_line(entry.get("message", ""))
    ]

    if options.sort_by_timestamp:
        rows.sort(key=lambda row: row["sort_time"] or datetime.max.replace(tzinfo=timezone.utc))

    content_rows = [
        {
            "timestamp": row["timestamp"],
            "message": row["message"],
            "sort_time": row["sort_time"].isoformat() if isinstance(row["sort_time"], datetime) else None,
        }
        for row in rows
    ]

    stats = FormatStats(
        raw_count=raw_count,
        filtered_count=filtered_count,
        merged_count=merged_count,
        output_count=len(content_rows),
        selections=selections,
        deployment_candidates=deployment_candidates,
    )
    return FormatResult(rows=content_rows, content=rows_to_content(content_rows, options.output_format), stats=stats)


def format_payload(payload: Any, options: FormatOptions | None = None) -> FormatResult:
    return format_records(load_records_from_payload(payload), options)


def stats_to_dict(stats: FormatStats) -> dict[str, Any]:
    return asdict(stats)
