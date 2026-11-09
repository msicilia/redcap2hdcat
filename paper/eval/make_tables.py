"""Write the manuscript tables from the stored results (no number is typed by hand).

  results/contribution.csv  -> ../tables/elements.tex   (Table 1)
  results/corpus.csv        -> ../tables/corpus.tex     (Table 3)

contribution.csv holds the rectal project's title and form names, but the table written
here contains only element names, properties and sources.
"""

from __future__ import annotations

import csv
import re

from evallib import EVAL, RESULTS

TABLES = EVAL.parent / "tables"


def tex(s: str) -> str:
    return s.replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("&", r"\&") \
        .replace("%", r"\%").replace("#", r"\#")


def obligation(text: str) -> str:
    m = re.match(r"(Mandatory|Recommended|Optional)", text)
    return {"Mandatory": "M", "Recommended": "R", "Optional": "O"}[m.group(1)] if m else "--"


def source(row: dict) -> str:
    by, later = row["supplied_by"], row["changed_later"]
    if not row["first_stage"]:
        need = row["if_not_supplied"].lower()
        if need.startswith("redcap api"):
            return "not supplied: REDCap API"
        if need.startswith(("institutional configuration", "configuration")):
            return "not supplied: settings"
        if need.startswith("redcap field annotations"):
            return "not supplied: field annotations or person"
        return "not supplied: person"
    if by == "REDCap export":
        return "REDCap export"
    if by == "institutional configuration":
        return "institutional settings"
    if by == "DMP":
        return "DMP"
    if by.startswith("tool fallback") and "value changed at c (DMP)" in later:
        return "DMP (copy of title before)"
    if by.startswith("tool-composed"):
        return "tool, from REDCap export"
    if by.startswith("tool-constructed"):
        return "tool, from base address"
    if by.startswith("tool default"):
        return "tool default"
    return "tool constant"


def elements() -> None:
    with (RESULTS / "contribution.csv").open(newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["section"] == "IR 2026/2098 element"]
    lines = [r"\begin{tabular}{@{}r>{\raggedright\arraybackslash}p{3.4cm}lc"
             r">{\raggedright\arraybackslash}p{3.6cm}@{}}", r"\toprule",
             r"No. & Element & HealthDCAT-AP property & Obl. & Source \\", r"\midrule"]
    for r in rows:
        prop = r["r8_property"] or "--"
        lines.append(f"{r['n']} & {tex(r['element'])} & \\code{{{tex(prop)}}} & "
                     f"{obligation(r['r8_obligation_non_public'])} & {tex(source(r))} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    (TABLES / "elements.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


COLLECTION = {"nacc": "NACC UDS", "iedea": "IeDEA", "rtd": "REDCap tests"}
SHORT = {"FormF2COVIDImpactSurvey-Participantv1.3": "FormF2 COVID impact (participant)",
         "FormF3COVID-CoParticipant": "FormF3 COVID (co-participant)"}


def corpus() -> None:
    with (RESULTS / "corpus.csv").open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    lines = [r"\begin{tabular}{@{}llllrrrl@{}}", r"\toprule",
             r"Project & Collection & Format & Header & Forms & Fields & Columns & Viol. \\",
             r"\midrule"]
    for r in rows:
        name = r["source"].split("-", 1)[1]
        name = SHORT.get(name, name)
        fmt = "XML" if r["input_format"].startswith("Project XML") else "CSV"
        header = {"UI": "UI", "API": "API"}.get(r["header_convention"].split(" ", 1)[0], "--")
        lines.append(f"{tex(name)} & {COLLECTION[r['source'].split('-', 1)[0]]} & {fmt} & "
                     f"{header} & {r['forms_in_source']} & {r['fields_in_source']} & "
                     f"{r['csvw_columns']} & {conformance(r['source'])} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    (TABLES / "corpus.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def conformance(source_id: str) -> str:
    """Violations without / with the two placeholders, from shacl_per_record.csv."""
    with (RESULTS / "shacl_per_record.csv").open(newline="", encoding="utf-8") as fh:
        rows = {(r["variant"], r["source"]): r for r in csv.DictReader(fh)}
    return f"{rows[('records', source_id)]['violations']}/" \
           f"{rows[('records_hdab', source_id)]['violations']}"


def main() -> None:
    TABLES.mkdir(exist_ok=True)
    elements()
    corpus()
    print("wrote", TABLES / "elements.tex", TABLES / "corpus.tex")


if __name__ == "__main__":
    main()
