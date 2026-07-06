"""Ephemeral, session-scoped storage for OCI log runs."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import threading
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


MAX_MEMORY_BYTES = 20 * 1024 * 1024
SESSION_TTL = timedelta(minutes=10)
TEMP_ROOT = Path(tempfile.gettempdir()) / "oci-log-organizer"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def safe_filename(value: str, fallback: str = "log") -> str:
    cleaned = "".join(character if character.isalnum() or character in "._-" else "_" for character in value.strip())
    cleaned = cleaned.strip("._-")
    return cleaned[:100] or fallback


def nested_value(value: Any, path: tuple[str, ...], default: Any = "") -> Any:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current


def record_signature(record: Any) -> str:
    entry_id = nested_value(record, ("data", "logContent", "id"))
    if entry_id:
        return f"oci:{entry_id}"

    identity = {
        "datetime": nested_value(record, ("data", "datetime")),
        "event_time": nested_value(record, ("data", "logContent", "data", "time")),
        "message": nested_value(record, ("data", "logContent", "data", "message"))
        or nested_value(record, ("data", "logContent", "data", "content", "log")),
        "pod": nested_value(record, ("data", "logContent", "data", "content", "kubernetes", "pod_name")),
        "revision": nested_value(
            record,
            ("data", "logContent", "data", "content", "kubernetes", "labels", "serving.knative.dev/revision"),
        ),
    }
    encoded = json.dumps(identity, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return f"fallback:{hashlib.sha256(encoded).hexdigest()}"


@dataclass
class SessionResult:
    result_id: str
    log_id: str
    log_name: str
    output_format: str
    provider: str = ""
    provider_errors: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    raw_records: list[dict[str, Any]] | None = field(default_factory=list)
    formatted_content: str | None = ""
    raw_path: Path | None = None
    formatted_path: Path | None = None
    revision_locks: dict[str, dict[str, Any]] = field(default_factory=dict)
    acknowledged_revisions: dict[str, str] = field(default_factory=dict)


@dataclass
class LogSession:
    session_id: str
    created_at: datetime = field(default_factory=utcnow)
    last_seen: datetime = field(default_factory=utcnow)
    results: dict[str, SessionResult] = field(default_factory=dict)
    disk_backed: bool = False


class SessionNotFoundError(KeyError):
    pass


class SessionResultNotFoundError(KeyError):
    pass


class SessionStore:
    """Keeps active log runs in memory until the session exceeds the quota."""

    def __init__(self, temp_root: Path = TEMP_ROOT, memory_limit: int = MAX_MEMORY_BYTES) -> None:
        self.temp_root = temp_root
        self.memory_limit = memory_limit
        self.sessions: dict[str, LogSession] = {}
        self.lock = threading.RLock()

    def cleanup_orphaned_temp_dirs(self) -> None:
        with self.lock:
            if not self.temp_root.exists():
                return
            for path in self.temp_root.iterdir():
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)

    def create_session(self) -> LogSession:
        with self.lock:
            self.cleanup_expired()
            session = LogSession(session_id=uuid.uuid4().hex)
            self.sessions[session.session_id] = session
            return session

    def close_session(self, session_id: str) -> None:
        with self.lock:
            session = self.sessions.pop(session_id, None)
            if session is not None:
                shutil.rmtree(self._session_dir(session_id), ignore_errors=True)

    def cleanup_expired(self) -> int:
        with self.lock:
            cutoff = utcnow() - SESSION_TTL
            expired = [session_id for session_id, session in self.sessions.items() if session.last_seen < cutoff]
            for session_id in expired:
                self.close_session(session_id)
            return len(expired)

    def touch(self, session_id: str) -> LogSession:
        with self.lock:
            self.cleanup_expired()
            session = self.sessions.get(session_id)
            if session is None:
                raise SessionNotFoundError(session_id)
            session.last_seen = utcnow()
            return session

    def clear_results(self, session_id: str) -> None:
        with self.lock:
            session = self.touch(session_id)
            for result in session.results.values():
                self._remove_result_files(result)
            session.results.clear()
            session.disk_backed = False
            shutil.rmtree(self._session_dir(session_id), ignore_errors=True)

    def find_result_by_log(self, session_id: str, log_id: str) -> SessionResult | None:
        session = self.touch(session_id)
        return next((result for result in session.results.values() if result.log_id == log_id), None)

    def store_result(
        self,
        session_id: str,
        *,
        log_id: str,
        log_name: str,
        output_format: str,
        provider: str,
        provider_errors: list[dict[str, Any]],
        stats: dict[str, Any],
        raw_records: list[dict[str, Any]],
        formatted_content: str,
        revision_locks: dict[str, dict[str, Any]] | None = None,
        acknowledged_revisions: dict[str, str] | None = None,
    ) -> SessionResult:
        with self.lock:
            session = self.touch(session_id)
            result = self.find_result_by_log(session_id, log_id)
            if result is None:
                result = SessionResult(
                    result_id=uuid.uuid4().hex,
                    log_id=log_id,
                    log_name=log_name,
                    output_format=output_format,
                )
                session.results[result.result_id] = result

            result.log_name = log_name
            result.output_format = output_format
            result.provider = provider
            result.provider_errors = provider_errors
            result.stats = stats
            result.raw_records = raw_records
            result.formatted_content = formatted_content
            result.revision_locks = revision_locks or {}
            result.acknowledged_revisions = acknowledged_revisions or {}

            if session.disk_backed or self._session_memory_bytes(session) > self.memory_limit:
                session.disk_backed = True
                self._spill_session(session)
            return result

    def get_records(self, session_id: str, result_id: str) -> list[dict[str, Any]]:
        with self.lock:
            result = self.get_result(session_id, result_id)
            if result.raw_records is not None:
                return list(result.raw_records)
            if result.raw_path is None or not result.raw_path.exists():
                return []
            with result.raw_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            return payload if isinstance(payload, list) else []

    def get_content(self, session_id: str, result_id: str) -> str:
        with self.lock:
            result = self.get_result(session_id, result_id)
            if result.formatted_content is not None:
                return result.formatted_content
            if result.formatted_path is None or not result.formatted_path.exists():
                return ""
            return result.formatted_path.read_text(encoding="utf-8")

    def get_result(self, session_id: str, result_id: str) -> SessionResult:
        session = self.touch(session_id)
        result = session.results.get(result_id)
        if result is None:
            raise SessionResultNotFoundError(result_id)
        return result

    def list_result_summaries(self, session_id: str) -> list[dict[str, Any]]:
        session = self.touch(session_id)
        return [self.result_summary(result) for result in session.results.values()]

    def result_summary(self, result: SessionResult) -> dict[str, Any]:
        return {
            "status": "success",
            "result_id": result.result_id,
            "log_id": result.log_id,
            "log_name": result.log_name,
            "provider": result.provider,
            "provider_errors": result.provider_errors,
            "stats": result.stats,
            "output_format": result.output_format,
        }

    def paged_lines(self, session_id: str, result_id: str, offset: int, limit: int, query: str = "") -> dict[str, Any]:
        content = self.get_content(session_id, result_id)
        lines = content.splitlines()
        if query.strip():
            needle = query.casefold()
            lines = [line for line in lines if needle in line.casefold()]
        offset = max(offset, 0)
        limit = min(max(limit, 1), 500)
        return {
            "lines": lines[offset : offset + limit],
            "total": len(lines),
            "offset": offset,
            "limit": limit,
        }

    def get_download_source(self, session_id: str, result_id: str) -> tuple[Path | None, str | None, str]:
        with self.lock:
            result = self.get_result(session_id, result_id)
            extension = ".jsonl" if result.output_format == "jsonl" else ".txt"
            filename = f"{safe_filename(result.log_name)}{extension}"
            return result.formatted_path, result.formatted_content, filename

    def create_zip(self, session_id: str, result_ids: list[str]) -> Path:
        with self.lock:
            session = self.touch(session_id)
            session_dir = self._session_dir(session.session_id)
            session_dir.mkdir(parents=True, exist_ok=True)
            path = session_dir / f"formatted_logs_{uuid.uuid4().hex}.zip"
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for result_id in result_ids:
                    source, content, filename = self.get_download_source(session_id, result_id)
                    if source is not None and source.exists():
                        archive.write(source, arcname=filename)
                    elif content is not None:
                        archive.writestr(filename, content)
            return path

    def merge_records(self, existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        seen = {record_signature(record) for record in existing}
        merged = list(existing)
        added = 0
        for record in incoming:
            signature = record_signature(record)
            if signature in seen:
                continue
            seen.add(signature)
            merged.append(record)
            added += 1
        return merged, added

    def _session_dir(self, session_id: str) -> Path:
        return self.temp_root / session_id

    def _session_memory_bytes(self, session: LogSession) -> int:
        total = 0
        for result in session.results.values():
            if result.raw_records is not None:
                total += len(json.dumps(result.raw_records, ensure_ascii=False, default=str).encode("utf-8"))
            if result.formatted_content is not None:
                total += len(result.formatted_content.encode("utf-8"))
        return total

    def _spill_session(self, session: LogSession) -> None:
        directory = self._session_dir(session.session_id)
        directory.mkdir(parents=True, exist_ok=True)
        for result in session.results.values():
            raw_path = directory / f"{result.result_id}.raw.json"
            formatted_path = directory / f"{result.result_id}.{ 'jsonl' if result.output_format == 'jsonl' else 'txt' }"
            if result.raw_records is not None:
                raw_path.write_text(json.dumps(result.raw_records, ensure_ascii=False), encoding="utf-8")
                result.raw_records = None
            if result.formatted_content is not None:
                formatted_path.write_text(result.formatted_content, encoding="utf-8")
                result.formatted_content = None
            result.raw_path = raw_path
            result.formatted_path = formatted_path

    def _remove_result_files(self, result: SessionResult) -> None:
        for path in (result.raw_path, result.formatted_path):
            if path is not None:
                path.unlink(missing_ok=True)


session_store = SessionStore()
