"""Serialisation to HealthDCAT-AP (dataset level) and CSVW (variable level).

Both layers land in different worlds from the same artefact.
"""

from __future__ import annotations

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, XSD

from ..config import Agent, Config
from ..model import Project
from . import snomed
from .columns import expand
from .vocab import (
    ACCESS_RIGHTS,
    ADMS,
    CSVW,
    DATA_THEME,
    DCAT,
    DCATAP,
    DCTERMS,
    DPV,
    EHDS_LEGISLATION,
    FOAF,
    HEALTHDCATAP,
    RDF,
    RDFS,
    SKOS,
    VCARD,
)

_LEGISLATION = URIRef(EHDS_LEGISLATION)


def bind_namespaces(g: Graph) -> None:
    for prefix, ns in [
        ("dcat", DCAT), ("dct", DCTERMS), ("dcatap", DCATAP), ("dpv", DPV),
        ("healthdcatap", HEALTHDCATAP), ("csvw", CSVW), ("adms", ADMS),
        ("vcard", VCARD), ("foaf", FOAF), ("owl", OWL),
    ]:
        g.bind(prefix, ns)


def _agent_node(g: Graph, agent: Agent, node_type=FOAF.Agent) -> BNode:
    node = BNode()
    g.add((node, RDF.type, node_type))
    if agent.name:
        g.add((node, FOAF.name, Literal(agent.name)))
    if agent.email:
        g.add((node, FOAF.mbox, URIRef(f"mailto:{agent.email}")))
    if agent.homepage:
        g.add((node, FOAF.homepage, URIRef(agent.homepage)))
    if agent.type:
        g.add((node, DCTERMS.type, URIRef(agent.type)))
    return node


def _contact_node(g: Graph, agent: Agent) -> BNode:
    """vcard:Kind. The mailto: prefix is mandatory."""
    node = BNode()
    g.add((node, RDF.type, VCARD.Kind))
    if agent.name:
        g.add((node, VCARD.fn, Literal(agent.name)))
    if agent.email:
        g.add((node, VCARD.hasEmail, URIRef(f"mailto:{agent.email}")))
    return node


def dataset_uri(config: Config, project: Project) -> URIRef:
    """Stable global URI. A REDCap project_id is only local to its instance."""
    pid = project.metadata.project_id or project.provenance.get("source_file", "unknown")
    return URIRef(f"{config.base_uri.rstrip('/')}/dataset/{pid}")


def build_dataset(g: Graph, project: Project, config: Config) -> URIRef:
    """Emit the dcat:Dataset node and return its URI."""
    meta = project.metadata
    uri = dataset_uri(config, project)
    lang = config.language

    g.add((uri, RDF.type, DCAT.Dataset))
    g.add((uri, DCATAP.applicableLegislation, _LEGISLATION))

    title = meta.title or project.provenance.get("source_file", "Untitled REDCap project")
    g.add((uri, DCTERMS.title, Literal(title, lang=lang)))

    description = meta.description or config.default_description or title
    g.add((uri, DCTERMS.description, Literal(description, lang=lang)))

    g.add((uri, DCTERMS.identifier, Literal(str(uri))))
    g.add((uri, DCTERMS.accessRights, ACCESS_RIGHTS[config.access_rights]))

    for category in config.health_categories:
        g.add((uri, HEALTHDCATAP.healthCategory, URIRef(category)))
    for theme in config.themes:
        g.add((uri, DCAT.theme, DATA_THEME[theme]))

    if config.publisher.name:
        g.add((uri, DCTERMS.publisher, _agent_node(g, config.publisher)))
    if config.hdab.name:
        g.add((uri, HEALTHDCATAP.hdab, _agent_node(g, config.hdab)))
    if config.contact.name or config.contact.email:
        g.add((uri, DCAT.contactPoint, _contact_node(g, config.contact)))
    elif meta.pi_email:
        g.add((uri, DCAT.contactPoint,
               _contact_node(g, Agent(name=meta.pi_name, email=meta.pi_email))))

    # The producer: from the project when the source knows it, otherwise from the
    # institutional configuration. File exports never carry it.
    if meta.pi_name:
        g.add((uri, DCTERMS.creator, _agent_node(g, Agent(name=meta.pi_name, email=meta.pi_email))))
    elif config.creator.name:
        g.add((uri, DCTERMS.creator, _agent_node(g, config.creator)))

    if meta.language or config.language:
        g.add((uri, DCTERMS.language, Literal(meta.language or config.language)))
    if meta.created:
        g.add((uri, DCTERMS.issued, Literal(meta.created, datatype=XSD.dateTime)))
    if meta.modified:
        g.add((uri, DCTERMS.modified, Literal(meta.modified, datatype=XSD.dateTime)))
    if meta.record_count is not None:
        g.add((uri, HEALTHDCATAP.numberOfRecords,
               Literal(meta.record_count, datatype=XSD.nonNegativeInteger)))
    if meta.unique_individual_count is not None:
        g.add((uri, HEALTHDCATAP.numberOfUniqueIndividuals,
               Literal(meta.unique_individual_count, datatype=XSD.nonNegativeInteger)))

    # Personal data: a flagged identifier implies it; a DMP may also assert it where
    # the REDCap dictionary failed to flag one.
    if meta.personal_data or any(v.identifier for v in project.variables):
        g.add((uri, DPV.hasPersonalData, Literal(True)))

    # Licence and funding come from the second source (a DMP), never from REDCap.
    if meta.license:
        g.add((uri, DCTERMS.license, URIRef(meta.license)))
    if meta.grant_number:
        g.add((uri, DCTERMS.isReferencedBy, Literal(meta.grant_number)))

    keywords = list(project.forms) + list(meta.dmp_keywords)
    for keyword in keywords:
        if keyword:
            g.add((uri, DCAT.keyword, Literal(keyword, lang=lang)))

    if meta.source_system_version:
        g.add((uri, ADMS.versionNotes,
               Literal(f"{meta.source_system} {meta.source_system_version}")))

    return uri


