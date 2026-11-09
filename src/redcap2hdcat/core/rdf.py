"""Serialisation to HealthDCAT-AP (dataset level) and CSVW (variable level).

Both layers land in different worlds from the same artefact. The target is the
non-public profile of HealthDCAT-AP Release 8; see MAPPING.md for the property list.
"""

from __future__ import annotations

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, PROV, XSD

from ..config import Agent, Config
from ..model import Project
from . import snomed
from .columns import expand
from .vocab import (
    ACCESS_RIGHTS,
    ADMS,
    CSVW,
    CV,
    DATA_THEME,
    DCAT,
    DCATAP,
    DCTERMS,
    DPV,
    DPV_PD,
    EHDS_LEGISLATION,
    ELI,
    FILE_TYPE,
    FOAF,
    HEALTHDCATAP,
    RDF,
    RDFS,
    SKOS,
    VCARD,
    datatype_for,
    language_iri,
    language_tag,
    personal_data_category,
)

_LEGISLATION = URIRef(EHDS_LEGISLATION)
# HealthDCAT-AP Health Activity table: the dataset production context of a project
# described in a DMP.
HEALTH_ACTIVITY_RESEARCH_PROJECT = URIRef(
    "https://hdeu-dcat.data.health.europa.eu/resource/authority/health-activity/RESEARCH_PROJECT")


def bind_namespaces(g: Graph) -> None:
    for prefix, ns in [
        ("dcat", DCAT), ("dct", DCTERMS), ("dcatap", DCATAP), ("dpv", DPV),
        ("dpv-pd", DPV_PD), ("healthdcatap", HEALTHDCATAP), ("csvw", CSVW), ("adms", ADMS),
        ("vcard", VCARD), ("foaf", FOAF), ("owl", OWL), ("cv", CV), ("eli", ELI),
        ("prov", PROV),
    ]:
        g.bind(prefix, ns)


def _agent_node(g: Graph, agent: Agent, node_type=FOAF.Agent) -> BNode:
    """foaf:Agent with the cv:ContactPoint that Release 8 requires of a publisher or HDAB."""
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
    if agent.email or agent.homepage:
        contact = BNode()
        g.add((node, CV.contactPoint, contact))
        g.add((contact, RDF.type, CV.ContactPoint))
        if agent.email:
            g.add((contact, CV.email, Literal(agent.email)))
        if agent.homepage:
            g.add((contact, CV.contactPage, URIRef(agent.homepage)))
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


def _typed(g: Graph, iri: URIRef, cls: URIRef) -> URIRef:
    """State the class of a vocabulary IRI.

    Release 8 checks the class of the values of dct:accessRights,
    dcatap:applicableLegislation, dct:language and dpv:hasPersonalData, and the
    published vocabularies type their entries only as skos:Concept, so the record
    states the class itself, as DCAT-AP records usually do.
    """
    g.add((iri, RDF.type, cls))
    return iri


