"""Task 3: SHACL conformance against the pinned HealthDCAT-AP Release 8 shapes.

Reproduces the official HealthData@EU (ITB) validator set-up from the release's own
shapes/release-8/ehds/config.properties, offline, with pySHACL:
  * shapes graph = validator.shaclFile.<type> files + every owl:imports resolved through
    validator.owlImportMapping.* (recursively; validator.owlImportSkippedUris skipped). This
    pulls in the (locally modified) DCAT-AP 3.0.0 shapes, the ontologies and the controlled
    vocabularies (EU NALs + HealthData@EU CVs), as validator.preloadOwlImports=true does.
  * data graph = record + shapes graph. The ITB SHACL validator merges the shapes model
    into the input before validating (its default mergeModelsBeforeValidation=true); the
    vocabulary membership shapes (skos:inScheme) need the concepts in the data graph.
  * validation type 'non-public', because every record has dct:accessRights NON_PUBLIC.
Results whose focus node does not occur in the record (vocabulary concepts brought in by
the merge) are counted separately as 'outside_record' and excluded from the summaries.

Usage:
  python shacl_check.py                 # corpus records (records/, records_hdab/) + rectal stages
Outputs:
  results/shacl/<variant>/<id>.csv      every validation result (in-record)
  results/shacl_per_record.csv          counts per record and variant
  results/shacl_summary.csv             grouped by severity x focus type x path x sourceShape
  results/shacl_hdab_diff.csv           groups present without HDAB vs with placeholder HDAB
  results/rectal/shacl_*.csv            same for the internal rectal project (local only)
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

from pyshacl import validate
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, SH

from evallib import RESULTS, SHAPES, write_csv

PROFILE = "non-public"
PREFIXES = {
    "http://www.w3.org/ns/dcat#": "dcat:", "http://purl.org/dc/terms/": "dct:",
    "http://data.europa.eu/r5r/": "dcatap:", "https://w3id.org/dpv#": "dpv:",
    "http://healthdataportal.eu/ns/health#": "healthdcatap:", "http://www.w3.org/ns/csvw#": "csvw:",
    "http://xmlns.com/foaf/0.1/": "foaf:", "http://www.w3.org/2006/vcard/ns#": "vcard:",
    "http://data.europa.eu/m8g/": "cv:", "http://data.europa.eu/930/": "geodcatap:",
    "http://www.w3.org/ns/adms#": "adms:", "http://www.w3.org/2004/02/skos/core#": "skos:",
    "http://www.w3.org/ns/shacl#": "sh:", "http://www.w3.org/2000/01/rdf-schema#": "rdfs:",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:", "http://www.w3.org/ns/prov#": "prov:",
    "https://semiceu.github.io/DCAT-AP/releases/3.0.0/html/shacl/shapes.ttl#": "dcatap-shapes:",
    "http://www.w3.org/2001/XMLSchema#": "xsd:",
}


def curie(term) -> str:
    if term is None:
        return ""
    if isinstance(term, Literal):
        return repr(str(term))[:80] + (f"^^{curie(term.datatype)}" if term.datatype else "")
    s = str(term)
    for ns, p in PREFIXES.items():
        if s.startswith(ns):
            return p + s[len(ns):]
    return f"<{s}>" if isinstance(term, URIRef) else "_:b"


def read_properties(path: Path) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            props[k.strip()] = v.strip()
    return props


def build_shapes(profile: str = PROFILE) -> tuple[Graph, list[str]]:
    props = read_properties(SHAPES / "config.properties")
    files = [f.strip() for f in props[f"validator.shaclFile.{profile}"].split(",")]
    mapping = {}
    i = 0
    while f"validator.owlImportMapping.{i}.uri" in props:
        mapping[props[f"validator.owlImportMapping.{i}.uri"]] = \
            props[f"validator.owlImportMapping.{i}.file"]
        i += 1
    skipped = {u.strip() for u in props.get("validator.owlImportSkippedUris", "").split(",")}

    g = Graph()
    for f in files:
        g.parse(SHAPES / f, format="turtle")
    loaded, log = set(), [f"shaclFile: {f}" for f in files]
    while True:
        pending = {str(o) for o in g.objects(None, OWL.imports)} - loaded
        if not pending:
            break
        for uri in sorted(pending):
            loaded.add(uri)
            if uri in skipped:
                log.append(f"import skipped (config): {uri}")
                continue
            if uri not in mapping:
                log.append(f"import UNRESOLVED (no mapping): {uri}")
                continue
            local = SHAPES / mapping[uri]
            fmt = "xml" if local.suffix in {".rdf", ".owl"} else "turtle"
            g.parse(local, format=fmt)
            log.append(f"import {uri} -> {mapping[uri]}")
    log += patch_pathless_property_shapes(g)
    return g, log


def patch_pathless_property_shapes(g: Graph) -> list[str]:
    """In-memory workaround for a defect in the Release 8 shapes (files left untouched).

    shapes/<type>-shapes.ttl puts an sh:or (hasStructuredData -> hasVariables) inside an
    sh:property [] that has no sh:path. SHACL 2.3.1 requires every value of sh:property to be
    a property shape with exactly one sh:path; pySHACL rejects the whole shapes graph. We turn
    that blank node into a stand-alone node shape with the parent's targets, keeping its
    sh:or, sh:severity and sh:message, which is the evident intent.
    """
    notes = []
    for parent, prop in list(g.subject_objects(SH.property)):
        if g.value(prop, SH.path) is not None:
            continue
        g.remove((parent, SH.property, prop))
        g.add((prop, RDF.type, SH.NodeShape))
        for tp in (SH.targetClass, SH.targetNode, SH.targetSubjectsOf, SH.targetObjectsOf):
            for t in g.objects(parent, tp):
                g.add((prop, tp, t))
        notes.append(f"PATCH: pathless sh:property of {curie(parent)} "
                     f"(message: {g.value(prop, SH.message)}) re-attached as node shape "
                     f"targeting {[curie(t) for t in g.objects(parent, SH.targetClass)]}")
    return notes


def shape_label(shapes: Graph, shape) -> str:
    """Name a (possibly blank) property shape by its parent node shape and path."""
    if isinstance(shape, URIRef):
        return curie(shape)
    parent = next(shapes.subjects(SH.property, shape), None)
    path = shapes.value(shape, SH.path)
    return f"{curie(parent) if parent is not None else '_:b'}[{render_path(shapes, path)}]"


def render_path(g: Graph, path) -> str:
    if path is None:
        return ""
    if isinstance(path, BNode):
        alt = g.value(path, SH.alternativePath)
        if alt is not None:
            return "|".join(curie(x) for x in Collection(g, alt))
        inv = g.value(path, SH.inversePath)
        if inv is not None:
            return "^" + curie(inv)
        try:
            return "/".join(curie(x) for x in Collection(g, path))
        except Exception:
            return "_:path"
    return curie(path)


def check_record(record: Path, shapes: Graph) -> tuple[list[dict], int]:
    rec = Graph().parse(record)
    data = Graph()
    for t in shapes:
        data.add(t)
    for t in rec:
        data.add(t)
    in_record = set(rec.subjects()) | set(rec.objects())
    _, report, _ = validate(data, shacl_graph=shapes, inference="none", advanced=True,
                            allow_warnings=True)
    rows, outside = [], 0
    # pySHACL also types the nested sh:detail results of sh:node failures as sh:ValidationResult;
    # the ITB validator reports only top-level results, so skip details.
    details = set(report.objects(None, SH.detail))
    for res in report.subjects(RDF.type, SH.ValidationResult):
        if res in details:
            continue
        focus = report.value(res, SH.focusNode)
        if focus not in in_record:
            outside += 1
            continue
        types = sorted(curie(t) for t in rec.objects(focus, RDF.type)) or ["(untyped)"]
        path = report.value(res, SH.resultPath)
        rows.append({
            "severity": curie(report.value(res, SH.resultSeverity)).replace("sh:", ""),
            "focus_type": ",".join(types),
            "focus_node": curie(focus),
            "path": render_path(report, path) if path is not None else "",
            "source_shape": shape_label(shapes, report.value(res, SH.sourceShape)),
            "component": curie(report.value(res, SH.sourceConstraintComponent)),
            "value": curie(report.value(res, SH.value)),
            "message": re.sub(r"\s+", " ", str(report.value(res, SH.resultMessage) or ""))[:300],
        })
    return rows, outside


GROUP = ["severity", "focus_type", "path", "source_shape", "component"]


def run_set(name: str, records: list[Path], shapes: Graph, outdir: Path):
    per_record, groups = [], defaultdict(lambda: {"n_results": 0, "sources": set(),
                                                    "example_value": "", "message": ""})
    for rec in records:
        rows, outside = check_record(rec, shapes)
        write_csv(outdir / name / f"{rec.stem}.csv", rows or [{k: "" for k in
                  GROUP + ["focus_node", "value", "message"]}],
                  GROUP + ["focus_node", "value", "message"])
        sev = defaultdict(int)
        for r in rows:
            sev[r["severity"]] += 1
            g = groups[tuple(r[k] for k in GROUP)]
            g["n_results"] += 1
            g["sources"].add(rec.stem)
            g["example_value"] = g["example_value"] or r["value"]
            g["message"] = g["message"] or r["message"]
        per_record.append({"variant": name, "source": rec.stem,
                           "conforms": "y" if sev["Violation"] == 0 else "n",
                           "violations": sev["Violation"], "warnings": sev["Warning"],
                           "infos": sev["Info"], "results_outside_record": outside})
        print(name, rec.stem, dict(sev), "outside", outside, flush=True)
    summary = [dict(zip(GROUP, k), variant=name, n_results=v["n_results"],
                    n_sources=len(v["sources"]), sources=";".join(sorted(v["sources"])),
                    example_value=v["example_value"], message=v["message"])
               for k, v in sorted(groups.items())]
    return per_record, summary


def main() -> None:
    shapes, log = build_shapes()
    (RESULTS / "shacl").mkdir(parents=True, exist_ok=True)
    (RESULTS / "shacl" / "shapes_load_log.txt").write_text(
        f"profile={PROFILE}\nshapes+imports triples={len(shapes)}\n" + "\n".join(log) + "\n",
        encoding="utf-8")

    sets = [("records", sorted((RESULTS / "records").glob("*.ttl")), RESULTS / "shacl"),
            ("records_hdab", sorted((RESULTS / "records_hdab").glob("*.ttl")), RESULTS / "shacl")]
    rectal = RESULTS / "rectal"
    if "--no-rectal" not in sys.argv and rectal.exists():
        sets.append(("rectal", sorted(rectal.glob("stage_*.ttl")), rectal / "shacl"))

    fields_sum = ["variant"] + GROUP + ["n_results", "n_sources", "sources", "example_value",
                                        "message"]
    corpus_pr, corpus_sum = [], []
    for name, recs, outdir in sets:
        pr, sm = run_set(name, recs, shapes, outdir)
        if name == "rectal":
            write_csv(rectal / "shacl_per_record.csv", pr)
            write_csv(rectal / "shacl_summary.csv", sm, fields_sum)
        else:
            corpus_pr += pr
            corpus_sum += sm
    write_csv(RESULTS / "shacl_per_record.csv", corpus_pr)
    write_csv(RESULTS / "shacl_summary.csv", corpus_sum, fields_sum)

    # Isolate what the undesignated HDAB alone causes.
    def keyed(variant):
        return {tuple(r[k] for k in GROUP): r for r in corpus_sum if r["variant"] == variant}
    a, b = keyed("records"), keyed("records_hdab")
    diff = []
    for k in sorted(set(a) | set(b)):
        status = ("only_without_hdab" if k not in b else
                  "only_with_placeholder_hdab" if k not in a else "both")
        diff.append(dict(zip(GROUP, k), status=status,
                         n_sources_without_hdab=a[k]["n_sources"] if k in a else 0,
                         n_sources_with_hdab=b[k]["n_sources"] if k in b else 0,
                         message=(a.get(k) or b.get(k))["message"]))
    write_csv(RESULTS / "shacl_hdab_diff.csv", diff)


if __name__ == "__main__":
    main()
