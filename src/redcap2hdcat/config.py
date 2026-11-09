"""Institutional configuration.

Holds what REDCap cannot supply. Set once per institution, not per project
this is what makes the marginal cost of the 200th project small.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Agent:
    """A publisher, creator or health data access body."""

    name: str = ""
    email: str = ""
    homepage: str = ""
    identifier: str = ""
    type: str = ""


@dataclass
class Config:
    """Everything the human supplies."""

    base_uri: str = "https://example.org"
    catalogue_title: str = "Institutional dataset catalogue"
    catalogue_description: str = ""
    language: str = "en"
    access_rights: str = "NON_PUBLIC"
    health_categories: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=lambda: ["HEAL"])
    publisher: Agent = field(default_factory=Agent)
    # Mandatory in the specification, but HDAB-ES is not yet designated.
    # Left empty rather than invented.
    hdab: Agent = field(default_factory=Agent)
    contact: Agent = field(default_factory=Agent)
    # The producer of the data. File exports carry no principal investigator, so
    # this comes from configuration until the API adapter exists.
    creator: Agent = field(default_factory=Agent)
    default_description: str = ""
    # Where a data user requests access: the institution's data-request page or, once
    # designated, the HDAB's. HealthDCAT-AP needs at least one dcat:Distribution and
    # REDCap knows nothing about access procedures, so this has to be configured.
    access_url: str = ""
    # dct:type of each dataset, a SKOS concept (mandatory for non-public datasets in
    # Release 8). The recommended EU dataset-type table has no concept for research
    # data collected on case report forms, so the tool does not choose one.
    dataset_type: str = ""
    # Label of that concept, needed when it is the institution's own and no published
    # vocabulary supplies its skos:prefLabel.
    dataset_type_label: str = ""
    # Overrides the provenance statement the tool composes from the REDCap export.
    provenance: str = ""

    @classmethod
    def load(cls, path: str | Path) -> Config:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        agents = {
            key: Agent(**(raw.pop(key, None) or {}))
            for key in ("publisher", "hdab", "contact", "creator")
        }
        known = {f for f in cls.__dataclass_fields__ if f not in agents}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"unknown configuration keys: {sorted(unknown)}")
        return cls(**{k: v for k, v in raw.items() if k in known}, **agents)

    def missing_mandatory(self) -> list[str]:
        """Mandatory HealthDCAT-AP properties this configuration cannot fill."""
        gaps = []
        if not self.health_categories:
            gaps.append("healthdcatap:healthCategory")
        if not self.hdab.name:
            gaps.append("healthdcatap:hdab")
        if not self.publisher.name:
            gaps.append("dct:publisher")
        if not self.access_url:
            gaps.append("dcat:distribution (access_url)")
        if not self.dataset_type:
            gaps.append("dct:type (dataset_type)")
        return gaps


def _placeholder_values() -> frozenset[str]:
    """Human-facing strings the template ships, so an unedited value is spotted."""
    data = yaml.safe_load(TEMPLATE) or {}
    out: set[str] = set()
    for key in ("catalogue_title", "catalogue_description"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            out.add(value.strip())
    for key in ("publisher", "creator", "contact", "hdab"):
        for value in (data.get(key) or {}).values():
            if isinstance(value, str) and value.strip():
                out.add(value.strip())
    return frozenset(out)


def is_placeholder(value: str) -> bool:
    """True when a value is an unedited template default or an example.org address."""
    if not value:
        return False
    text = str(value).strip()
    if text in _PLACEHOLDER_VALUES:
        return True
    low = text.lower()
    return "example.org" in low or "example.com" in low


TEMPLATE = """\
# Institutional configuration for redcap2hdcat. Fill once, reuse for every project.
base_uri: https://redcap.example.org
catalogue_title: Dataset catalogue of Example Institute
catalogue_description: Datasets held by Example Institute under Article 77 EHDS.
language: en

# NAL access-right. NON_PUBLIC is the correct default for clinical research data:
# Article 77 is about describing datasets, not granting access.
access_rights: NON_PUBLIC

# EHDS Article 51 categories, from the HealthDCAT-AP vocabulary. Mandatory.
health_categories:
  - "https://hdeu-dcat.data.health.europa.eu/resource/authority/healthcategories/EHRS"

themes:
  - HEAL

# Page where a data user requests access (becomes the dcat:Distribution). Mandatory.
access_url: https://example.org/data-access-request

# dct:type of the datasets: a SKOS concept, mandatory for non-public datasets. The EU
# dataset-type table (http://publications.europa.eu/resource/authority/dataset-type)
# is recommended but has no concept for research data; a concept from the
# institution's own vocabulary is allowed.
dataset_type: ""

publisher:
  name: Example Institute
  email: data@example.org
  homepage: https://example.org
  type: https://hdeu-dcat.data.health.europa.eu/resource/authority/publisher-type/research-institute-org

# Producer of the data: the research group or unit that generated it. A file
# export carries no principal investigator, so it has to be stated here.
creator:
  name: Grupo de investigacion
  email: pi@example.org

# Health Data Access Body. HDAB-ES is still being set up: leave blank until
# designated rather than inventing a value.
hdab:
  name: ""
  email: ""

contact:
  name: Data Protection Office
  email: dpo@example.org
"""

# Computed once, after TEMPLATE is defined.
_PLACEHOLDER_VALUES = _placeholder_values()
