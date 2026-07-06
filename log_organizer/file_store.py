import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT_DIR / "Input_Logs"
FORMATTED_DIR = ROOT_DIR / "Formatted_Logs"
EXPORT_DIR = ROOT_DIR / "Exports"


def ensure_dirs() -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    FORMATTED_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def safe_slug(value: str, fallback: str = "log") -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    slug = re.sub(r"_+", "_", slug).strip("_.-")
    return slug[:120] or fallback


def timestamp_slug(value: str) -> str:
    return safe_slug(value.replace(":", "-"), "time")


def run_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_base_name(log_name: str, start_time: str, end_time: str) -> str:
    return f"{safe_slug(log_name)}_{timestamp_slug(start_time)}_to_{timestamp_slug(end_time)}_{run_stamp()}"


def write_raw_payload(payload: Any, log_name: str, start_time: str, end_time: str) -> Path:
    ensure_dirs()
    path = INPUT_DIR / f"{build_base_name(log_name, start_time, end_time)}.json"
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return path


def write_formatted_content(content: str, log_name: str, start_time: str, end_time: str, output_format: str) -> Path:
    ensure_dirs()
    extension = ".jsonl" if output_format == "jsonl" else ".txt"
    path = FORMATTED_DIR / f"{build_base_name(log_name, start_time, end_time)}{extension}"
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)
    return path


def resolve_formatted_file(file_id: str) -> Path:
    candidate = FORMATTED_DIR / Path(file_id).name
    resolved = candidate.resolve()
    if not str(resolved).lower().startswith(str(FORMATTED_DIR.resolve()).lower()) or not resolved.exists():
        raise FileNotFoundError(file_id)
    return resolved

