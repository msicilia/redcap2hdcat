"""Conformance checking against the official HealthDCAT-AP SHACL shapes.

No validator is written here: the HealthData@EU Validator and the published shapes
already exist. This only drives pySHACL over local shape files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rdflib import Graph

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
]

_DATASET = "http://www.w3.org/ns/dcat#Dataset"
_RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


@dataclass
class ValidationResult:
    conforms: bool
    missing: list[str]
    report: str = ""
    shacl_used: bool = False

    def to_dict(self) -> dict:
        return {
            "conforms": self.conforms,
            "missing_mandatory": self.missing,
            "shacl_used": self.shacl_used,
            "report": self.report,
        }


def check_mandatory(graph: Graph) -> list[str]:
    """Return mandatory properties absent from any dcat:Dataset in the graph."""
    from rdflib import URIRef

    datasets = list(graph.subjects(URIRef(_RDF_TYPE), URIRef(_DATASET)))
    if not datasets:
        return ["no dcat:Dataset found in graph"]

    missing: list[str] = []
    for dataset in datasets:
        for uri, label in MANDATORY:
            if (dataset, URIRef(uri), None) not in graph:
                missing.append(label)
    return sorted(set(missing))


def validate(graph: Graph, shapes_dir: str | Path | None = None) -> ValidationResult:
    """Check mandatory properties, and run pySHACL when shapes are available."""
    missing = check_mandatory(graph)

    if shapes_dir is None:
        return ValidationResult(conforms=not missing, missing=missing)

    shapes_path = Path(shapes_dir)
    shape_files = sorted(shapes_path.glob("*.ttl"))
    if not shape_files:
        raise FileNotFoundError(f"no .ttl shape files in {shapes_path}")

    try:
        from pyshacl import validate as shacl_validate
    except ImportError as exc: # pragma: no cover - optional dependency
        raise RuntimeError(
            "SHACL checking needs the 'shacl' extra: pip install 'redcap2hdcat[shacl]'"
        ) from exc

    shapes = Graph()
    for shape_file in shape_files:
        shapes.parse(shape_file, format="turtle")

    conforms, _, text = shacl_validate(graph, shacl_graph=shapes, advanced=True)
    return ValidationResult(
        conforms=bool(conforms) and not missing,
        missing=missing,
        report=text,
        shacl_used=True,
    )
