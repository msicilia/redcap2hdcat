"""Synthetic sample distribution.

The specification requires the sample distribution to be synthetic and anonymised.
Types, ranges and value sets are already known, so generating a structurally
conformant CSV costs almost nothing (MAPPING.md 6).

No real data is ever read: the generator sees the dictionary only.
"""

from __future__ import annotations

import csv
import io
import random

from ..model import FieldType, Project
from .columns import expand, variable_of


def _numeric(lo: str, hi: str, rng: random.Random, decimals: int) -> str:
    try:
        low = float(lo) if lo else 0.0
        high = float(hi) if hi else low + 100.0
    except ValueError:
        low, high = 0.0, 100.0
    if high < low:
        low, high = high, low
    value = rng.uniform(low, high)
    return str(int(round(value))) if decimals == 0 else f"{value:.{decimals}f}"


def _value(project: Project, column, rng: random.Random) -> str:
    var = variable_of(project, column)

    if column.name == project.record_id_field:
        return "" # filled by the caller with a sequence number
    if column.name == "redcap_event_name":
        return rng.choice([e.unique_name for e in project.events]) if project.events else ""
    if column.name == "redcap_repeat_instrument":
        return rng.choice(project.repeating_forms) if project.repeating_forms else ""
    if column.name == "redcap_repeat_instance":
        return str(rng.randint(1, 3))

    if var is not None and var.field_type == FieldType.CHECKBOX:
        return str(rng.randint(0, 1))
    if var is not None and var.is_coded:
        return rng.choice([c.code for c in var.choices])
    if column.choices:  # status columns added on export
        return rng.choice([code for code, _ in column.choices])

    dtype = column.datatype
    lo = var.validation_min if var else ""
    hi = var.validation_max if var else ""

    if dtype == "boolean":
        return str(rng.randint(0, 1))
    if dtype == "integer":
        return _numeric(lo, hi, rng, 0)
    if dtype == "decimal":
        return _numeric(lo, hi, rng, 2)
    if dtype == "date":
        return f"{rng.randint(2015, 2025)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    if dtype == "dateTime":
        return (
            f"{rng.randint(2015, 2025)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d} "
            f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}"
        )
    if dtype == "time":
        return f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}"
    # Never emit anything resembling a real value for free text.
    return f"sample-{rng.randint(1000, 9999)}"


def generate(project: Project, rows: int = 10, seed: int = 0) -> str:
    """Return a structurally conformant synthetic CSV.

    Deterministic given a seed, so fixtures are reproducible.
    """
    rng = random.Random(seed)
    columns = expand(project)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([c.name for c in columns])

    for index in range(1, rows + 1):
        row = []
        for column in columns:
            value = _value(project, column, rng)
            row.append(str(index) if column.name == project.record_id_field else value)
        writer.writerow(row)

    return buffer.getvalue()
