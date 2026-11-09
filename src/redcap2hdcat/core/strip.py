"""Remove ClinicalData from a Project XML export, leaving structure only.

For the common case where REDCap offers no metadata-only option, or where someone
exported with data by mistake. Runs locally; nothing is transmitted anywhere.

Deliberately kept separate from the adapters: those refuse files with records,
and that refusal must not be weakened.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from ..adapters.odm import ODM, _localname

# Match the whole element, including a self-closing form, without parsing values.
_CLINICAL_DATA = re.compile(
    rb"[ \t]*<(?:\w+:)?ClinicalData\b[^>]*(?:/>|>.*?</(?:\w+:)?ClinicalData>)\s*",
    re.DOTALL | re.IGNORECASE,
)


@dataclass
class StripResult:
    subjects_removed: int
    bytes_before: int
    bytes_after: int

    @property
    def bytes_removed(self) -> int:
        return self.bytes_before - self.bytes_after


def count_subjects(path: str | Path) -> int:
    """Number of SubjectData elements, without reading any value."""
    total = 0
    for _, elem in ET.iterparse(str(path), events=("end",)):
        if _localname(elem.tag) == "SubjectData":
            total += 1
            elem.clear()
    return total


def strip_file(source: str | Path, target: str | Path) -> StripResult:
    """Write a metadata-only copy of an ODM export.

    Operates on bytes rather than re-serialising the tree, so the metadata half
    stays byte-identical and no namespace prefixes are rewritten.
    """
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve():
        raise ValueError("refusing to overwrite the source file; choose another target")

    raw = source.read_bytes()
    subjects = count_subjects(source)
    cleaned, substitutions = _CLINICAL_DATA.subn(b"", raw)

    if subjects and not substitutions:
        raise ValueError(
            f"{source}: found {subjects} subject record(s) but could not remove the "
            "ClinicalData block. Refusing to write a file that may still contain data."
        )

    target.write_bytes(cleaned)

    # Verify against the real parser rather than trusting the regex.
    remaining = count_subjects(target)
    if remaining:
        target.unlink(missing_ok=True)
        raise ValueError(f"{source}: {remaining} record(s) survived stripping; output discarded")

    return StripResult(
        subjects_removed=subjects,
        bytes_before=len(raw),
        bytes_after=len(cleaned),
    )


__all__ = ["ODM", "StripResult", "count_subjects", "strip_file"]
