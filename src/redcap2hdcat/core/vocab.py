"""Namespaces, controlled-vocabulary URIs and the REDCap -> XSD type table."""

from __future__ import annotations

from rdflib import Namespace
from rdflib.namespace import DCAT, DCTERMS, FOAF, PROV, RDF, RDFS, SKOS, XSD
from rdflib.namespace import Namespace as _NS

# Re-exported so callers import namespaces from one place.
__all__ = [
    "DCAT", "DCTERMS", "FOAF", "PROV", "RDF", "RDFS", "SKOS", "XSD",
    "HEALTHDCATAP", "DCATAP", "DPV", "CSVW", "ADMS", "VCARD", "DQV",
    "EHDS_LEGISLATION", "ACCESS_RIGHTS", "DATA_THEME", "datatype_for",
]

HEALTHDCATAP = Namespace("http://healthdataportal.eu/ns/health#")
DCATAP = Namespace("http://data.europa.eu/r5r/")
DPV = Namespace("https://w3id.org/dpv#")
CSVW = Namespace("http://www.w3.org/ns/csvw#")
ADMS = Namespace("http://www.w3.org/ns/adms#")
VCARD = Namespace("http://www.w3.org/2006/vcard/ns#")
DQV = Namespace("http://www.w3.org/ns/dqv#")

# Constant for every record produced by this tool.
EHDS_LEGISLATION = "http://data.europa.eu/eli/reg/2025/327/oj"

# EU Publications Office authority tables.
ACCESS_RIGHTS = _NS("http://publications.europa.eu/resource/authority/access-right/")
DATA_THEME = _NS("http://publications.europa.eu/resource/authority/data-theme/")

# REDCap text_validation_type_or_show_slider_number -> XSD datatype.
_VALIDATION_TYPES: dict[str, str] = {
    "integer": "integer",
    "number": "decimal",
    "number_1dp": "decimal",
    "number_2dp": "decimal",
    "number_3dp": "decimal",
    "number_4dp": "decimal",
    "number_comma_decimal": "decimal",
    "date_ymd": "date",
    "date_dmy": "date",
    "date_mdy": "date",
    "datetime_ymd": "dateTime",
    "datetime_dmy": "dateTime",
    "datetime_mdy": "dateTime",
    "datetime_seconds_ymd": "dateTime",
    "datetime_seconds_dmy": "dateTime",
    "datetime_seconds_mdy": "dateTime",
    "time": "time",
    "time_mm_ss": "string",
    "email": "string",
    "phone": "string",
    "phone_australia": "string",
    "postalcode_australia": "string",
    "zipcode": "string",
    "ssn": "string",
    "vmrn": "string",
    "alpha_only": "string",
}

# Validation types that are, by construction, direct identifiers or quasi-identifiers.
IDENTIFYING_VALIDATIONS = frozenset({"email", "phone", "phone_australia", "ssn", "vmrn", "zipcode",
                                     "postalcode_australia"})

DATE_VALIDATIONS = frozenset(v for v, t in _VALIDATION_TYPES.items() if t in {"date", "dateTime"})


def datatype_for(field_type: str, validation: str = "", coded: bool = False) -> str:
    """Map a REDCap field to an XSD datatype name.

    Mirrors the type table in MAPPING.md 4.
    """
    ft = (field_type or "").strip().lower()
    val = (validation or "").strip().lower()

    if ft == "text":
        return _VALIDATION_TYPES.get(val, "string")
    if ft == "notes":
        return "string"
    if ft in {"radio", "dropdown"}:
        return "integer" if coded else "string"
    if ft in {"yesno", "truefalse"}:
        return "boolean"
    if ft == "checkbox":
        # Each expanded column is a 0/1 flag.
        return "boolean"
    if ft == "calc":
        return "decimal"
    if ft == "slider":
        return "integer"
    return "string"
