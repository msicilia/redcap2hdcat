"""Namespaces, controlled-vocabulary URIs and the REDCap -> XSD type table."""

from __future__ import annotations

from rdflib import Namespace
from rdflib.namespace import DCAT, DCTERMS, FOAF, PROV, RDF, RDFS, SKOS, XSD
from rdflib.namespace import Namespace as _NS

# Re-exported so callers import namespaces from one place.
__all__ = [
    "DCAT", "DCTERMS", "FOAF", "PROV", "RDF", "RDFS", "SKOS", "XSD",
    "HEALTHDCATAP", "DCATAP", "DPV", "DPV_PD", "CSVW", "ADMS", "VCARD", "DQV", "CV", "ELI",
    "EHDS_LEGISLATION", "ACCESS_RIGHTS", "DATA_THEME", "LANGUAGE", "FILE_TYPE",
    "datatype_for", "language_iri", "language_tag", "personal_data_category",
]

HEALTHDCATAP = Namespace("http://healthdataportal.eu/ns/health#")
DCATAP = Namespace("http://data.europa.eu/r5r/")
DPV = Namespace("https://w3id.org/dpv#")
# HealthDCAT-AP Release 8 requires dpv:hasPersonalData values from this namespace.
DPV_PD = Namespace("https://w3id.org/dpv/dpv-pd#")
CSVW = Namespace("http://www.w3.org/ns/csvw#")
ADMS = Namespace("http://www.w3.org/ns/adms#")
VCARD = Namespace("http://www.w3.org/2006/vcard/ns#")
DQV = Namespace("http://www.w3.org/ns/dqv#")
# Core Vocabularies (cv:contactPoint, cv:ContactPoint, cv:email).
CV = Namespace("http://data.europa.eu/m8g/")
ELI = Namespace("http://data.europa.eu/eli/ontology#")

# Constant for every record produced by this tool.
EHDS_LEGISLATION = "http://data.europa.eu/eli/reg/2025/327/oj"

# EU Publications Office authority tables.
ACCESS_RIGHTS = _NS("http://publications.europa.eu/resource/authority/access-right/")
DATA_THEME = _NS("http://publications.europa.eu/resource/authority/data-theme/")
LANGUAGE = _NS("http://publications.europa.eu/resource/authority/language/")
FILE_TYPE = _NS("http://publications.europa.eu/resource/authority/file-type/")

# ISO 639-1 <-> ISO 639-3 for the languages a REDCap project in the EU is likely to use.
# The EU language table is keyed by the three-letter code in upper case.
_ISO639 = {
    "en": "eng", "es": "spa", "ca": "cat", "eu": "eus", "gl": "glg", "fr": "fra",
    "de": "deu", "it": "ita", "pt": "por", "nl": "nld", "pl": "pol", "ro": "ron",
    "sv": "swe", "da": "dan", "fi": "fin", "el": "ell", "cs": "ces", "sk": "slk",
    "sl": "slv", "hu": "hun", "bg": "bul", "hr": "hrv", "et": "est", "lv": "lav",
    "lt": "lit", "mt": "mlt", "ga": "gle",
}
_ISO639_3 = {v: k for k, v in _ISO639.items()}


def _bare_language(code: str) -> str:
    """Accept 'es', 'spa', 'es-ES' or an enum repr such as 'LanguageEnum.spa'."""
    text = (code or "").strip()
    text = text.rsplit(".", 1)[-1]
    return text.split("-", 1)[0].split("_", 1)[0].lower()


def language_tag(code: str) -> str:
    """Two-letter tag for rdf:langString literals; empty when the code is unknown."""
    bare = _bare_language(code)
    if bare in _ISO639:
        return bare
    return _ISO639_3.get(bare, "")


def language_iri(code: str) -> str:
    """IRI in the EU language table; empty when the code is unknown."""
    bare = _bare_language(code)
    three = _ISO639.get(bare) or (bare if bare in _ISO639_3 else "")
    return f"{LANGUAGE}{three.upper()}" if three else ""


# REDCap validation types that identify a person -> DPV personal-data category
# (names checked against the DPV-PD 2022 report and the current pd: vocabulary).
_PD_BY_VALIDATION = {
    "email": "EmailAddress",
    "phone": "TelephoneNumber",
    "phone_australia": "TelephoneNumber",
    "zipcode": "PhysicalAddress",
    "postalcode_australia": "PhysicalAddress",
    "ssn": "OfficialID",
    "vmrn": "Identifying",
}


def personal_data_category(validation: str, datatype: str = "") -> str:
    """DPV personal-data category of a field flagged as an identifier."""
    name = _PD_BY_VALIDATION.get((validation or "").strip().lower())
    if name:
        return str(DPV_PD[name])
    if datatype in {"date", "dateTime"}:
        return str(DPV_PD["BirthDate"])
    return str(DPV_PD["Identifying"])

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
    # file and signature: the export holds the name of the stored document.
    return "string"
