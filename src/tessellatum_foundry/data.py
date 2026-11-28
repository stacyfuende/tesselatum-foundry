"""Resolve canonical Foundry data from a source checkout or installed distribution."""

from __future__ import annotations

from pathlib import Path
from sysconfig import get_path


def foundry_data_dir(name: str) -> Path:
    """Return a repository or installed share directory for schemas/manifests."""
    if not name or Path(name).is_absolute() or ".." in Path(name).parts:
        raise ValueError("Foundry data directory name must be a safe relative path.")
    # data.py lives at src/tessellatum_foundry/data.py; parents[2] is the
    # repository root (parents[3] is its parent directory).
    source_path = Path(__file__).resolve().parents[2] / name
    installed_path = (
        Path(get_path("data")) / "share" / "tessellatum-foundry" / name
    )
    for candidate in (source_path, installed_path):
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        f"Foundry data directory {name!r} is unavailable in this installation."
    )
