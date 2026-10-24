"""Saving uploaded files into the storage/ folder."""
from pathlib import Path

from app.core.settings import get_settings


def storage_root() -> Path:
    return get_settings().storage_path


def to_relative(path) -> str:
    """Path relative to storage/, with forward slashes (same on Windows and Linux)."""
    p = Path(path).resolve()
    try:
        return p.relative_to(storage_root().resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def resolve(relative_path: str) -> Path:
    """Turn a stored relative path back into a full path (never leaves storage/)."""
    root = storage_root().resolve()
    full = (root / relative_path).resolve()
    if root != full and root not in full.parents:
        raise ValueError("path escapes the storage folder")
    return full


def inspection_dir(inspection_id: int) -> Path:
    folder = storage_root() / "inspections" / str(inspection_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder
