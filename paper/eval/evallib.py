"""Shared helpers for the redcap2hdcat evaluation scripts.

Run every script with the tool's own environment so the version under test is used:
    uv run --project ../.. --extra shacl --extra dmp python <script>.py
"""

from __future__ import annotations

import csv
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

EVAL = Path(__file__).resolve().parent
TOOL = EVAL.parent.parent  # .../papers/redcap2hdcat/redcap2healthdcat
PAPER = TOOL.parent  # .../papers/redcap2hdcat
CORPUS = EVAL / "corpus"
RESULTS = EVAL / "results"
CONFIG = EVAL / "config"
SHAPES = EVAL / "shapes" / "release-8" / "ehds"

# Internal institutional project (rectal cancer, IRYCIS). Outputs stay local (results/rectal/).
RECTAL_XML = PAPER / "workspace" / "ejemplo-test" / "proyecto-limpio.xml"
RECTAL_CSV = PAPER / "workspace" / "ejemplo-test" / (
    "MultiplataformaEnCncerDeRecto_DataDictionary_2026-07-20.csv")
# Synthetic DMP written for the tool's tests. NOT the study's real DMP.
DMP_FIXTURE = TOOL / "tests" / "fixtures" / "dmp.json"

UV = ["uv", "run", "--project", str(TOOL), "--extra", "shacl", "--extra", "dmp"]
CLI = UV + ["redcap2hdcat"]

ODM = "{http://www.cdisc.org/ns/odm/v1.3}"
REDCAP = "{https://projectredcap.org}"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run the tool's CLI exactly as a user would."""
    return subprocess.run(CLI + [str(a) for a in args], capture_output=True, text=True)


def load_sources() -> list[dict]:
    """Corpus A selection from corpus/SOURCES.tsv (excluded entries skipped)."""
    with (CORPUS / "SOURCES.tsv").open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    out = []
    for row in rows:
        if row["source_id"].startswith("EXCLUDED"):
            continue
        repo = row["repo_url"].rstrip("/").rsplit("/", 1)[-1]
        row["file"] = CORPUS / repo / row["path"]
        out.append(row)
    return out


def input_format(path: Path) -> str:
    return "Project XML (ODM)" if path.suffix.lower() == ".xml" else "CSV data dictionary"


def header_convention(path: Path) -> str:
    """UI download ('Variable / Field Name') vs API/raw metadata ('field_name')."""
    if path.suffix.lower() != ".csv":
        return "n/a (XML)"
    with path.open(newline="", encoding="utf-8-sig") as fh:
        first = next(csv.reader(fh))
    h = (first[0] if first else "").strip().lower()
    if "variable / field name" in h:
        return "UI (Variable / Field Name)"
    if h == "field_name":
        return "API (field_name)"
    return f"other ({first[0]!r})"


def source_structure(path: Path) -> dict:
    """Count fields/forms/events/arms straight from the file, independently of the tool.

    CSV: one row per field. ODM: distinct redcap:Variable over ItemDefs, excluding the
    form-status '<form>_complete' items and redcap_data_access_group, which REDCap adds to
    the ODM but which are not dictionary fields.
    """
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh))
        head = [h.strip().lower() for h in rows[0]]
        name_i = next(i for i, h in enumerate(head) if "field name" in h or h == "field_name")
        form_i = next(i for i, h in enumerate(head) if "form name" in h or h == "form_name")
        names = [r[name_i].strip() for r in rows[1:] if len(r) > name_i and r[name_i].strip()]
        forms = {r[form_i].strip() for r in rows[1:] if len(r) > form_i and r[name_i].strip()}
        return {"fields_in_source": len(names), "forms_in_source": len(forms),
                "events_in_source": "", "arms_in_source": ""}
    root = ET.parse(path).getroot()
    mdv = root.find(f"{ODM}Study/{ODM}MetaDataVersion")
    forms = [f.get(f"{REDCAP}FormName") or f.get("OID", "") for f in mdv.findall(f"{ODM}FormDef")]
    status = {f"{f}_complete" for f in forms}
    variables: list[str] = []
    for item in mdv.findall(f"{ODM}ItemDef"):
        var = item.get(f"{REDCAP}Variable") or item.get("Name", "")
        if var in status or var == "redcap_data_access_group":
            continue
        if var not in variables:
            variables.append(var)
    events = mdv.findall(f"{ODM}StudyEventDef")
    arms = {e.get(f"{REDCAP}ArmName", "") for e in events} - {""}
    return {"fields_in_source": len(variables), "forms_in_source": len(forms),
            "events_in_source": len(events), "arms_in_source": len(arms) if events else ""}


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def dump_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
