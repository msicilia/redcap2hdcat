"""Conformance checking against the official HealthDCAT-AP SHACL shapes.

No validator is written here: the HealthData@EU Validator and the published shapes
already exist. This only drives pySHACL over local shape files, set up the way the
official validator sets itself up.

Two layouts are accepted for --shapes:

* the configuration folder of the HealthData@EU (ITB) validator, published with each
  HealthDCAT-AP release (``.../ehds/`` with ``config.properties``). The shape files of
  the profile that matches the record's access rights are loaded, their owl:imports
  are resolved through the folder's own import mapping, and the shapes graph is
  merged into the data graph, as the validator does, so that controlled-vocabulary
  checks see the vocabularies;
* any folder of ``.ttl`` shape files, loaded as they are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, SH

# Mandatory dcat:Dataset properties (MAPPING.md 1). Checked without
# SHACL so that `check` gives a useful answer with no extra dependency installed.
MANDATORY = [
    ("http://purl.org/dc/terms/title", "dct:title"),
    ("http://purl.org/dc/terms/description", "dct:description"),
    ("http://purl.org/dc/terms/identifier", "dct:identifier"),
    ("http://purl.org/dc/terms/accessRights", "dct:accessRights"),
    ("http://data.europa.eu/r5r/applicableLegislation", "dcatap:applicableLegislation"),
    ("http://healthdataportal.eu/ns/health#healthCategory", "healthdcatap:healthCategory"),
    ("http://healthdataportal.eu/ns/health#hdab", "healthdcatap:hdab"),
    # Mandatory for non-public datasets in Release 8.
    ("http://www.w3.org/ns/dcat#distribution", "dcat:distribution"),
    ("http://purl.org/dc/terms/provenance", "dct:provenance"),
    ("http://purl.org/dc/terms/type", "dct:type"),
    ("http://healthdataportal.eu/ns/health#hasStructuredData", "healthdcatap:hasStructuredData"),
]

_DATASET = "http://www.w3.org/ns/dcat#Dataset"
_RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
_ACCESS_RIGHTS = URIRef("http://purl.org/dc/terms/accessRights")
_PROFILES = {"PUBLIC": "public", "NON_PUBLIC": "non-public", "RESTRICTED": "restricted"}


@dataclass
class ValidationResult:
    conforms: bool
    missing: list[str]
    report: str = ""
    shacl_used: bool = False
    profile: str = ""
    violations: list[dict] = field(default_factory=list)
    warnings: int = 0

    def to_dict(self) -> dict:
        return {
            "conforms": self.conforms,
            "missing_mandatory": self.missing,
            "shacl_used": self.shacl_used,
            "profile": self.profile,
            "violations": self.violations,
            "warnings": self.warnings,
        }


def check_mandatory(graph: Graph) -> list[str]:
    """Return mandatory properties absent from any dcat:Dataset in the graph."""
    datasets = list(graph.subjects(URIRef(_RDF_TYPE), URIRef(_DATASET)))
    if not datasets:
        return ["no dcat:Dataset found in graph"]

    missing: list[str] = []
    for dataset in datasets:
        for uri, label in MANDATORY:
            if (dataset, URIRef(uri), None) not in graph:
                missing.append(label)
    return sorted(set(missing))


def _read_properties(path: Path) -> dict[str, str]:
    """Java .properties, enough for the validator's config (key=value, \\ continuations)."""
    props: dict[str, str] = {}
    key, value = None, ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if key is None:
            if not line or line.startswith(("#", "!")) or "=" not in line:
                continue
            key, value = (part.strip() for part in line.split("=", 1))
        else:
            value += line
        if value.endswith("\\"):
            value = value[:-1]
            continue
        props[key] = value
        key, value = None, ""
    return props


def profile_of(graph: Graph) -> str:
    """Validation profile from the record's dct:accessRights (non-public by default)."""
    for value in graph.objects(None, _ACCESS_RIGHTS):
        name = str(value).rstrip("/").rsplit("/", 1)[-1]
        if name in _PROFILES:
            return _PROFILES[name]
    return "non-public"


