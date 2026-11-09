"""Task 2: run build / audit / check over Corpus A and tabulate the results.

Outputs
  results/records/<id>.ttl              build with config/institution.yaml (hdab empty)
  results/records_hdab/<id>.ttl         build with config/institution_hdab.yaml (placeholder HDAB)
  results/records_redcap_only/<id>.ttl  build with config/redcap_only.yaml (stage a)
  results/logs/<id>.<step>.txt          stderr/exit code of every CLI call
  results/corpus.csv                    one row per source
  results/audit.json                    audit --json per source + per-rule totals
  results/audit_summary.csv             rule x number of sources affected (robustness only, not a quality metric)
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from evallib import (CONFIG, PAPER, RESULTS, dump_json, header_convention, input_format,
                     load_sources, run_cli, source_structure, write_csv)
from redcap2hdcat.adapters import load_project

CSVW_COLUMN = URIRef("http://www.w3.org/ns/csvw#Column")
CSVW_NAME = URIRef("http://www.w3.org/ns/csvw#name")
JULY = PAPER / "workspace" / "corpus-registros"

VARIANTS = {
    "records": CONFIG / "institution.yaml",
    "records_hdab": CONFIG / "institution_hdab.yaml",
    "records_redcap_only": CONFIG / "redcap_only.yaml",
}


def log(sid: str, step: str, proc) -> None:
    path = RESULTS / "logs" / f"{sid}.{step}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"exit={proc.returncode}\n--- stderr ---\n{proc.stderr}", encoding="utf-8")


def columns_of(path: Path) -> list[str]:
    if not path.exists():
        return []
    g = Graph().parse(path)
    return [str(g.value(c, CSVW_NAME)) for c in g.subjects(RDF.type, CSVW_COLUMN)]


def longitudinal_from_repo(path: Path) -> str:
    """redcap-test-datasets ships the API project-information export next to the dictionary."""
    info = next(path.parent.glob("*project-information.csv"), None)
    if info is None:
        return ""
    with info.open(newline="", encoding="utf-8") as fh:
        row = next(csv.DictReader(fh))
    return "y" if row.get("is_longitudinal", "").strip() == "1" else "n"


def main() -> None:
    rows, audits = [], {}
    rule_sources: Counter = Counter()
    rule_findings: Counter = Counter()

    for src in load_sources():
        sid, path = src["source_id"], src["file"]
        row = {"source": sid, "domain": src["domain"], "input_format": input_format(path),
               "header_convention": header_convention(path)}

        # Structure as the tool sees it.
        exceptions = []
        try:
            project = load_project(path)
            arms = {e.arm for e in project.events} - {""}
            row.update({
                "forms_tool": len(project.forms),
                "variables_tool": len(project.variables),
                "longitudinal_tool": "y" if project.events else "n",
                "events_tool": len(project.events) if project.events else "",
                "arms_tool": len(arms) if project.events else "",
                "repeating_instruments_tool": len(project.repeating_forms),
            })
        except Exception as exc:  # recorded, not hidden
            exceptions.append(f"load: {type(exc).__name__}: {exc}")

        # Structure counted independently from the file.
        row.update(source_structure(path))
        row["longitudinal_per_repo_project_info"] = longitudinal_from_repo(path)

        # Build in three configurations.
        build_exit = {}
        for outdir, cfg in VARIANTS.items():
            out = RESULTS / outdir / f"{sid}.ttl"
            out.parent.mkdir(parents=True, exist_ok=True)
            proc = run_cli("build", path, "-c", cfg, "-o", out)
            log(sid, f"build.{outdir}", proc)
            build_exit[outdir] = proc.returncode
            if proc.returncode == 2 or "Traceback" in proc.stderr:
                exceptions.append(f"build[{outdir}] exit {proc.returncode}: "
                                  f"{proc.stderr.strip().splitlines()[-1]}")
        record = RESULTS / "records" / f"{sid}.ttl"
        row["build_exit_code"] = build_exit["records"]
        row["build_success"] = "y" if record.exists() and build_exit["records"] in (0, 1) else "n"

        cols = columns_of(record)
        row["csvw_columns"] = len(cols)
        # ODM checkbox options already arrive as field___code items; re-expanding them yields
        # names with two '___' separators (see report, tool bug B1).
        row["csvw_columns_double_checkbox_suffix"] = sum(1 for c in cols if c.count("___") >= 2)
        july = JULY / f"{sid}.ttl"
        row["csvw_columns_july2026_record"] = len(columns_of(july)) if july.exists() else ""

        # Audit.
        proc = run_cli("audit", path, "--json")
        log(sid, "audit", proc)
        try:
            report = json.loads(proc.stdout)
            audits[sid] = report
            for rule, n in report["counts_by_rule"].items():
                rule_sources[rule] += 1
                rule_findings[rule] += n
            row["audit_findings"] = len(report["findings"])
            row["audit_errors"] = report["error_count"]
        except json.JSONDecodeError as exc:
            exceptions.append(f"audit: {exc}")

        # Check (mandatory properties, no SHACL: the SHACL run is shacl_check.py).
        proc = run_cli("check", record, "--json")
        log(sid, "check", proc)
        try:
            res = json.loads(proc.stdout)
            row["check_conforms"] = "y" if res["conforms"] else "n"
            row["mandatory_missing"] = ";".join(res["missing_mandatory"])
        except json.JSONDecodeError as exc:
            exceptions.append(f"check: {exc}")

        row["exceptions"] = " | ".join(exceptions)
        rows.append(row)
        print(sid, row["build_success"], row.get("variables_tool"), row["csvw_columns"],
              row.get("mandatory_missing"))

    fields = ["source", "domain", "input_format", "header_convention",
              "forms_tool", "forms_in_source", "variables_tool", "fields_in_source",
              "longitudinal_tool", "longitudinal_per_repo_project_info", "events_tool",
              "events_in_source", "arms_tool", "arms_in_source", "repeating_instruments_tool",
              "build_success", "build_exit_code", "exceptions", "csvw_columns",
              "csvw_columns_double_checkbox_suffix", "csvw_columns_july2026_record",
              "audit_findings", "audit_errors", "check_conforms", "mandatory_missing"]
    write_csv(RESULTS / "corpus.csv", rows, fields)

    dump_json(RESULTS / "audit.json", {
        "note": "Robustness/illustration only; not a data-quality metric.",
        "rules": {r: {"sources_affected": rule_sources[r], "findings": rule_findings[r]}
                  for r in sorted(rule_sources)},
        "per_source": audits,
    })
    all_rules = ["unflagged-identifier", "coded-without-choices", "duplicate-choice-code",
                 "dangling-branching-reference", "inconsistent-coding", "numeric-without-range",
                 "unconstrained-text", "missing-label", "date-not-reviewed"]
    sev = {"unflagged-identifier": "error", "coded-without-choices": "error",
           "duplicate-choice-code": "error", "dangling-branching-reference": "error",
           "inconsistent-coding": "warning", "numeric-without-range": "warning",
           "unconstrained-text": "warning", "missing-label": "warning",
           "date-not-reviewed": "info"}
    write_csv(RESULTS / "audit_summary.csv", [
        {"rule": r, "severity": sev[r], "sources_affected": rule_sources.get(r, 0),
         "total_findings": rule_findings.get(r, 0), "sources_total": len(rows)}
        for r in all_rules])

    print("total sources", len(rows), "variables_tool", sum(int(r.get("variables_tool") or 0)
          for r in rows), "fields_in_source", sum(int(r["fields_in_source"]) for r in rows))


if __name__ == "__main__":
    main()
