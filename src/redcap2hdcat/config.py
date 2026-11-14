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
    # Organisation accountable for the dataset (geodcatap:custodian), when not the publisher.
    custodian: Agent = field(default_factory=Agent)
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
        """Read the settings from YAML, or from RDF (Turtle and other syntaxes).

        The RDF form is a partial HealthDCAT-AP record: the institution's dcat:Catalog
        and one dcat:Dataset node linked from it, whose values are the defaults for
        every dataset of the institution. See TEMPLATE_TTL and MAPPING.md 9.
        """
        path = Path(path)
        if path.suffix.lower() in _RDF_SUFFIXES:
            from rdflib import Graph
            return cls.from_graph(Graph().parse(path))
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        agents = {
            key: Agent(**(raw.pop(key, None) or {}))
            for key in ("publisher", "hdab", "contact", "creator", "custodian")
        }
        known = {f for f in cls.__dataclass_fields__ if f not in agents}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"unknown configuration keys: {sorted(unknown)}")
        return cls(**{k: v for k, v in raw.items() if k in known}, **agents)

    @classmethod
    def from_graph(cls, g) -> Config:
        """Settings from an RDF graph holding one dcat:Catalog (see load)."""
        from rdflib import Literal
        from rdflib.namespace import DCAT, DCTERMS, FOAF, RDF, RDFS, SKOS

        from .core.vocab import GEODCATAP, HEALTHDCATAP, VCARD, language_tag

        catalogues = list(g.subjects(RDF.type, DCAT.Catalog))
        if len(catalogues) != 1:
            raise ValueError("the settings graph must describe exactly one dcat:Catalog")
        cat = catalogues[0]

        def text(s, p) -> str:
            v = g.value(s, p)
            return str(v) if v is not None else ""

        def last(iri) -> str:
            return str(iri).rstrip("/").rsplit("/", 1)[-1]

        def agent(node) -> Agent:
            if node is None:
                return Agent()
            return Agent(name=text(node, FOAF.name),
                         email=text(node, FOAF.mbox).removeprefix("mailto:"),
                         homepage=text(node, FOAF.homepage),
                         identifier=text(node, DCTERMS.identifier),
                         type=text(node, DCTERMS.type))

        def contact(node) -> Agent:
            if node is None:
                return Agent()
            return Agent(name=text(node, VCARD.fn),
                         email=text(node, VCARD.hasEmail).removeprefix("mailto:"))

        base = str(cat)
        if base.endswith("/catalogue"):
            base = base[: -len("/catalogue")]
        kw: dict = {"base_uri": base,
                    "catalogue_title": text(cat, DCTERMS.title),
                    "catalogue_description": text(cat, DCTERMS.description),
                    "publisher": agent(g.value(cat, DCTERMS.publisher))}
        lang = g.value(cat, DCTERMS.language)
        if lang is not None:
            kw["language"] = language_tag(last(lang).lower()) or str(lang)
        contact_node = g.value(cat, DCAT.contactPoint)

        defaults = next((d for d in g.objects(cat, DCAT.dataset)
                         if (d, RDF.type, DCAT.Dataset) in g), None)
        if defaults is not None:
            contact_node = g.value(defaults, DCAT.contactPoint) or contact_node
            rights = g.value(defaults, DCTERMS.accessRights)
            if rights is not None:
                kw["access_rights"] = last(rights)
            kw["health_categories"] = sorted(
                str(o) for o in g.objects(defaults, HEALTHDCATAP.healthCategory))
            themes = sorted(last(o) for o in g.objects(defaults, DCAT.theme))
            if themes:
                kw["themes"] = themes
            dtype = g.value(defaults, DCTERMS.type)
            if dtype is not None:
                kw["dataset_type"] = str(dtype)
                kw["dataset_type_label"] = text(dtype, SKOS.prefLabel)
            kw["hdab"] = agent(g.value(defaults, HEALTHDCATAP.hdab))
            kw["custodian"] = agent(g.value(defaults, GEODCATAP.custodian))
            kw["creator"] = agent(g.value(defaults, DCTERMS.creator))
            kw["default_description"] = text(defaults, DCTERMS.description)
            dist = g.value(defaults, DCAT.distribution)
            if dist is not None:
                kw["access_url"] = text(dist, DCAT.accessURL)
            prov = g.value(defaults, DCTERMS.provenance)
            if isinstance(prov, Literal):
                kw["provenance"] = str(prov)
            elif prov is not None:
                kw["provenance"] = text(prov, RDFS.label)
        kw["contact"] = contact(contact_node)
        return cls(**kw)

    def to_graph(self):
        """The settings as a partial HealthDCAT-AP record (inverse of from_graph)."""
        from rdflib import BNode, Graph, Literal, URIRef
        from rdflib.namespace import DCAT, DCTERMS, FOAF, RDF, RDFS, SKOS

        from .core.rdf import bind_namespaces
        from .core.vocab import (
            ACCESS_RIGHTS,
            DATA_THEME,
            GEODCATAP,
            HEALTHDCATAP,
            VCARD,
            language_iri,
            language_tag,
        )

        g = Graph()
        bind_namespaces(g)
        lang = language_tag(self.language) or self.language
        base = self.base_uri.rstrip("/")

        def agent(a: Agent) -> BNode:
            node = BNode()
            g.add((node, RDF.type, FOAF.Agent))
            if a.name:
                g.add((node, FOAF.name, Literal(a.name)))
            if a.email:
                g.add((node, FOAF.mbox, URIRef(f"mailto:{a.email}")))
            if a.homepage:
                g.add((node, FOAF.homepage, URIRef(a.homepage)))
            if a.identifier:
                g.add((node, DCTERMS.identifier, Literal(a.identifier)))
            if a.type:
                g.add((node, DCTERMS.type, URIRef(a.type)))
            return node

        cat = URIRef(f"{base}/catalogue")
        g.add((cat, RDF.type, DCAT.Catalog))
        if self.catalogue_title:
            g.add((cat, DCTERMS.title, Literal(self.catalogue_title, lang=lang)))
        if self.catalogue_description:
            g.add((cat, DCTERMS.description, Literal(self.catalogue_description, lang=lang)))
        if language_iri(self.language):
            g.add((cat, DCTERMS.language, URIRef(language_iri(self.language))))
        if self.publisher.name or self.publisher.email:
            g.add((cat, DCTERMS.publisher, agent(self.publisher)))

        ds = URIRef(f"{base}/dataset-defaults")
        g.add((cat, DCAT.dataset, ds))
        g.add((ds, RDF.type, DCAT.Dataset))
        g.add((ds, DCTERMS.accessRights, ACCESS_RIGHTS[self.access_rights]))
        for category in self.health_categories:
            g.add((ds, HEALTHDCATAP.healthCategory, URIRef(category)))
        for theme in self.themes:
            g.add((ds, DCAT.theme, DATA_THEME[theme]))
        if self.dataset_type:
            concept = URIRef(self.dataset_type)
            g.add((ds, DCTERMS.type, concept))
            g.add((concept, RDF.type, SKOS.Concept))
            if self.dataset_type_label:
                g.add((concept, SKOS.prefLabel, Literal(self.dataset_type_label, lang=lang)))
        for pred, a in ((HEALTHDCATAP.hdab, self.hdab), (GEODCATAP.custodian, self.custodian),
                        (DCTERMS.creator, self.creator)):
            if a.name or a.email:
                g.add((ds, pred, agent(a)))
        if self.contact.name or self.contact.email:
            cp = BNode()
            g.add((ds, DCAT.contactPoint, cp))
            g.add((cp, RDF.type, VCARD.Kind))
            if self.contact.name:
                g.add((cp, VCARD.fn, Literal(self.contact.name)))
            if self.contact.email:
                g.add((cp, VCARD.hasEmail, URIRef(f"mailto:{self.contact.email}")))
        if self.default_description:
            g.add((ds, DCTERMS.description, Literal(self.default_description, lang=lang)))
        if self.access_url:
            dist = BNode()
            g.add((ds, DCAT.distribution, dist))
            g.add((dist, RDF.type, DCAT.Distribution))
            g.add((dist, DCAT.accessURL, URIRef(self.access_url)))
        if self.provenance:
            prov = BNode()
            g.add((ds, DCTERMS.provenance, prov))
            g.add((prov, RDF.type, DCTERMS.ProvenanceStatement))
            g.add((prov, RDFS.label, Literal(self.provenance, lang="en")))
        return g

    def to_turtle(self) -> str:
        return self.to_graph().serialize(format="turtle")

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


