"""Normalised intermediate representation.

Adapters produce these; the core consumes them. Nothing here knows about REDCap
export quirks, RDF, or the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class FieldType(StrEnum):
    """REDCap field types that survive normalisation."""

    TEXT = "text"
    NOTES = "notes"
    RADIO = "radio"
    DROPDOWN = "dropdown"
    CHECKBOX = "checkbox"
    YESNO = "yesno"
    TRUEFALSE = "truefalse"
    CALC = "calc"
    SLIDER = "slider"
    FILE = "file"
    DESCRIPTIVE = "descriptive"
    SIGNATURE = "signature"

    @classmethod
    def parse(cls, raw: str) -> FieldType:
        try:
            return cls(raw.strip().lower())
        except ValueError:
            return cls.TEXT

    @property
    def is_data_column(self) -> bool:
        """False for presentational fields that never appear as export columns."""
        return self not in {FieldType.DESCRIPTIVE, FieldType.FILE, FieldType.SIGNATURE}


@dataclass(frozen=True)
class Choice:
    """One entry of a coded value set."""

    code: str
    label: str


@dataclass
class Variable:
    """A single dictionary entry, before checkbox expansion."""

    name: str
    form: str
    field_type: FieldType
    label: str = ""
    note: str = ""
    validation: str = ""
    validation_min: str = ""
    validation_max: str = ""
    choices: list[Choice] = field(default_factory=list)
    # For calc fields: the formula, written over internal field names.
    calculation: str = ""
    identifier: bool = False
    required: bool = False
    branching_logic: str = ""
    annotation: str = ""

    @property
    def is_coded(self) -> bool:
        return bool(self.choices)


@dataclass
class Event:
    """Longitudinal event definition. Absent in classic projects."""

    unique_name: str
    label: str = ""
    arm: str = ""


@dataclass
class ProjectMetadata:
    """Dataset-level facts. Mostly absent from file exports.3."""

    project_id: str = ""
    title: str = ""
    description: str = ""
    language: str = ""
    created: str = ""
    modified: str = ""
    purpose: str = ""
    pi_name: str = ""
    pi_email: str = ""
    irb_number: str = ""
    grant_number: str = ""
    source_system: str = ""
    source_system_version: str = ""
    is_longitudinal: bool = False
    record_count: int | None = None
    unique_individual_count: int | None = None
    # Filled from a second source (a maDMP), not from REDCap.
    license: str = ""
    funder: str = ""
    dmp_keywords: list[str] = field(default_factory=list)
    personal_data: bool | None = None


@dataclass
class Project:
    """A REDCap project as the rest of the tool sees it."""

    metadata: ProjectMetadata = field(default_factory=ProjectMetadata)
    variables: list[Variable] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    repeating_forms: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)

    @property
    def record_id_field(self) -> str:
        """First declared variable, whatever it is called."""
        return self.variables[0].name if self.variables else "record_id"

    @property
    def forms(self) -> list[str]:
        seen: dict[str, None] = {}
        for v in self.variables:
            seen.setdefault(v.form, None)
        return list(seen)

    def by_name(self, name: str) -> Variable | None:
        return next((v for v in self.variables if v.name == name), None)