def load_validator_shapes(folder: Path, profile: str) -> Graph:
    """Shapes of one profile from an ITB validator folder, with imports resolved."""
    props = _read_properties(folder / "config.properties")
    key = f"validator.shaclFile.{profile}"
    if key not in props:
        raise ValueError(f"{folder}/config.properties defines no '{profile}' profile")
    mapping: dict[str, str] = {}
    i = 0
    while f"validator.owlImportMapping.{i}.uri" in props:
        mapping[props[f"validator.owlImportMapping.{i}.uri"]] = \
            props[f"validator.owlImportMapping.{i}.file"]
        i += 1
    skipped = {u.strip() for u in props.get("validator.owlImportSkippedUris", "").split(",")}

    shapes = Graph()
    for name in (f.strip() for f in props[key].split(",")):
        shapes.parse(folder / name, format="turtle")
    loaded: set[str] = set()
    while True:
        pending = {str(o) for o in shapes.objects(None, OWL.imports)} - loaded
        if not pending:
            break
        for uri in sorted(pending):
            loaded.add(uri)
            if uri in skipped or uri not in mapping:
                continue
            local = folder / mapping[uri]
            shapes.parse(local, format="xml" if local.suffix in {".rdf", ".owl"} else "turtle")
    return shapes


def repair_pathless_property_shapes(shapes: Graph) -> int:
    """Turn an sh:property without sh:path into a node shape with the parent's targets.

    HealthDCAT-AP Release 8 states the hasStructuredData -> hasVariables rule this way.
    SHACL requires a path on every property shape, and pySHACL rejects the whole
    shapes graph otherwise. The rule itself is kept.
    """
    repaired = 0
    for parent, prop in list(shapes.subject_objects(SH.property)):
        if shapes.value(prop, SH.path) is not None:
            continue
        shapes.remove((parent, SH.property, prop))
        shapes.add((prop, RDF.type, SH.NodeShape))
        for target in (SH.targetClass, SH.targetNode, SH.targetSubjectsOf, SH.targetObjectsOf):
            for value in shapes.objects(parent, target):
                shapes.add((prop, target, value))
        repaired += 1
    return repaired


def _results(report: Graph, record: Graph) -> tuple[list[dict], int]:
    """Top-level results whose focus node is in the record, as the official validator
    reports them (nested sh:detail results and vocabulary nodes left out)."""
    in_record = set(record.subjects()) | set(record.objects())
    details = set(report.objects(None, SH.detail))
    violations, warnings = [], 0
    for res in report.subjects(RDF.type, SH.ValidationResult):
        if res in details or report.value(res, SH.focusNode) not in in_record:
            continue
        severity = report.value(res, SH.resultSeverity)
        if severity == SH.Violation:
            violations.append({
                "focus_node": str(report.value(res, SH.focusNode)),
                "path": str(report.value(res, SH.resultPath) or ""),
                "message": str(report.value(res, SH.resultMessage) or ""),
                "value": str(report.value(res, SH.value) or ""),
            })
        elif severity == SH.Warning:
            warnings += 1
    return violations, warnings


def validate(graph: Graph, shapes_dir: str | Path | None = None) -> ValidationResult:
    """Check mandatory properties, and run pySHACL when shapes are available."""
    missing = check_mandatory(graph)

    if shapes_dir is None:
        return ValidationResult(conforms=not missing, missing=missing)

    folder = Path(shapes_dir)
    try:
        from pyshacl import validate as shacl_validate
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "SHACL checking needs the 'shacl' extra: pip install 'redcap2hdcat[shacl]'"
        ) from exc

    profile = ""
    data = Graph()
    for triple in graph:
        data.add(triple)
    if (folder / "config.properties").exists():
        profile = profile_of(graph)
        shapes = load_validator_shapes(folder, profile)
        for triple in shapes:
            data.add(triple)
    else:
        shape_files = sorted(folder.glob("*.ttl"))
        if not shape_files:
            raise FileNotFoundError(
                f"no .ttl shape files and no validator config.properties in {folder}")
        shapes = Graph()
        for shape_file in shape_files:
            shapes.parse(shape_file, format="turtle")
    repair_pathless_property_shapes(shapes)

    _, report, text = shacl_validate(data, shacl_graph=shapes, inference="none",
                                     advanced=True, allow_warnings=True)
    violations, warnings = _results(report, graph)
    return ValidationResult(
        conforms=not violations and not missing,
        missing=missing,
        report=text if violations else "",
        shacl_used=True,
        profile=profile,
        violations=violations,
        warnings=warnings,
    )
