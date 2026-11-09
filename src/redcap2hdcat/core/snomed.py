"""Semantic coding at three levels: dataset, form and field.

REDCap has no native place for terminology codes, so this module defines a
convention for writing them in the field annotation, plus a naive demonstration
mapper that guesses codes from field labels.

PROOF OF CONCEPT. The demonstration mapper's label->code table is illustrative:
the codes are real SNOMED CT identifiers but the assignment to a given field is
approximate. Real annotation is the subject of separate work (an LLM-based mapper).

Convention (terminology-agnostic; chosen because none exists yet):

    @CODE=<system>|<version>|<code-or-expression>

written anywhere in the REDCap field annotation. Fields:

  - system: short token, no '|' (SNOMED, LOINC, ICD10, ...)
  - version: optional, may be empty (a SNOMED edition/date, a LOINC version...)
  - value: a plain code OR a full expression; may embed a human term as |term|
              in SNOMED Compositional Grammar style, which becomes the display.

Only the first two '|' are delimiters, so a value may itself contain '|' (as SCG
terms do). Everything after the tag up to the next '@' belongs to the tag, so other
REDCap action tags (@HIDDEN, @READONLY...) are left untouched. Examples:

    @CODE=SNOMED||22298006
    @CODE=SNOMED|20230731|22298006 |Myocardial infarction|
    @CODE=LOINC|2.74|4548-4
    @CODE=ICD10|2019|I21.9
    @CODE=SNOMED||243796009:246090004=421720008 (post-coordinated expression)

Codes written by the ROME module (REDCap Ontology Annotations Made Easy) are read as
well. ROME stores a JSON object in an ``@ONTOLOGY`` action tag, with FHIR-style codings
for the field (``dataElement.coding``), for its answer options
(``dataElement.valueCodingMap``, keyed by choice code) and for its unit
(``dataElement.unit``). Format: technical_docs/Annotation_Format.md and
schemas/rome-annotation.schema.json in
https://github.com/REDCap-German-User-Group/ontology-annotation (commit f945c6d).
As in ROME's own parser, the tag may be quoted or not, and when several @ONTOLOGY
tags are present the last valid one is used.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# system name -> base URI for a concept in that system.
_SYSTEM_URI = {
    "SNOMED": "http://snomed.info/id/",
    "LOINC": "https://loinc.org/",
    "ICD10": "http://hl7.org/fhir/sid/icd-10/",
    "ICD10CM": "http://hl7.org/fhir/sid/icd-10-cm/",
}

# FHIR code-system URI (as ROME writes it) -> the system token used above.
_FHIR_SYSTEM = {
    "snomed.info/sct": "SNOMED",
    "loinc.org": "LOINC",
    "hl7.org/fhir/sid/icd-10": "ICD10",
    "hl7.org/fhir/sid/icd-10-cm": "ICD10CM",
    "id.who.int/icd/release/11/mms": "ICD11",
    "terminology.hl7.org/CodeSystem/icd-o-3": "ICDO3",
    "www.whocc.no/atc": "ATC",
    "www.nlm.nih.gov/research/umls/rxnorm": "RXNORM",
    "human-phenotype-ontology.org": "HPO",
    "www.orpha.net": "ORPHA",
    "ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl": "NCIT",
    "unitsofmeasure.org": "UCUM",
}

# system name -> concept of the HealthDCAT-AP coding-system vocabulary, the range of
# healthdcatap:hasCodingSystem in Release 8 (catalogue/coding-system.rdf).
_CODING_SYSTEM_NAL = "https://hdeu-dcat.data.health.europa.eu/resource/authority/coding-system/"
CODING_SYSTEM = {
    token: _CODING_SYSTEM_NAL + concept
    for token, concept in {
        "SNOMED": "SNOMED-CT", "LOINC": "LOINC", "ICD10": "ICD-10",
        # ICD-10-CM is the US national modification of ICD-10.
        "ICD10CM": "ICD-10-NAT", "ICD11": "ICD-11", "ICDO3": "ICD-O", "ATC": "ATC",
        "RXNORM": "RXNORM", "HPO": "HPO", "ORPHA": "ORPHACODE", "NCIT": "NCIT",
        "MESH": "MESH", "UCUM": "UCUM",
    }.items()
}

# Everything from @CODE= up to the next action tag or end of string.
_CODE_TAG = re.compile(r"@CODE=([^@]+)")
# A concept whose value is a bare code (no expression operators or whitespace).
_SIMPLE_CODE = re.compile(r"^[A-Za-z0-9.\-]+$")
# A SNOMED Compositional Grammar term: |Human readable|.
_SCG_TERM = re.compile(r"\|([^|]+)\|")


@dataclass(frozen=True)
class Coding:
    system: str
    code: str # a plain code or a full expression
    version: str = ""
    display: str = ""

    @property
    def is_expression(self) -> bool:
        return not bool(_SIMPLE_CODE.match(self.code))

    @property
    def uri(self) -> str:
        """A resolvable concept URI for a plain code; empty for an expression."""
        if self.is_expression:
            return ""
        base = _SYSTEM_URI.get(self.system.upper())
        return f"{base}{self.code}" if base else ""

    @property
    def pill(self) -> str:
        """Compact label for a UI badge, e.g. 'SNOMED 22298006'."""
        return f"{self.system} {self.code}".strip()


def parse_annotation(annotation: str) -> list[Coding]:
    """Field codes: those of the @CODE convention, then those of a ROME @ONTOLOGY tag."""
    out = parse_code_tags(annotation)
    rome = parse_rome(annotation)
    if rome:
        out += [c for c in rome.coding if c not in out]
    return out


def parse_code_tags(annotation: str) -> list[Coding]:
    """Extract codes written with the @CODE convention, ignoring action tags."""
    out: list[Coding] = []
    for payload in _CODE_TAG.findall(annotation or ""):
        parts = payload.strip().split("|", 2) # first two '|' delimit; value keeps the rest
        if len(parts) < 2:
            continue
        system = parts[0].strip().upper()
        version = parts[1].strip() if len(parts) >= 3 else ""
        value = (parts[2] if len(parts) >= 3 else parts[1]).strip()
        if not system or not value:
            continue
        term = _SCG_TERM.search(value)
        display = term.group(1).strip() if term else ""
        code = re.sub(r"\s+", " ", _SCG_TERM.sub("", value)).strip()
        out.append(Coding(system=system, code=code, version=version, display=display))
    return out


# --- ROME @ONTOLOGY ----------------------------------------------------------------

@dataclass(frozen=True)
class RomeAnnotation:
    """Codings of one ROME annotation: field, answer options (by choice code), unit."""

    coding: list[Coding] = field(default_factory=list)
    values: dict[str, list[Coding]] = field(default_factory=dict)
    unit: list[Coding] = field(default_factory=list)


_ONTOLOGY_TAG = re.compile(r"@ONTOLOGY\s*=\s*", re.IGNORECASE)


def _json_object_at(text: str, start: int) -> str | None:
    """The balanced {...} beginning at text[start], skipping braces inside strings."""
    if start >= len(text) or text[start] != "{":
        return None
    depth, in_string, escaped = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _system_token(system: str) -> str:
    key = re.sub(r"^https?://", "", system.strip()).rstrip("/")
    return _FHIR_SYSTEM.get(key, system.strip())


def _codings(items) -> list[Coding]:
    out: list[Coding] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        system, code = str(item.get("system", "")).strip(), str(item.get("code", "")).strip()
        if not system or not code:
            continue
        coding = Coding(system=_system_token(system), code=code,
                        version=str(item.get("version", "")).strip(),
                        display=str(item.get("display", "")).strip())
        if coding not in out:
            out.append(coding)
    return out


def parse_rome(annotation: str) -> RomeAnnotation | None:
    """The last valid ROME @ONTOLOGY annotation in a field annotation, or None."""
    text = annotation or ""
    found: RomeAnnotation | None = None
    for match in _ONTOLOGY_TAG.finditer(text):
        start = match.end()
        if start < len(text) and text[start] in "'\"":
            start += 1
        raw = _json_object_at(text, start)
        if raw is None:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        element = data.get("dataElement") if isinstance(data, dict) else None
        if not isinstance(element, dict):
            continue
        values_raw = element.get("valueCodingMap")
        values = {
            str(code): _codings(entry.get("coding"))
            for code, entry in (values_raw.items() if isinstance(values_raw, dict) else [])
            if isinstance(entry, dict)
        }
        unit = element.get("unit")
        found = RomeAnnotation(
            coding=_codings(element.get("coding")),
            values={k: v for k, v in values.items() if v},
            unit=_codings(unit.get("coding")) if isinstance(unit, dict) else [],
        )
    return found


# --- demonstration auto-mapper -------------------------------------------------
# Illustrative label keywords -> real SNOMED CT concepts. Approximate on purpose.
_DEMO_SNOMED = [
    (("sexo", "sex", "gender", "genero"), "263495000", "Gender"),
    (("edad", "age"), "424144002", "Current chronological age"),
    (("fecha de nacimiento", "fecha nacimiento", "birth date", "date of birth", "dob"),
     "184099003", "Date of birth"),
    (("peso", "weight"), "27113001", "Body weight"),
    (("altura", "talla", "height"), "50373000", "Body height measure"),
    (("diabetes",), "73211009", "Diabetes mellitus"),
    (("hipertension", "hypertension", "hta"), "38341003", "Hypertensive disorder"),
    (("tension arterial", "blood pressure", "presion arterial"), "75367002", "Blood pressure"),
    (("tumor", "tumour", "neoplasia", "cancer", "carcinoma"), "108369006", "Neoplasm"),
    (("recto", "rectal", "rectum"), "34402009", "Rectum structure"),
    (("biopsia", "biopsy"), "86273004", "Biopsy"),
    (("tratamiento", "treatment", "terapia", "therapy"), "276239002", "Therapy"),
    (("quimioterapia", "chemotherapy"), "367336001", "Chemotherapy"),
    (("radioterapia", "radiotherapy"), "108290001", "Radiation oncology / radiotherapy"),
    (("estadio", "stage", "staging"), "258235000", "Tumor stage"),
    (("mutacion", "mutation"), "55446002", "Genetic mutation"),
    (("diagnostico", "diagnosis"), "439401001", "Diagnosis"),
    (("supervivencia", "survival"), "445320007", "Survival"),
    (("recidiva", "recurrence", "relapse"), "246455001", "Recurrence"),
]


def guess_snomed(label: str, name: str = "") -> Coding | None:
    """Demonstration only: guess a SNOMED concept from a field label.

    Returns a real SNOMED code, but the match is heuristic and must not be treated
    as a validated clinical annotation.
    """
    haystack = f"{label} {name}".lower()
    for keywords, code, display in _DEMO_SNOMED:
        if any(k in haystack for k in keywords):
            return Coding("SNOMED", code, display)
    return None


def code_field(annotation: str, label: str, name: str = "", *, demo: bool) -> list[Coding]:
    """Codes for one field: explicit annotation wins; the demo mapper fills gaps."""
    explicit = parse_annotation(annotation)
    if explicit:
        return explicit
    if demo:
        guess = guess_snomed(label, name)
        return [guess] if guess else []
    return []
