"""Data dictionary quality audit.

Findings are emitted as structured records from day one: the empirical study is a
by-product of running the tool, not separate work.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Literal

from ..model import FieldType, Project
from .vocab import DATE_VALIDATIONS, IDENTIFYING_VALIDATIONS

Severity = Literal["error", "warning", "info"]

# Names and labels that denote a direct identifier in Spanish or English clinical use.
_IDENTIFIER_PATTERNS = [
    (r"\bnhc\b|\bhistoria\s*cl|\bmedical\s*record|\bmrn\b", "medical record number"),
    (r"\bcipa\b|\btarjeta\s*sanitaria|\bhealth\s*card", "health card number"),
    (r"\bdni\b|\bnif\b|\bnie\b|\bpasaporte\b|\bpassport\b|\bssn\b", "national identifier"),
    (r"fecha.*nacimiento|\bfnac\b|birth\s*date|\bdob\b|date.*birth", "date of birth"),
    (r"\btel[eé]fono\b|\btelefono\b|\bphone\b|\bm[oó]vil\b", "phone number"),
    (r"\bemail\b|correo\s*electr", "email address"),
    (r"\bdirecci[oó]n\b|\baddress\b|\bdomicilio\b", "postal address"),
    (r"\bnombre\b|\bapellido|\bfirst\s*name|\blast\s*name|\bsurname\b", "personal name"),
]

_BRANCHING_VAR = re.compile(r"\[([A-Za-z0-9_]+)")


@dataclass
class Finding:
    """One rule violation, tied to a rule id so results aggregate across projects."""

    rule: str
    severity: Severity
    variable: str
    message: str
    detail: str = ""


@dataclass
class AuditReport:
    """Machine-readable audit result for one project."""

    source: str = ""
    variable_count: int = 0
    form_count: int = 0
    is_longitudinal: bool = False
    findings: list[Finding] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    def counts_by_rule(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.rule] = out.get(f.rule, 0) + 1
        return out

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "variable_count": self.variable_count,
            "form_count": self.form_count,
            "is_longitudinal": self.is_longitudinal,
            "error_count": self.error_count,
            "counts_by_rule": self.counts_by_rule(),
            "findings": [asdict(f) for f in self.findings],
        }


def _looks_identifying(name: str, label: str) -> str:
    haystack = f"{name} {label}".lower()
    for pattern, kind in _IDENTIFIER_PATTERNS:
        if re.search(pattern, haystack):
            return kind
    return ""


def audit(project: Project) -> AuditReport:
    """Run every rule over a project."""
    report = AuditReport(
        source=project.provenance.get("source_file", ""),
        variable_count=len(project.variables),
        form_count=len(project.forms),
        is_longitudinal=bool(project.events),
    )
    add = report.findings.append
    declared = {v.name for v in project.variables}
    record_id = project.record_id_field

    for var in project.variables:
        # The headline metric: a direct identifier left unflagged.
        if not var.identifier and var.name != record_id:
            kind = _looks_identifying(var.name, var.label)
            if kind or var.validation in IDENTIFYING_VALIDATIONS:
                add(
                    Finding(
                        rule="unflagged-identifier",
                        severity="error",
                        variable=var.name,
                        message="Field looks like a direct identifier but is not flagged.",
                        detail=kind or f"validation '{var.validation}'",
                    )
                )

        if var.field_type in {FieldType.RADIO, FieldType.DROPDOWN, FieldType.CHECKBOX}:
            if not var.choices:
                add(
                    Finding(
                        rule="coded-without-choices",
                        severity="error",
                        variable=var.name,
                        message="Coded field declares no value set.",
                    )
                )
            else:
                codes = [c.code for c in var.choices]
                if len(codes) != len(set(codes)):
                    add(
                        Finding(
                            rule="duplicate-choice-code",
                            severity="error",
                            variable=var.name,
                            message="Value set repeats a code.",
                        )
                    )

        # Free text where a value set belongs.
        if var.field_type in {FieldType.TEXT, FieldType.NOTES} and not var.validation:
            add(
                Finding(
                    rule="unconstrained-text",
                    severity="warning",
                    variable=var.name,
                    message="Free-text field with no validation declared.",
                )
            )

        if var.validation in {"integer", "number", "number_1dp", "number_2dp"}:
            if not var.validation_min and not var.validation_max:
                add(
                    Finding(
                        rule="numeric-without-range",
                        severity="warning",
                        variable=var.name,
                        message="Numeric field declares neither minimum nor maximum.",
                    )
                )

        if var.validation in DATE_VALIDATIONS and not var.identifier:
            add(
                Finding(
                    rule="date-not-reviewed",
                    severity="info",
                    variable=var.name,
                    message="Date field: confirm it is not a date of birth.",
                )
            )

        if not var.label:
            add(
                Finding(
                    rule="missing-label",
                    severity="warning",
                    variable=var.name,
                    message="Field has no label; CSVW title falls back to the name.",
                )
            )

        for referenced in set(_BRANCHING_VAR.findall(var.branching_logic or "")):
            if referenced not in declared:
                add(
                    Finding(
                        rule="dangling-branching-reference",
                        severity="error",
                        variable=var.name,
                        message="Branching logic references an undeclared variable.",
                        detail=referenced,
                    )
                )

    # Label reused across forms with different value sets: a merge hazard.
    by_label: dict[str, list] = {}
    for var in project.variables:
        if var.is_coded and var.label:
            by_label.setdefault(var.label.strip().lower(), []).append(var)
    for label, group in by_label.items():
        signatures = {tuple(sorted((c.code, c.label) for c in v.choices)) for v in group}
        if len(group) > 1 and len(signatures) > 1:
            add(
                Finding(
                    rule="inconsistent-coding",
                    severity="warning",
                    variable=", ".join(v.name for v in group),
                    message="Same label coded differently in different fields.",
                    detail=label,
                )
            )

    return report