def _is_iri(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def dataset_uri(config: Config, project: Project) -> URIRef:
    """Stable global URI. A REDCap project_id is only local to its instance."""
    pid = project.metadata.project_id or project.provenance.get("source_file", "unknown")
    return URIRef(f"{config.base_uri.rstrip('/')}/dataset/{pid}")


def provenance_statement(project: Project, config: Config) -> str:
    """A factual account of where the data and this description come from."""
    if config.provenance:
        return config.provenance
    meta = project.metadata
    system = " ".join(x for x in (meta.source_system or "REDCap", meta.source_system_version) if x)
    forms = len(project.forms)
    text = (f"Data captured through electronic case report forms in {system} "
            f"({forms} instrument{'s' if forms != 1 else ''}")
    if project.events:
        text += f", {len(project.events)} longitudinal events"
    text += "). "
    source = {"odm": "Project XML export", "csv_dict": "data dictionary"}.get(
        project.provenance.get("adapter", ""), "metadata export")
    text += f"This description was derived from the project's {source} by redcap2hdcat"
    if project.provenance.get("dmp"):
        text += " and completed from the study's data management plan"
    return text + "."


def personal_data_categories(project: Project) -> list[str]:
    """DPV personal-data categories for the dataset, or none.

    Personal data are present when REDCap flags a field as an identifier or a DMP
    says so. A dataset of a health research project that holds personal data holds
    health data, so dpv-pd:Health is always among the categories; flagged fields add
    the category their validation type implies.
    """
    meta = project.metadata
    flagged = [v for v in project.variables if v.identifier]
    if not flagged and not meta.personal_data:
        return []
    categories = [str(DPV_PD["Health"])]
    for var in flagged:
        cat = personal_data_category(var.validation, datatype_for(var.field_type.value,
                                                                  var.validation))
        if cat not in categories:
            categories.append(cat)
    return categories


def build_dataset(g: Graph, project: Project, config: Config) -> URIRef:
    """Emit the dcat:Dataset node and return its URI."""
    meta = project.metadata
    uri = dataset_uri(config, project)
    lang = language_tag(config.language) or config.language

    g.add((uri, RDF.type, DCAT.Dataset))
    g.add((uri, DCATAP.applicableLegislation, _typed(g, _LEGISLATION, ELI.LegalResource)))

    title = meta.title or project.provenance.get("source_file", "Untitled REDCap project")
    g.add((uri, DCTERMS.title, Literal(title, lang=lang)))

    description = meta.description or config.default_description or title
    desc_lang = meta.dmp_text_language if meta.description and meta.dmp_text_language else lang
    g.add((uri, DCTERMS.description, Literal(description, lang=desc_lang)))

    g.add((uri, DCTERMS.identifier, Literal(str(uri))))
    g.add((uri, DCTERMS.accessRights,
           _typed(g, ACCESS_RIGHTS[config.access_rights], DCTERMS.RightsStatement)))
    if config.dataset_type:
        concept = _typed(g, URIRef(config.dataset_type), SKOS.Concept)
        g.add((uri, DCTERMS.type, concept))
        if config.dataset_type_label:
            g.add((concept, SKOS.prefLabel, Literal(config.dataset_type_label, lang=lang)))

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

    language = language_iri(meta.language or config.language)
    if language:
        g.add((uri, DCTERMS.language, _typed(g, URIRef(language), DCTERMS.LinguisticSystem)))
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

    for category in personal_data_categories(project):
        g.add((uri, DPV.hasPersonalData, _typed(g, URIRef(category), DPV.PersonalData)))

    provenance = BNode()
    g.add((uri, DCTERMS.provenance, provenance))
    g.add((provenance, RDF.type, DCTERMS.ProvenanceStatement))
    g.add((provenance, RDFS.label, Literal(provenance_statement(project, config), lang="en")))

    # The research project that generated the data, from the DMP.
    if meta.project_title:
        activity = BNode()
        g.add((uri, PROV.wasGeneratedBy, activity))
        g.add((activity, RDF.type, PROV.Activity))
        g.add((activity, DCTERMS.type, HEALTH_ACTIVITY_RESEARCH_PROJECT))
        g.add((activity, DCTERMS.title,
               Literal(meta.project_title, lang=meta.dmp_text_language or lang)))
        if meta.grant_number:
            g.add((activity, DCTERMS.identifier, Literal(meta.grant_number)))

    # Funding comes from the second source (a DMP), never from REDCap. The licence,
    # also from the DMP, belongs to the distribution.
    if meta.grant_number and _is_iri(meta.grant_number):
        g.add((uri, DCTERMS.isReferencedBy, URIRef(meta.grant_number)))

    for keyword in project.forms:
        if keyword:
            g.add((uri, DCAT.keyword, Literal(keyword, lang=lang)))
    for keyword in meta.dmp_keywords:
        if keyword:
            g.add((uri, DCAT.keyword, Literal(keyword, lang=meta.dmp_text_language or lang)))

    if meta.source_system_version:
        g.add((uri, ADMS.versionNotes,
               Literal(f"{meta.source_system} {meta.source_system_version}")))

    if config.access_url:
        build_distribution(g, uri, config, lang, license_iri=meta.license)

    return uri


def build_distribution(g: Graph, dataset: URIRef, config: Config, lang: str,
                       license_iri: str = "") -> URIRef:
    """The one distribution a REDCap project has: record-level data on request.

    The access URL is the page where access is requested, not a download.
    """
    dist = URIRef(f"{dataset}/distribution")
    g.add((dataset, DCAT.distribution, dist))
    g.add((dist, RDF.type, DCAT.Distribution))
    g.add((dist, DCAT.accessURL, URIRef(config.access_url)))
    g.add((dist, DCATAP.applicableLegislation, _LEGISLATION))
    g.add((dist, DCTERMS.format, _typed(g, FILE_TYPE.CSV, DCTERMS.MediaTypeOrExtent)))
    g.add((dist, DCTERMS.title, Literal("Record-level data, on request", lang="en")))
    if license_iri:
        g.add((dist, DCTERMS.license, _typed(g, URIRef(license_iri), DCTERMS.LicenseDocument)))
    return dist


def _emit_column(g: Graph, table: URIRef, schema: BNode, column, lang: str) -> None:
    node = BNode()
    # Release 8 reads columns from the table; CSVW metadata from the table schema.
    g.add((table, CSVW.column, node))
    g.add((schema, CSVW.column, node))
    g.add((node, RDF.type, CSVW.Column))
    g.add((node, CSVW.name, Literal(column.name)))
    g.add((node, CSVW.title, Literal(column.title, lang=lang)))
    # Release 8 requires a description on every column; the field note when REDCap
    # has one, otherwise the label.
    g.add((node, DCTERMS.description, Literal(column.description or column.title, lang=lang)))
    g.add((node, CSVW.datatype, Literal(column.datatype)))
    # The original REDCap widget, kept so the catalogue can show real structure.
    if column.redcap_type:
        g.add((node, DCTERMS.type, Literal(column.redcap_type)))
    if column.required:
        g.add((node, CSVW.required, Literal(True)))
    # Column-level personal-data label; OpenMetadata and DataHub consume this natively.
    if column.identifier:
        category = personal_data_category(column.validation, column.datatype)
        g.add((node, DPV.hasPersonalData, URIRef(category)))
    if column.property_url and _is_iri(column.property_url):
        g.add((node, CSVW.propertyUrl, URIRef(column.property_url)))
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
    lang = language_tag(config.language) or config.language
    table_group = URIRef(f"{dataset}/dictionary")
    g.add((table_group, RDF.type, CSVW.TableGroup))
    title = project.metadata.title or project.provenance.get("source_file", "REDCap project")
    g.add((table_group, DCTERMS.title, Literal(f"Data dictionary of {title}", lang=lang)))
    g.add((dataset, HEALTHDCATAP.hasVariables, table_group))
    g.add((dataset, HEALTHDCATAP.hasStructuredData, Literal(True)))

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
        g.add((table, DCTERMS.title, Literal(form or f"table-{index}", lang=lang)))
        g.add((table, CSVW.tableSchema, schema))
        g.add((schema, RDF.type, CSVW.Schema))
        for column in columns:
            _emit_column(g, table, schema, column, lang)
            if column.name == record_id:
                g.add((schema, CSVW.primaryKey, Literal(record_id)))
            for coding in column.codings:
                systems_used.add(coding.system)
                # Form-level subject: the concepts its fields carry.
                if coding.uri:
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
    lang = language_tag(config.language) or config.language
    uri = URIRef(f"{config.base_uri.rstrip('/')}/catalogue")
    g.add((uri, RDF.type, DCAT.Catalog))
    g.add((uri, DCTERMS.title, Literal(config.catalogue_title, lang=lang)))
    g.add((uri, DCTERMS.description,
           Literal(config.catalogue_description or config.catalogue_title, lang=lang)))
    g.add((uri, DCATAP.applicableLegislation, _LEGISLATION))
    g.add((uri, DCAT.themeTaxonomy, URIRef(str(DATA_THEME).rstrip("/"))))
    if config.publisher.name:
        g.add((uri, DCTERMS.publisher, _agent_node(g, config.publisher)))
    for dataset in datasets:
        g.add((uri, DCAT.dataset, dataset))
    return g
