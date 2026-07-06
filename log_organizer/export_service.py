import zipfile
from pathlib import Path

from .file_store import EXPORT_DIR, ensure_dirs, resolve_formatted_file, run_stamp


def create_formatted_zip(file_ids: list[str]) -> Path:
    ensure_dirs()
    zip_path = EXPORT_DIR / f"formatted_logs_{run_stamp()}.zip"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_id in file_ids:
            path = resolve_formatted_file(file_id)
            archive.write(path, arcname=path.name)

    return zip_path

