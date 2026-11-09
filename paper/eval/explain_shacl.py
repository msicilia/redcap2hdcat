"""Attach a cause to every distinct SHACL result group in results/shacl_summary.csv.

The cause column is the author's reading of each group (checked against the record, the tool's
source and the pinned Release 8 shapes); it is kept in code so that it is reviewable.

Cause classes
  tool-bug          the tool emits something the spec/vocabulary does not define, or uses the wrong term
  tool-gap          the tool never emits a property Release 8 requires / recommends
  config            the value would come from institutional configuration (here: HDAB, by design empty)
  untyped-iri       a controlled-vocabulary / ELI IRI is used correctly but the record does not state its
                    rdf:type, while Release 8 range.ttl has sh:class (the bundled vocabularies do not type them)
Output: results/shacl_explained.csv
"""

from __future__ import annotations

import csv

from evallib import RESULTS, write_csv

# (path, component-substring) -> (cause class, explanation). First match wins.
RULES = [
    ("csvw:title", "MinCount", "tool-bug",
     "Tool writes csvw:titles; the CSVW ontology defines csvw:title (csvw:titles is not an RDF term)."),
    ("csvw:propertyUrl", "NodeKind", "tool-bug",
     "Tool copies the raw REDCap field annotation (e.g. @PLACEHOLDER='Month') into csvw:propertyUrl as a "
     "literal; Release 8 requires an IRI."),
    ("dct:description", "MinCount", "tool-gap",
     "Release 8 requires dct:description on every csvw:Column; tool emits one only when the REDCap field "
     "note is non-empty."),
    ("csvw:column", "MinCount", "tool-gap",
     "Release 8 expects csvw:column on csvw:Table; tool puts the columns on a csvw:Schema reached through "
     "csvw:tableSchema (CSVW metadata layout)."),
    ("dct:title", "MinCount", "tool-gap",
     "Release 8 requires dct:title on the csvw:TableGroup; tool emits none."),
    ("skos:inScheme", "", "tool-bug",
     "Consequence of dct:conformsTo -> csvw:TableGroup: the TableGroup is checked as a concept of the "
     "HealthData@EU 'standard' vocabulary. Tool should use healthdcatap:hasVariables for the dictionary."),
    ("dct:conformsTo", "", "tool-bug",
     "Tool links the variable dictionary (csvw:TableGroup) with dct:conformsTo, whose Release 8 range is "
     "dct:Standard from the 'standard' vocabulary; the Release 8 property is healthdcatap:hasVariables."),
    ("dct:language", "", "tool-bug",
     "Tool emits dct:language as a plain literal (e.g. \"en\"); Release 8 requires an IRI of the EU "
     "language NAL typed dct:LinguisticSystem."),
    ("dpv:hasPersonalData", "MinCount", "tool-gap",
     "Recommended; absent when no REDCap field is flagged as identifier and no DMP says personal data."),
    ("dpv:hasPersonalData", "", "tool-bug",
     "Tool emits dpv:hasPersonalData true (xsd:boolean); Release 8 expects IRIs of dpv-pd personal-data "
     "categories (pattern ^https://w3id.org/dpv/dpv-pd#.+, class dpv:PersonalData)."),
    ("", "PersonalDataRestriction", "tool-bug",
     "Same cause as the dpv:hasPersonalData literal."),
    ("dcat:distribution", "MinCount", "tool-gap", "Mandatory; tool emits no dcat:Distribution."),
    ("dct:provenance", "MinCount", "tool-gap", "Mandatory for NON_PUBLIC; tool emits none."),
    ("dct:type", "MinCount", "tool-gap",
     "Dataset: mandatory for NON_PUBLIC, tool emits none. foaf:Agent (Warning): creator/HDAB agents carry "
     "no dct:type."),
    ("healthdcatap:hasStructuredData", "MinCount", "tool-gap",
     "Mandatory 1..1; tool never emits it (it would be the constant true for a REDCap project)."),
    ("healthdcatap:hdab", "MinCount", "config",
     "HDAB left empty by design (not designated)."),
    ("healthdcatap:hdab", "Node", "tool-bug",
     "With an HDAB configured, the agent fails HealthAgent_Shape: tool writes foaf:mbox but no "
     "cv:contactPoint."),
    ("cv:contactPoint", "MinCount", "tool-bug",
     "Agents (publisher; HDAB when set) carry foaf:mbox/foaf:homepage but no cv:contactPoint, which "
     "Release 8 HealthPublisherAgent_Shape / HealthAgent_Shape require exactly once."),
    ("dct:publisher", "Node", "tool-bug", "Publisher fails HealthPublisherAgent_Shape (no cv:contactPoint)."),
    ("dct:accessRights", "Class", "untyped-iri",
     "Value is the correct NAL IRI access-right/NON_PUBLIC, but range.ttl requires class "
     "dct:RightsStatement and neither the record nor the bundled NAL states it."),
    ("dcatap:applicableLegislation", "Class", "untyped-iri",
     "Value is the EHDS ELI IRI, but range.ttl requires class eli:LegalResource, not stated in the record."),
]


def classify(row: dict) -> tuple[str, str]:
    if row["severity"] == "Warning" and row["component"] == "sh:MinCountConstraintComponent" \
            and row["focus_type"] == "dcat:Dataset" and row["path"] != "dpv:hasPersonalData":
        return "tool-gap", "Recommended property not emitted."
    for path, comp, cause, why in RULES:
        if path and path != row["path"]:
            continue
        if comp and comp not in row["component"] and comp not in row["source_shape"]:
            continue
        return cause, why
    return "unclassified", ""


def main() -> None:
    with (RESULTS / "shacl_summary.csv").open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        cause, why = classify(r)
        out.append({"variant": r["variant"], "severity": r["severity"], "focus_type": r["focus_type"],
                    "path": r["path"], "source_shape": r["source_shape"], "component": r["component"],
                    "n_results": r["n_results"], "n_sources": r["n_sources"], "cause": cause,
                    "explanation": why, "example_value": r["example_value"]})
    write_csv(RESULTS / "shacl_explained.csv", out)
    for v in ("records", "records_hdab"):
        sub = [o for o in out if o["variant"] == v]
        by = {}
        for o in sub:
            k = (o["severity"], o["cause"])
            by[k] = by.get(k, 0) + 1
        print(v, "groups:", len(sub), dict(sorted(by.items())))


if __name__ == "__main__":
    main()
