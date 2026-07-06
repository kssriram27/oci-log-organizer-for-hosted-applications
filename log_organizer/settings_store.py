import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
SETTINGS_PATH = CONFIG_DIR / "log_app_settings.json"

DEFAULT_THEME_SELECTIONS: dict[str, str] = {
    "classic": "frosted-light",
    "accent-light": "accent-light-azure",
    "accent-dark": "accent-dark-azure",
}

MAX_SAVED_CHOICES = 20
MAX_SAVED_CONTEXTS = 20
SETTINGS_LOCK = threading.RLock()


DEFAULT_SETTINGS: dict[str, Any] = {
    "config_file": "~/.oci/config",
    "profile": "DEFAULT",
    "region": "",
    "compartment_id": "",
    "region_options": [],
    "compartment_id_options": [],
    "oci_context_history": {},
    "provider_mode": "auto",
    "output_format": "text",
    "sort_by_timestamp": True,
    "merge_partial_oci_logs": True,
    "remove_timestamp_from_message": True,
    "filter_latest_revision": True,
    "latest_revision_scope": "workload",
    "default_time_minutes": 5,
    "selected_log_group_id": "",
    "selected_log_group_name": "",
    "include_raw_in_zip": False,
    "theme": "frosted-light",
    "theme_style": "classic",
    "theme_selection_by_style": DEFAULT_THEME_SELECTIONS,
    "sidebar_collapsed": False,
}


def _default_settings() -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    settings["theme_selection_by_style"] = dict(DEFAULT_THEME_SELECTIONS)
    return settings


def _choice_history(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result[-MAX_SAVED_CHOICES:]


def _with_current_choice(options: list[str], value: Any) -> list[str]:
    current = value.strip() if isinstance(value, str) else ""
    if not current:
        return options
    return [current, *(option for option in options if option != current)][:MAX_SAVED_CHOICES]


def _context_key(config_file: Any, profile: Any) -> str:
    config = str(config_file or "~/.oci/config").strip() or "~/.oci/config"
    name = str(profile or "DEFAULT").strip() or "DEFAULT"
    return f"{config}\n{name}"


def _normalized_context_history(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}

    history: dict[str, dict[str, Any]] = {}
    for key, entry in value.items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            continue
        history[key] = {
            "region_options": _choice_history(entry.get("region_options")),
            "compartment_id_options": _choice_history(entry.get("compartment_id_options")),
            "selected_log_group_id": str(entry.get("selected_log_group_id") or "").strip(),
            "selected_log_group_name": str(entry.get("selected_log_group_name") or "").strip(),
        }
    return dict(list(history.items())[-MAX_SAVED_CONTEXTS:])


def merge_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    source = settings or {}
    merged = _default_settings()
    merged.update(
        {
            key: value
            for key, value in source.items()
            if value is not None and key != "theme_selection_by_style"
        }
    )

    saved_selections = source.get("theme_selection_by_style")
    if isinstance(saved_selections, dict):
        merged["theme_selection_by_style"].update(
            {key: value for key, value in saved_selections.items() if isinstance(value, str) and value}
        )

    active_style = merged.get("theme_style") or "classic"
    active_theme = source.get("theme")
    if isinstance(active_theme, str) and active_theme:
        merged["theme_selection_by_style"].setdefault(active_style, active_theme)
        if "theme_selection_by_style" not in source:
            merged["theme_selection_by_style"][active_style] = active_theme

    if not isinstance(merged.get("theme"), str) or not merged["theme"]:
        merged["theme"] = merged["theme_selection_by_style"].get(active_style, DEFAULT_THEME_SELECTIONS["classic"])

    history = _normalized_context_history(source.get("oci_context_history"))
    key = _context_key(merged.get("config_file"), merged.get("profile"))
    entry = history.get(
        key,
        {
            "region_options": [],
            "compartment_id_options": [],
            "selected_log_group_id": "",
            "selected_log_group_name": "",
        },
    )
    entry["region_options"] = _with_current_choice(entry["region_options"], merged.get("region"))
    entry["compartment_id_options"] = _with_current_choice(entry["compartment_id_options"], merged.get("compartment_id"))
    entry["selected_log_group_id"] = str(merged.get("selected_log_group_id") or "").strip()
    entry["selected_log_group_name"] = str(merged.get("selected_log_group_name") or "").strip()
    history[key] = entry
    history = dict(list(history.items())[-MAX_SAVED_CONTEXTS:])

    merged["oci_context_history"] = history
    merged["region_options"] = entry["region_options"]
    merged["compartment_id_options"] = entry["compartment_id_options"]

    return merged


def load_settings() -> dict[str, Any]:
    with SETTINGS_LOCK:
        if not SETTINGS_PATH.exists():
            return _default_settings()

        with open(SETTINGS_PATH, "r", encoding="utf-8") as file:
            return merge_settings(json.load(file))


def save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    with SETTINGS_LOCK:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        merged = merge_settings(settings)
        temporary_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=CONFIG_DIR,
                prefix=f".{SETTINGS_PATH.name}.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary_path = file.name
                json.dump(merged, file, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, SETTINGS_PATH)
        finally:
            if temporary_path:
                Path(temporary_path).unlink(missing_ok=True)
        return merged