def _emit_column(g: Graph, schema: BNode, column, lang: str) -> None:
    node = BNode()
    g.add((schema, CSVW.column, node))
    g.add((node, RDF.type, CSVW.Column))
    g.add((node, CSVW.name, Literal(column.name)))
    g.add((node, CSVW.titles, Literal(column.title, lang=lang)))
    if column.description:
        g.add((node, DCTERMS.description, Literal(column.description, lang=lang)))
    g.add((node, CSVW.datatype, Literal(column.datatype)))
    # The original REDCap widget, kept so the catalogue can show real structure.
    if column.redcap_type:
        g.add((node, DCTERMS.type, Literal(column.redcap_type)))
    if column.required:
        g.add((node, CSVW.required, Literal(True)))
    # Column-level PII label; OpenMetadata and DataHub consume this natively.
    if column.identifier:
        g.add((node, DPV.hasPersonalData, Literal(True)))
    if column.property_url:
        g.add((node, CSVW.propertyUrl, Literal(column.property_url)))
    # The calculation formula, over internal field names (calc fields only).
    if column.calculation:
        g.add((node, RDFS.comment, Literal(column.calculation)))
    # Redundant with the table grouping below, but kept for flat consumers.
    if column.form:
        g.add((node, DCTERMS.isPartOf, Literal(column.form)))
    for code, label in column.choices:
        g.add((node, SKOS.notation, Literal(f"{code} = {label}")))
    # Field-level semantic coding, terminology-agnostic (SNOMED, LOINC, ICD-10...).
    for coding in column.codings:
        # A resolvable URI for a plain code; a blank node for an expression.
        concept = URIRef(coding.uri) if coding.uri else BNode()
        g.add((node, SKOS.exactMatch, concept))
        g.add((concept, SKOS.notation, Literal(coding.pill)))
        if coding.display:
            g.add((concept, RDFS.label, Literal(coding.display)))
        if coding.version:
            g.add((concept, OWL.versionInfo, Literal(coding.version)))


def build_csvw(
    g: Graph, project: Project, config: Config, dataset: URIRef, snomed_demo: bool = False
) -> URIRef:
    """Emit the variable-level csvw:TableGroup.

    A REDCap project is several related instruments sharing a record identifier, so
    each form becomes its own csvw:Table within the group rather than flattening
    everything into one. This makes the project's structure first-class in the export.
    """
    table_group = URIRef(f"{dataset}/dictionary")
    g.add((table_group, RDF.type, CSVW.TableGroup))
    g.add((dataset, DCTERMS.conformsTo, table_group))

    # Preserve form order as encountered in the export.
    forms: dict[str, list] = {}
    for column in expand(project, snomed_demo=snomed_demo):
        forms.setdefault(column.form, []).append(column)

    systems_used: set[str] = set()
    record_id = project.record_id_field
    for index, (form, columns) in enumerate(forms.items()):
        table = URIRef(f"{table_group}/table-{index}")
        schema = BNode()
        g.add((table_group, CSVW.table, table))
        g.add((table, RDF.type, CSVW.Table))
        # The instrument name is the meaningful structure for a catalogue reader.
        if form:
            g.add((table, DCTERMS.title, Literal(form, lang=config.language)))
        g.add((table, CSVW.tableSchema, schema))
        g.add((schema, RDF.type, CSVW.Schema))
        for column in columns:
            _emit_column(g, schema, column, config.language)
            if column.name == record_id:
                g.add((schema, CSVW.primaryKey, Literal(record_id)))
            for coding in column.codings:
                systems_used.add(coding.system)
                # Form-level subject: the concepts its fields carry.
                g.add((table, DCTERMS.subject, URIRef(coding.uri)))

    # Dataset-level: declare which coding systems are in use (EHDS Art. 51 style).
    for system in sorted(systems_used):
        wikidata = snomed.CODING_SYSTEM_WIKIDATA.get(system)
        if wikidata:
            g.add((dataset, HEALTHDCATAP.hasCodingSystem, URIRef(wikidata)))

    return table_group


def build(project: Project, config: Config, snomed_demo: bool = False) -> Graph:
    """Full record: dataset node plus its CSVW dictionary."""
    g = Graph()
    bind_namespaces(g)
    dataset = build_dataset(g, project, config)
    build_csvw(g, project, config, dataset, snomed_demo=snomed_demo)
    return g


def build_catalogue(datasets: list[URIRef], config: Config) -> Graph:
    """The dcat:Catalog wrapper the harvester consumes."""
    g = Graph()
    bind_namespaces(g)
    uri = URIRef(f"{config.base_uri.rstrip('/')}/catalogue")
    g.add((uri, RDF.type, DCAT.Catalog))
    g.add((uri, DCTERMS.title, Literal(config.catalogue_title, lang=config.language)))
    g.add((uri, DCTERMS.description,
           Literal(config.catalogue_description or config.catalogue_title, lang=config.language)))
    g.add((uri, DCATAP.applicableLegislation, _LEGISLATION))
    g.add((uri, DCAT.themeTaxonomy, URIRef(str(DATA_THEME).rstrip("/"))))
    if config.publisher.name:
        g.add((uri, DCTERMS.publisher, _agent_node(g, config.publisher)))
    for dataset in datasets:
        g.add((uri, DCAT.dataset, dataset))
    return g
