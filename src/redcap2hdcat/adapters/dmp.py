"""Adapter for a machine-actionable DMP (RDA DMP Common Standard).

A REDCap file export describes the instrument but not the dataset as a governed
asset: no institute, responsible person, description, licence or project. A maDMP
carries exactly those. This adapter reads one and returns an overlay that fills the
gaps REDCap leaves.

Parsing and validation are delegated to madmpy (an optional dependency), so the
REDCap-only core keeps working without it and stays pure-Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import Agent
from ..core.vocab import language_tag
from ..model import Project


class DMPUnavailable(RuntimeError):
    """madmpy is not installed."""


@dataclass
class DMPOverlay:
    """Project-level metadata sourced from a maDMP, ready to enrich a Project."""

    title: str = ""
    description: str = ""
    language: str = ""
    issued: str = ""
    modified: str = ""
    creator: Agent = field(default_factory=Agent)
    contact: Agent = field(default_factory=Agent)
    grant_number: str = ""
    funder: str = ""
    project_title: str = ""
    license: str = ""
    keywords: list[str] = field(default_factory=list)
    personal_data: bool | None = None

    def apply(self, project: Project) -> None:
        """Fill empty metadata fields on a project. The DMP never overwrites a value
        REDCap already provided; it only fills what is missing."""
        meta = project.metadata
        if not meta.title:
            meta.title = self.title
        if not meta.description and self.description:
            meta.description = self.description
            meta.dmp_text_language = _language_code(self.language)
        if self.keywords and not meta.dmp_text_language:
            meta.dmp_text_language = _language_code(self.language)
        if not meta.language:
            meta.language = _language_code(self.language)
        if not meta.project_title:
            meta.project_title = self.project_title
        if not meta.created:
            meta.created = self.issued
        if not meta.modified:
            meta.modified = self.modified
        if not meta.pi_name and self.creator.name:
            meta.pi_name = self.creator.name
            meta.pi_email = self.creator.email
        if not meta.grant_number:
            meta.grant_number = self.grant_number
        if not meta.license:
            meta.license = self.license
        if not meta.funder:
            meta.funder = self.funder
        # The DMP can assert personal data the REDCap dictionary failed to flag.
        if meta.personal_data is None:
            meta.personal_data = self.personal_data
        for keyword in self.keywords:
            if keyword not in meta.dmp_keywords:
                meta.dmp_keywords.append(keyword)
        project.provenance["dmp"] = self.title


def _language_code(rda_language: str) -> str:
    """RDA uses ISO 639-3 (spa, eng); language tags want ISO 639-1 (es, en).

    An unknown code gives an empty string rather than a truncation: truncating
    'LanguageEnum.spa' once produced the tag 'La'.
    """
    return language_tag(rda_language)


def _enum_value(value) -> str:
    """madmpy models controlled fields as enums; take the value, not the repr."""
    if value is None:
        return ""
    return str(getattr(value, "value", value) or "")


def _agent(node) -> Agent:
    if node is None:
        return Agent()
    name = getattr(node, "name", "") or ""
    mbox = getattr(node, "mbox", "") or ""
    ident = getattr(node, "contact_id", None) or getattr(node, "contributor_id", None)
    identifier = getattr(ident, "identifier", "") if ident else ""
    return Agent(name=name, email=str(mbox), identifier=str(identifier))


def _pick_dataset(dmp, project_title: str):
    """Match the maDMP dataset to the REDCap project, since a DMP can list several."""
    datasets = list(getattr(dmp, "dataset", None) or [])
    if not datasets:
        return None
    if len(datasets) == 1:
        return datasets[0]
    target = (project_title or "").strip().lower()
    if target:
        for ds in datasets:
            if (getattr(ds, "title", "") or "").strip().lower() == target:
                return ds
        for ds in datasets:
            if target in (getattr(ds, "title", "") or "").strip().lower():
                return ds
    return datasets[0]


def load(path: str | Path, project_title: str = "") -> DMPOverlay:
    """Read a maDMP JSON into an overlay. Requires the 'dmp' extra."""
    try:
        import madmpy
    except ImportError as exc: # pragma: no cover - optional dependency
        raise DMPUnavailable(
            "reading a DMP needs the 'dmp' extra: pip install 'redcap2hdcat[dmp]'"
        ) from exc

    dmp_cls = madmpy.load()
    import json as _json

    raw = _json.loads(Path(path).read_text(encoding="utf-8"))
    dmp = dmp_cls.DMP.model_validate(raw["dmp"])

    dataset = _pick_dataset(dmp, project_title)

    # Creator: prefer the first contributor, fall back to the DMP contact.
    contributors = list(getattr(dmp, "contributor", None) or [])
    creator = _agent(contributors[0]) if contributors else _agent(getattr(dmp, "contact", None))
    contact = _agent(getattr(dmp, "contact", None))

    grant_number = funder = ""
    projects = list(getattr(dmp, "project", None) or [])
    project_title_dmp = getattr(projects[0], "title", "") if projects else ""
    if projects:
        for funding in getattr(projects[0], "funding", None) or []:
            grant = getattr(funding, "grant_id", None)
            if grant:
                grant_number = str(getattr(grant, "identifier", "") or "")
            fid = getattr(funding, "funder_id", None)
            if fid:
                funder = str(getattr(fid, "identifier", "") or "")

    license_ref = ""
    personal = None
    keywords: list[str] = []
    if dataset is not None:
        keywords = [str(k) for k in (getattr(dataset, "keyword", None) or [])]
        pd = getattr(dataset, "personal_data", None)
        # madmpy may model this as an enum; compare on its value.
        pd_value = getattr(pd, "value", pd)
        personal = str(pd_value).lower() == "yes" if pd is not None else None
        for dist in getattr(dataset, "distribution", None) or []:
            for lic in getattr(dist, "license", None) or []:
                license_ref = str(getattr(lic, "license_ref", "") or "")

    ds_title = str(getattr(dataset, "title", "") if dataset else "")
    return DMPOverlay(
        title=ds_title or str(getattr(dmp, "title", "")),
        description=str(getattr(dataset, "description", "") if dataset else "")
        or str(getattr(dmp, "description", "") or ""),
        language=_enum_value(getattr(dataset, "language", None) if dataset else None)
        or _enum_value(getattr(dmp, "language", None)),
        issued=str(getattr(dataset, "issued", "") if dataset else ""),
        modified=str(getattr(dmp, "modified", "") or ""),
        creator=creator,
        contact=contact,
        grant_number=grant_number,
        funder=funder,
        project_title=str(project_title_dmp or ""),
        license=license_ref,
        keywords=keywords,
        personal_data=personal,
    )
