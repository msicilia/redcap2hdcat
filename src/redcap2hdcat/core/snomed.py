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
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# system name -> base URI for a concept in that system.
_SYSTEM_URI = {
    "SNOMED": "http://snomed.info/id/",
    "LOINC": "https://loinc.org/",
    "ICD10": "http://hl7.org/fhir/sid/icd-10/",
    "ICD10CM": "http://hl7.org/fhir/sid/icd-10-cm/",
}

# system name -> Wikidata entity for healthdcatap:hasCodingSystem (dataset level).
CODING_SYSTEM_WIKIDATA = {
    "SNOMED": "http://www.wikidata.org/entity/Q1753883",
    "LOINC": "http://www.wikidata.org/entity/Q502415",
    "ICD10": "http://www.wikidata.org/entity/Q45127",
    "ICD10CM": "http://www.wikidata.org/entity/Q45127",
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