_RDF_SUFFIXES = {".ttl", ".turtle", ".n3", ".nt", ".rdf", ".jsonld"}


def _placeholder_values() -> frozenset[str]:
    """Human-facing strings the template ships, so an unedited value is spotted."""
    data = yaml.safe_load(TEMPLATE) or {}
    out: set[str] = set()
    for key in ("catalogue_title", "catalogue_description"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            out.add(value.strip())
    for key in ("publisher", "creator", "contact", "hdab", "custodian"):
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

# Organisation accountable for the dataset (geodcatap:custodian), if different from
# the publisher. Recommended; leave blank to omit.
custodian:
  name: ""
  email: ""
"""

# The same settings as a partial HealthDCAT-AP record. Every key of the YAML form is a
# DCAT-AP or HealthDCAT-AP property of the institution's catalogue or of the dataset node
# that holds the defaults, so the file can be validated and reused like any other record.
TEMPLATE_TTL = """\
# Institutional settings for redcap2hdcat, as a partial HealthDCAT-AP record.
# Fill once, reuse for every project. YAML with the same content is also accepted
# (redcap2hdcat init-config --format yaml).
@prefix dcat:         <http://www.w3.org/ns/dcat#> .
@prefix dct:          <http://purl.org/dc/terms/> .
@prefix foaf:         <http://xmlns.com/foaf/0.1/> .
@prefix vcard:        <http://www.w3.org/2006/vcard/ns#> .
@prefix skos:         <http://www.w3.org/2004/02/skos/core#> .
@prefix healthdcatap: <http://healthdataportal.eu/ns/health#> .
@prefix geodcatap:    <http://data.europa.eu/930/> .
@prefix access:       <http://publications.europa.eu/resource/authority/access-right/> .
@prefix theme:        <http://publications.europa.eu/resource/authority/data-theme/> .
@prefix lang:         <http://publications.europa.eu/resource/authority/language/> .
@prefix healthcat:
    <https://hdeu-dcat.data.health.europa.eu/resource/authority/healthcategories/> .
@prefix pubtype:      <https://hdeu-dcat.data.health.europa.eu/resource/authority/publisher-type/> .

# The institution's catalogue. Its IRI, without the final "/catalogue", is the base of
# every dataset identifier.
<https://redcap.example.org/catalogue> a dcat:Catalog ;
    dct:title "Dataset catalogue of Example Institute"@en ;
    dct:description "Datasets held by Example Institute under Article 77 EHDS."@en ;
    dct:language lang:ENG ;
    dct:publisher [ a foaf:Agent ;
        foaf:name "Example Institute" ;
        foaf:mbox <mailto:data@example.org> ;
        foaf:homepage <https://example.org> ;
        dct:type pubtype:research-institute-org ] ;
    dcat:dataset <https://redcap.example.org/dataset-defaults> .

# Defaults for every dataset of the institution. A project or a plan may override them.
<https://redcap.example.org/dataset-defaults> a dcat:Dataset ;
    # NAL access right. NON_PUBLIC is the correct default for clinical research data:
    # Article 77 is about describing datasets, not granting access.
    dct:accessRights access:NON_PUBLIC ;
    # EHDS Article 51 categories, from the HealthDCAT-AP vocabulary. Mandatory.
    healthdcatap:healthCategory healthcat:EHRS ;
    dcat:theme theme:HEAL ;
    # dct:type: a SKOS concept, mandatory for non-public datasets. The EU dataset-type
    # table has no concept for research data; a concept of the institution's own
    # vocabulary is allowed. Uncomment and set:
    # dct:type <https://redcap.example.org/concept/research-data> ;
    # Producer of the data: the research group or unit. A file export carries no
    # principal investigator, so it has to be stated here.
    dct:creator [ a foaf:Agent ; foaf:name "Grupo de investigacion" ;
                  foaf:mbox <mailto:pi@example.org> ] ;
    dcat:contactPoint [ a vcard:Kind ; vcard:fn "Data Protection Office" ;
                        vcard:hasEmail <mailto:dpo@example.org> ] ;
    # Health Data Access Body. HDAB-ES is still being set up: leave out until designated.
    # healthdcatap:hdab [ a foaf:Agent ; foaf:name "" ; foaf:mbox <mailto:> ] ;
    # Organisation accountable for the dataset, if different from the publisher.
    # geodcatap:custodian [ a foaf:Agent ; foaf:name "" ] ;
    # Page where a data user requests access (becomes the dcat:Distribution). Mandatory.
    dcat:distribution [ a dcat:Distribution ;
                        dcat:accessURL <https://example.org/data-access-request> ] .
"""

# Computed once, after TEMPLATE is defined.
_PLACEHOLDER_VALUES = _placeholder_values()
