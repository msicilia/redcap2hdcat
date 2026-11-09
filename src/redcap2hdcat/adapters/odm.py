"""Adapter for the REDCap Project XML export (CDISC ODM 1.3.1 with redcap: extensions).

Uses xml.etree only: lxml would close the Pyodide path.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..model import Choice, Event, FieldType, Project, ProjectMetadata, Variable

ODM = "{http://www.cdisc.org/ns/odm/v1.3}"
REDCAP = "{https://projectredcap.org}"


class ClinicalDataPresent(Exception):
    """Raised when the export carries records, not just structure.

    Blocking by design: a silent pass could process a full patient cohort.
    """


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _strip_prefix(value: str, prefix: str) -> str:
    return value[len(prefix):] if value.startswith(prefix) else value


def assert_metadata_only(root: ET.Element) -> None:
    """Refuse exports containing ClinicalData."""
    for child in root:
        if _localname(child.tag) == "ClinicalData":
            subjects = sum(1 for e in child if _localname(e.tag) == "SubjectData")
            raise ClinicalDataPresent(
                f"export contains <ClinicalData> ({subjects} subject record(s)). "
                "This tool reads structure only. Re-export with 'metadata only' selected."
            )


def _text_of(elem: ET.Element | None) -> str:
    return (elem.text or "").strip() if elem is not None and elem.text else ""


# REDCap's ODM widget names differ from its data dictionary names.
_FIELD_TYPE_ALIASES = {
    "select": "dropdown",
    "textarea": "notes",
    "sql": "dropdown",
}

# Likewise for validation types: the dictionary says 'integer', the ODM says 'int'.
_VALIDATION_ALIASES = {
    "int": "integer",
    "float": "number",
}


def _field_type(item: ET.Element) -> FieldType:
    """REDCap keeps the original widget in a vendor attribute."""
    raw = (item.get(f"{REDCAP}FieldType") or "").strip().lower()
    if not raw:
        return FieldType.TEXT
    return FieldType.parse(_FIELD_TYPE_ALIASES.get(raw, raw))


def _validation(item: ET.Element) -> str:
    """Normalise the validation type, falling back to the standard ODM DataType.

    Not every item carries redcap:TextValidationType, but DataType is mandatory in
    ODM and distinguishes date and integer fields that would otherwise look like
    free text.
    """
    raw = (item.get(f"{REDCAP}TextValidationType") or "").strip().lower()
    if raw:
        return _VALIDATION_ALIASES.get(raw, raw)

    data_type = (item.get("DataType") or "").strip().lower()
    return {"integer": "integer", "float": "number", "double": "number"}.get(data_type, "")


def _collect_codelists(mdv: ET.Element) -> dict[str, list[Choice]]:
    """Structured value sets, so no regex over ``1, Male | 2, Female``."""
    out: dict[str, list[Choice]] = {}
    for cl in mdv.findall(f"{ODM}CodeList"):
        oid = cl.get("OID", "")
        choices: list[Choice] = []
        for item in cl.findall(f"{ODM}CodeListItem"):
            decode = item.find(f"{ODM}Decode/{ODM}TranslatedText")
            choices.append(Choice(code=item.get("CodedValue", ""), label=_text_of(decode)))
        if oid:
            out[oid] = choices
    return out


def load(path: str | Path) -> Project:
    """Read a REDCap Project XML export into the intermediate representation."""
    path = Path(path)
    root = ET.parse(path).getroot()
    assert_metadata_only(root)

    study = root.find(f"{ODM}Study")
    if study is None:
        raise ValueError(f"{path}: no <Study> element; not a REDCap Project XML export")

    mdv = study.find(f"{ODM}MetaDataVersion")
    if mdv is None:
        raise ValueError(f"{path}: no <MetaDataVersion> element")

    global_vars = study.find(f"{ODM}GlobalVariables")
    codelists = _collect_codelists(mdv)

    # ItemGroupDef elements are *sections*, not instruments: their Name is the section
    # header and redcap:FormName is often absent. The instrument comes from FormDef,
    # whose ItemGroupRef children point at the sections it owns.
    group_form: dict[str, str] = {}
    for form_def in mdv.findall(f"{ODM}FormDef"):
        name = form_def.get(f"{REDCAP}FormName") or _strip_prefix(form_def.get("OID", ""), "Form.")
        for ref in form_def.findall(f"{ODM}ItemGroupRef"):
            group_form[ref.get("ItemGroupOID", "")] = name

    item_form: dict[str, str] = {}
    item_order: list[str] = []
    for ig in mdv.findall(f"{ODM}ItemGroupDef"):
        oid = ig.get("OID", "")
        # Fall back to the OID prefix: REDCap names sections <form>.<first_item>.
        form = group_form.get(oid) or (oid.split(".", 1)[0] if "." in oid else ig.get("Name", ""))
        for ref in ig.findall(f"{ODM}ItemRef"):
            item_oid = ref.get("ItemOID", "")
            if item_oid and item_oid not in item_form:
                item_form[item_oid] = form
                item_order.append(item_oid)

    defs = {i.get("OID", ""): i for i in mdv.findall(f"{ODM}ItemDef")}

    variables: list[Variable] = []
    for oid in item_order:
        item = defs.get(oid)
        if item is None:
            continue
        question = item.find(f"{ODM}Question/{ODM}TranslatedText")
        cl_ref = item.find(f"{ODM}CodeListRef")
        choices = codelists.get(cl_ref.get("CodeListOID", ""), []) if cl_ref is not None else []
        variables.append(
            Variable(
                name=item.get("Name", oid),
                form=item_form.get(oid, ""),
                field_type=_field_type(item),
                label=_text_of(question),
                note=item.get(f"{REDCAP}FieldNote", ""),
                validation=_validation(item),
                calculation=item.get(f"{REDCAP}Calculation", ""),
                validation_min=item.get(f"{REDCAP}TextValidationMin", ""),
                validation_max=item.get(f"{REDCAP}TextValidationMax", ""),
                choices=choices,
                identifier=(item.get(f"{REDCAP}Identifier", "") or "").lower() in {"y", "yes"},
                required=(item.get("Mandatory", "") or "").lower() == "yes",
                branching_logic=item.get(f"{REDCAP}BranchingLogic", ""),
                annotation=item.get(f"{REDCAP}FieldAnnotation", ""),
            )
        )

    events = [
        Event(
            unique_name=se.get(f"{REDCAP}UniqueEventName")
            or _strip_prefix(se.get("OID", ""), "Event."),
            # Name embeds the arm ("Event 1 (Arm 1: PTS 1)"); EventName is the plain label.
            label=se.get(f"{REDCAP}EventName") or se.get("Name", ""),
            arm=se.get(f"{REDCAP}ArmName", ""),
        )
        for se in mdv.findall(f"{ODM}StudyEventDef")
    ]

    # Repeating instruments appear either as a vendor element or as Repeating="Yes"
    # on the FormDef, depending on REDCap version.
    repeating = [
        rf.get(f"{REDCAP}FormName", "")
        for rf in mdv.findall(f".//{REDCAP}RepeatingInstrument")
        if rf.get(f"{REDCAP}FormName")
    ]
    for form_def in mdv.findall(f"{ODM}FormDef"):
        if (form_def.get("Repeating") or "").lower() == "yes":
            name = form_def.get(f"{REDCAP}FormName") or _strip_prefix(
                form_def.get("OID", ""), "Form."
            )
            if name and name not in repeating:
                repeating.append(name)

    meta = ProjectMetadata(
        # StudyName is a filename-derived string, not a real title, but it is the
        # only candidate present in a file export.
        title=_text_of(global_vars.find(f"{ODM}StudyName")) if global_vars is not None else "",
        source_system=root.get("SourceSystem", "REDCap"),
        source_system_version=root.get("SourceSystemVersion", ""),
        is_longitudinal=bool(events),
    )

    return Project(
        metadata=meta,
        variables=variables,
        events=events,
        repeating_forms=repeating,
        provenance={
            "adapter": "odm",
            "source_file": path.name,
            # Export timestamp, not project creation date.
            "export_datetime": root.get("CreationDateTime", ""),
        },
    )
