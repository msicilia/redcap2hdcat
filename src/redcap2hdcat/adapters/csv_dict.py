"""Adapter for the REDCap data dictionary CSV export."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from ..model import Choice, FieldType, Project, ProjectMetadata, Variable

# REDCap dictionaries ship in two header conventions: the UI download
# ("Variable / Field Name", localised) and the API / raw metadata ("field_name").
# Each logical column lists substrings to try, most specific first.
_COLUMNS = {
    "name": ["variable / field name", "field_name"],
    "form": ["form name", "form_name"],
    "type": ["field type", "field_type"],
    "label": ["field label", "field_label"],
    "note": ["field note", "field_note"],
    "choices": ["choices, calculations", "select_choices_or_calculations"],
    "validation": ["text validation type", "text_validation_type"],
    "min": ["text validation min", "text_validation_min"],
    "max": ["text validation max", "text_validation_max"],
    "identifier": ["identifier"],
    "required": ["required field", "required_field"],
    "branching": ["branching logic", "branching_logic"],
    "annotation": ["field annotation", "field_annotation"],
}

_CHOICE_SEP = re.compile(r"\s*\|\s*")


def parse_choices(raw: str) -> list[Choice]:
    """Parse ``1, Male | 2, Female`` into codes and labels.

    Labels may themselves contain commas, so split on the first one only.
    """
    if not raw or not raw.strip():
        return []
    out: list[Choice] = []
    for chunk in _CHOICE_SEP.split(raw.strip()):
        if not chunk:
            continue
        code, sep, label = chunk.partition(",")
        if not sep:
            continue
        out.append(Choice(code=code.strip(), label=label.strip()))
    return out


def _resolve_headers(fieldnames: list[str]) -> dict[str, str]:
    """Map our logical keys to the actual header strings present in the file."""
    lowered = {(h or "").strip().lower(): h for h in fieldnames}
    resolved: dict[str, str] = {}
    for key, needles in _COLUMNS.items():
        for needle in needles:
            match = next((h for lc, h in lowered.items() if needle in lc), None)
            if match:
                resolved[key] = match
                break
    return resolved


def _truthy(value: str) -> bool:
    return (value or "").strip().lower() in {"y", "yes", "1", "true"}


def load(path: str | Path) -> Project:
    """Read a data dictionary CSV into the intermediate representation."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError(f"{path}: empty or unreadable data dictionary")
        cols = _resolve_headers(list(reader.fieldnames))
        missing = {"name", "form", "type"} - cols.keys()
        if missing:
            raise ValueError(
                f"{path}: not a REDCap data dictionary (missing columns: {sorted(missing)})"
            )

        variables: list[Variable] = []
        for row in reader:
            name = (row.get(cols["name"]) or "").strip()
            if not name:
                continue

            def cell(key: str, _row: dict = row) -> str:
                header = cols.get(key)
                return (_row.get(header) or "").strip() if header else ""

            field_type = FieldType.parse(cell("type"))
            raw_choices = cell("choices")
            variables.append(
                Variable(
                    name=name,
                    form=cell("form"),
                    field_type=field_type,
                    label=cell("label"),
                    note=cell("note"),
                    validation=cell("validation"),
                    validation_min=cell("min"),
                    validation_max=cell("max"),
                    # calc fields reuse the choices column for the expression.
                    choices=parse_choices(raw_choices) if field_type != FieldType.CALC else [],
                    calculation=raw_choices if field_type == FieldType.CALC else "",
                    identifier=_truthy(cell("identifier")),
                    required=_truthy(cell("required")),
                    branching_logic=cell("branching"),
                    annotation=cell("annotation"),
                )
            )

    return Project(
        metadata=ProjectMetadata(source_system="REDCap"),
        variables=variables,
        provenance={"adapter": "csv_dict", "source_file": path.name},
    )
