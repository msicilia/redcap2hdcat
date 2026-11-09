"""Command line interface.

Exit codes are meaningful so this composes in CI: 0 conformant, 1 missing
mandatory properties, 2 usage or input error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .adapters import load_project
from .adapters.odm import ClinicalDataPresent
from .config import TEMPLATE, Config
from .core import audit as audit_mod
from .core import rdf, sample, strip, validate

EXIT_OK = 0
EXIT_NONCONFORMANT = 1
EXIT_ERROR = 2


def _load_config(path: str | None) -> Config:
    return Config.load(path) if path else Config()


def cmd_audit(args: argparse.Namespace) -> int:
    project = load_project(args.source)
    report = audit_mod.audit(project)

    if args.json:
        json.dump(report.to_dict(), sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return EXIT_OK if report.error_count == 0 else EXIT_NONCONFORMANT

    print(f"Project: {report.source or args.source}")
    print(f"  variables: {report.variable_count}   forms: {report.form_count}"
          f"   longitudinal: {'yes' if report.is_longitudinal else 'no'}")
    if not report.findings:
        print("\nNo findings.")
        return EXIT_OK

    print(f"\n{len(report.findings)} finding(s), {report.error_count} error(s):\n")
    for severity in ("error", "warning", "info"):
        group = [f for f in report.findings if f.severity == severity]
        if not group:
            continue
        print(f"  [{severity}]")
        for finding in group:
            detail = f" ({finding.detail})" if finding.detail else ""
            print(f"    {finding.variable}: {finding.message}{detail}  <{finding.rule}>")
        print()

    # Internal use only: this output names fields that leak identifiers.
    print("This report is for internal use. Do not publish it alongside the catalogue.")
    return EXIT_OK if report.error_count == 0 else EXIT_NONCONFORMANT


def cmd_build(args: argparse.Namespace) -> int:
    project = load_project(args.source)
    config = _load_config(args.config)

    # Second source: fill the institute/responsible/description/licence gaps REDCap
    # leaves, from a machine-actionable DMP (RDA DMP Common Standard).
    if args.dmp:
        from .adapters import dmp as dmp_adapter
        overlay = dmp_adapter.load(args.dmp, project_title=project.metadata.title)
        overlay.apply(project)
        print(f"Composed with DMP: {overlay.title}", file=sys.stderr)

    graph = rdf.build(project, config, snomed_demo=args.snomed)
    if args.snomed:
        print("SNOMED demo mapper on: codes are illustrative, not validated.",
              file=sys.stderr)

    output = graph.serialize(format=args.format)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Wrote {args.output} ({len(graph)} triples)", file=sys.stderr)
    else:
        sys.stdout.write(output)

    gaps = config.missing_mandatory()
    if gaps:
        print(f"\nIncomplete: {', '.join(gaps)} not set in configuration.", file=sys.stderr)
        if not args.config:
            print("Start from a template: redcap2hdcat init-config > institution.yaml",
                  file=sys.stderr)
        return EXIT_NONCONFORMANT
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    graph = validate.Graph()
    graph.parse(args.record)
    result = validate.validate(graph, args.shapes)

    if args.json:
        json.dump(result.to_dict(), sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    elif result.conforms:
        checked = (f"SHACL, {result.profile or 'given'} shapes" if result.shacl_used
                   else "mandatory properties")
        warn = f"; {result.warnings} warning(s)" if result.warnings else ""
        print(f"Conformant ({checked} checked{warn}).")
    else:
        for prop in result.missing:
            print(f"  missing: {prop}")
        for v in result.violations:
            path = f" [{v['path']}]" if v["path"] else ""
            print(f"  violation{path}: {v['message']}")
        if result.shacl_used:
            print(f"{len(result.violations)} violation(s), {result.warnings} warning(s) "
                  f"({result.profile or 'given'} shapes).")
    return EXIT_OK if result.conforms else EXIT_NONCONFORMANT


def cmd_sample(args: argparse.Namespace) -> int:
    project = load_project(args.source)
    output = sample.generate(project, rows=args.rows, seed=args.seed)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output)
    return EXIT_OK


def cmd_strip(args: argparse.Namespace) -> int:
    target = Path(args.output)
    if target.exists() and not args.force:
        print(f"{target} exists; pass --force to overwrite.", file=sys.stderr)
        return EXIT_ERROR

    result = strip.strip_file(args.source, target)
    if result.subjects_removed:
        print(f"Removed {result.subjects_removed} subject record(s) "
              f"({result.bytes_removed:,} bytes). Wrote {target}", file=sys.stderr)
        print("The source file still contains those records. Delete it if you no longer "
              "need it.", file=sys.stderr)
    else:
        print(f"No records found; the export was already metadata-only. Wrote {target}",
              file=sys.stderr)
    return EXIT_OK


def cmd_init_config(args: argparse.Namespace) -> int:
    if args.output:
        path = Path(args.output)
        if path.exists() and not args.force:
            print(f"{path} exists; pass --force to overwrite.", file=sys.stderr)
            return EXIT_ERROR
        path.write_text(TEMPLATE, encoding="utf-8")
        print(f"Wrote {path}", file=sys.stderr)
    else:
        sys.stdout.write(TEMPLATE)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="redcap2hdcat",
        description="Derive HealthDCAT-AP records from REDCap project metadata. "
                    "Reads structure only; never writes to REDCap.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("audit", help="report data dictionary quality issues")
    p.add_argument("source", help="Project XML or data dictionary CSV")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("build", help="generate the HealthDCAT-AP record")
    p.add_argument("source")
    p.add_argument("-c", "--config", help="institutional configuration YAML")
    p.add_argument("--dmp", help="maDMP JSON (RDA) to fill institute/responsible/description")
    p.add_argument("--snomed", action="store_true",
                   help="add SNOMED coding (demo mapper; codes are illustrative)")
    p.add_argument("-o", "--output")
    p.add_argument("-f", "--format", default="turtle",
                   choices=["turtle", "xml", "json-ld", "nt"])
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("check", help="validate a generated record")
    p.add_argument("record", help="Turtle or RDF/XML file")
    p.add_argument("--shapes", help="directory of official SHACL .ttl shape files")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("sample", help="generate a synthetic sample distribution")
    p.add_argument("source")
    p.add_argument("-n", "--rows", type=int, default=10)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("strip", help="write a metadata-only copy of a Project XML export")
    p.add_argument("source", help="Project XML export, possibly containing records")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_strip)

    p = sub.add_parser("init-config", help="write a configuration template")
    p.add_argument("-o", "--output")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ClinicalDataPresent as exc:
        print(f"Refusing to process: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
