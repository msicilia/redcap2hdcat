"""Compare the official HealthData@EU (ITB) validator report for one record with the local
pySHACL reproduction (shacl_check.py), group by severity x path x constraint component.

Also lists the local results whose focus node lies outside the record (brought in by merging
the shapes/vocabulary graph into the data graph, as the ITB validator does), which
shacl_check.py excludes from its summaries.

Usage: python itb_compare.py [record-id] [variant]
       (defaults rtd-case07-longitudinal, records; variant records_hdab = with placeholders)
Output: results/itb/compare_<id>.csv, results/itb/outside_record_<id>.csv
"""

from __future__ import annotations

import csv
import sys
from collections import Counter

from pyshacl import validate
from rdflib import Graph
from rdflib.namespace import RDF, SH

from evallib import RESULTS, write_csv
from shacl_check import PREFIXES, build_shapes, curie, shape_label


def expand(c: str) -> str:
    for ns, p in PREFIXES.items():
        if c.startswith(p):
            return ns + c[len(p):]
    return c.strip("<>")


def main() -> None:
    rid = sys.argv[1] if len(sys.argv) > 1 else "rtd-case07-longitudinal"
    variant = sys.argv[2] if len(sys.argv) > 2 else "records"
    itb = Graph().parse(RESULTS / "itb" / f"{rid}.report.ttl")
    online = Counter(
        (str(itb.value(r, SH.resultSeverity)).split("#")[1], str(itb.value(r, SH.resultPath)),
         str(itb.value(r, SH.sourceConstraintComponent)).split("#")[1])
        for r in itb.subjects(RDF.type, SH.ValidationResult))
    with (RESULTS / "shacl" / variant / f"{rid}.csv").open(newline="", encoding="utf-8") as fh:
        local = Counter((r["severity"], expand(r["path"]), r["component"].replace("sh:", ""))
                        for r in csv.DictReader(fh) if r["severity"])

    # Local results outside the record.
    shapes, _ = build_shapes()
    rec = Graph().parse(RESULTS / variant / f"{rid}.ttl")
    data = Graph()
    for t in shapes:
        data.add(t)
    for t in rec:
        data.add(t)
    _, rep, _ = validate(data, shacl_graph=shapes, inference="none", advanced=True,
                         allow_warnings=True)
    inrec = set(rec.subjects()) | set(rec.objects())
    details = set(rep.objects(None, SH.detail))
    outside = []
    for r in rep.subjects(RDF.type, SH.ValidationResult):
        f = rep.value(r, SH.focusNode)
        if r in details or f in inrec:
            continue
        key = (str(rep.value(r, SH.resultSeverity)).split("#")[1], str(rep.value(r, SH.resultPath)),
               str(rep.value(r, SH.sourceConstraintComponent)).split("#")[1])
        local[key] += 0
        outside.append({"severity": key[0], "path": key[1], "component": key[2],
                        "focus_node": curie(f),
                        "focus_types": ";".join(curie(t) for t in data.objects(f, RDF.type)),
                        "source_shape": shape_label(shapes, rep.value(r, SH.sourceShape)),
                        "message": str(rep.value(r, SH.resultMessage))})
    out_keys = Counter((o["severity"], o["path"], o["component"]) for o in outside)
    rows = [{"severity": k[0], "path": k[1], "component": k[2], "itb_online": online[k],
             "local_in_record": local[k], "local_outside_record": out_keys[k],
             "match": "y" if online[k] == local[k] + out_keys[k] else "n"}
            for k in sorted(set(online) | set(local) | set(out_keys))]
    write_csv(RESULTS / "itb" / f"compare_{rid}.csv", rows)
    write_csv(RESULTS / "itb" / f"outside_record_{rid}.csv", outside or [{"severity": ""}])
    print("online", sum(online.values()), "local in-record", sum(local.values()),
          "outside", len(outside), "mismatching groups", sum(r["match"] == "n" for r in rows))


if __name__ == "__main__":
    main()
