"""Expansion of the dictionary into the columns an export actually has.

The CSVW description must match the *exported* shape, not the dictionary shape
(MAPPING.md 4).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..model import FieldType, Project, Variable
from .snomed import Coding, code_field, parse_rome
from .vocab import datatype_for


@dataclass
class Column:
    """One column of the exported CSV."""

    name: str
    title: str
    description: str
    datatype: str
    required: bool = False
    identifier: bool = False
    source_variable: str = ""
    # An IRI for the column's property. REDCap has none; field annotations are
    # action tags, not IRIs, and are not copied here.
    property_url: str = ""
    form: str = ""
    # The original REDCap widget (text, radio, checkbox...), kept alongside the XSD
    # datatype so the catalogue can show the project's real structure.
    redcap_type: str = ""
    validation: str = ""
    # Calculated fields carry a formula written over internal field names.
    calculation: str = ""
    choices: list[tuple[str, str]] = None # type: ignore[assignment]
    codings: list[Coding] = None # type: ignore[assignment]
    # Codes of the answer options, by choice code (ROME valueCodingMap).
    value_codings: dict[str, list[Coding]] = None # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.choices is None:
            self.choices = []
        if self.codings is None:
            self.codings = []
        if self.value_codings is None:
            self.value_codings = {}

    @property
    def all_codings(self) -> list[Coding]:
        """Codes of the field and of its answer options, without repetition."""
        out = list(self.codings)
        for codings in self.value_codings.values():
            out += [c for c in codings if c not in out]
        return out


def _structural_columns(project: Project) -> list[Column]:
    """Columns REDCap adds on export that exist in no dictionary."""
    out: list[Column] = []
    if project.events:
        out.append(
            Column(
                name="redcap_event_name",
                title="Event Name",
                description="Unique name of the longitudinal event.",
                datatype="string",
            )
        )
    # Both columns appear once anything repeats; the instrument is empty for a
    # repeated event.
    if project.repeating_forms or project.repeating_events:
        out.extend(
            [
                Column(
                    name="redcap_repeat_instrument",
                    title="Repeat Instrument",
                    description="Instrument this repeating instance belongs to.",
                    datatype="string",
                ),
                Column(
                    name="redcap_repeat_instance",
                    title="Repeat Instance",
                    description="Sequence number of the repeating instance.",
                    datatype="integer",
                ),
            ]
        )
    if project.survey_forms and not project.by_name("redcap_survey_identifier"):
        out.append(
            Column(
                name="redcap_survey_identifier",
                title="Survey Identifier",
                description="Identifier of the survey participant, when one is set.",
                datatype="string",
            )
        )
    return out


# Status column that REDCap adds to every instrument on export.
_COMPLETE_CHOICES = [("0", "Incomplete"), ("1", "Unverified"), ("2", "Complete")]


def _complete_column(form: str) -> Column:
    return Column(
        name=f"{form}_complete",
        title="Complete?",
        description="Completion status of the instrument.",
        datatype="integer",
        form=form,
        redcap_type="dropdown",
        choices=list(_COMPLETE_CHOICES),
    )


def _timestamp_column(form: str) -> Column:
    return Column(
        name=f"{form}_timestamp",
        title="Survey Timestamp",
        description="Date and time at which the survey was completed.",
        datatype="dateTime",
        form=form,
    )


def expand(project: Project, snomed_demo: bool = False) -> list[Column]:
    """Return the export columns, with checkboxes expanded to one flag each."""
    columns: list[Column] = []
    record_id = project.record_id_field
    # A Project XML export lists the status and survey columns as items; a CSV data
    # dictionary does not, so they are added here when absent.
    present = {v.name for v in project.variables}
    surveys = set(project.survey_forms)
    first_timestamp: list[Column] = []
    current_form: str | None = None

    def close_form(form: str | None) -> None:
        if form and f"{form}_complete" not in present:
            columns.append(_complete_column(form))

    for index, var in enumerate(project.variables):
        if var.form != current_form:
            close_form(current_form)
            current_form = var.form
            if current_form in surveys and f"{current_form}_timestamp" not in present:
                # The first instrument's timestamp follows the record identifier and
                # the structural columns.
                (first_timestamp if index == 0 else columns).append(
                    _timestamp_column(current_form))
        if not var.field_type.is_data_column:
            continue

        codings = code_field(var.annotation, var.label, var.name, demo=snomed_demo)
        rome = parse_rome(var.annotation)
        value_codings = rome.values if rome else {}

        if var.field_type == FieldType.CHECKBOX:
            for choice in var.choices:
                # REDCap sanitises codes for column names: 1 -> field___1.
                suffix = choice.code.strip().lower().replace("-", "_")
                columns.append(
                    Column(
                        name=f"{var.name}___{suffix}",
                        title=f"{var.label} (choice={choice.label})".strip(),
                        # The label is the title; the note is extra, only when present.
                        description=var.note,
                        datatype="boolean",
                        identifier=var.identifier,
                        source_variable=var.name,
                        form=var.form,
                        redcap_type=var.field_type.value,
                        validation=var.validation,
                        # The column of one option denotes that option.
                        codings=list(codings) + [
                            c for c in value_codings.get(choice.code.strip(), [])
                            if c not in codings],
                    )
                )
            continue

        columns.append(
            Column(
                name=var.name,
                title=var.label or var.name,
                # The label is the title; the note is a genuine extra description.
                description=var.note,
                datatype=datatype_for(var.field_type.value, var.validation, var.is_coded),
                # The record identifier is always required; index 0 is that field.
                required=var.required or index == 0,
                identifier=var.identifier or var.name == record_id,
                source_variable=var.name,
                form=var.form,
                redcap_type=var.field_type.value,
                validation=var.validation,
                calculation=var.calculation,
                choices=[(c.code, c.label) for c in var.choices],
                codings=list(codings),
                value_codings={
                    c.code: value_codings[c.code] for c in var.choices if c.code in value_codings
                },
            )
        )

    close_form(current_form)

    # Structural columns sit right after the record identifier in a real export.
    structural = _structural_columns(project) + first_timestamp
    if structural and columns:
        return columns[:1] + structural + columns[1:]
    return structural + columns


def variable_of(project: Project, column: Column) -> Variable | None:
    return project.by_name(column.source_variable) if column.source_variable else None
