"""Input adapters. Thin by design: they only normalise into the model."""

from __future__ import annotations

from pathlib import Path

from ..model import Project
from . import csv_dict, odm

__all__ = ["csv_dict", "odm", "load_project"]


def load_project(path: str | Path) -> Project:
    """Dispatch on file extension."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".xml":
        return odm.load(path)
    if suffix in {".csv", ".tsv", ".txt"}:
        return csv_dict.load(path)
    raise ValueError(f"{path}: unsupported input (expected .xml or .csv)")
