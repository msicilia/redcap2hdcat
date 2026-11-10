from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS

from redcap2hdcat.config import Config
from redcap2hdcat.core import rdf
from redcap2hdcat.core.validate import check_mandatory, validate
from redcap2hdcat.core.vocab import (
    CSVW,
    CV,
    DCAT,
    DCTERMS,
    DPV,
    DPV_PD,
    EHDS_LEGISLATION,
    HEALTHDCATAP,
)


class TestDatasetNode:
    def test_emits_one_dataset(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        assert len(list(g.subjects(RDF.type, DCAT.Dataset))) == 1

    def test_applicable_legislation_is_the_ehds_regulation(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        assert (None, None, URIRef(EHDS_LEGISLATION)) in g

    def test_uri_is_global_not_local(self, dictionary_project, full_config):
        uri = str(rdf.dataset_uri(full_config, dictionary_project))
        assert uri.startswith("https://redcap.example.org/dataset/")

    def test_personal_data_derived_from_identifier_flags(self, dictionary_project, full_config):
        # fecha_nacimiento is flagged in the fixture.
        g = rdf.build(dictionary_project, full_config)
        assert (None, DPV.hasPersonalData, None) in g

    def test_forms_become_keywords(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        keywords = {str(o) for o in g.objects(None, DCAT.keyword)}
        assert {"demographics", "clinical", "followup"} <= keywords


class TestCsvwLayer:
    def test_emits_a_table_group(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        assert len(list(g.subjects(RDF.type, CSVW.TableGroup))) == 1

    def test_one_column_per_exported_column(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        # 14 data columns and one status column per instrument.
        assert len(list(g.subjects(RDF.type, CSVW.Column))) == 14 + len(dictionary_project.forms)

    def test_declares_primary_key(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        assert str(next(g.objects(None, CSVW.primaryKey))) == "record_id"

    def test_dataset_links_its_variables(self, dictionary_project, full_config):
        # Release 8: healthdcatap:hasVariables, not dct:conformsTo (whose range is a
        # standard), and hasStructuredData true whenever variables are described.
        g = rdf.build(dictionary_project, full_config)
        assert (None, HEALTHDCATAP.hasVariables, None) in g
        assert (None, DCTERMS.conformsTo, None) not in g
        assert (None, HEALTHDCATAP.hasStructuredData, Literal(True)) in g

    def test_columns_use_csvw_title_and_always_have_a_description(
            self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        columns = list(g.subjects(RDF.type, CSVW.Column))
        assert not list(g.objects(None, CSVW.titles))
        assert all(g.value(c, CSVW.title) is not None for c in columns)
        assert all(g.value(c, DCTERMS.description) is not None for c in columns)

    def test_columns_hang_from_the_table(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        for table in g.subjects(RDF.type, CSVW.Table):
            assert list(g.objects(table, CSVW.column))

    def test_annotations_are_not_property_urls(self, tmp_path, full_config):
        path = tmp_path / "d.csv"
        path.write_text(
            "field_name,form_name,field_type,field_label,field_annotation\n"
            "record_id,f,text,Record ID,\n"
            "mes,f,text,Mes,@PLACEHOLDER='Month'\n"
        )
        from redcap2hdcat.adapters import csv_dict
        g = rdf.build(csv_dict.load(path), full_config)
        assert not list(g.objects(None, CSVW.propertyUrl))


class TestRelease8Values:
    def test_language_is_an_eu_language_iri(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        lang = URIRef("http://publications.europa.eu/resource/authority/language/ENG")
        assert set(g.objects(None, DCTERMS.language)) == {lang}
        assert (lang, RDF.type, DCTERMS.LinguisticSystem) in g

    def test_personal_data_are_dpv_categories(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        values = set(g.objects(rdf.dataset_uri(full_config, dictionary_project),
                               DPV.hasPersonalData))
        assert values and all(str(v).startswith(str(DPV_PD)) for v in values)
        assert DPV_PD.Health in values

    def test_agents_have_a_contact_point(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        for prop in (DCTERMS.publisher, HEALTHDCATAP.hdab):
            agent = next(g.objects(None, prop))
            contact = g.value(agent, CV.contactPoint)
            assert (contact, RDF.type, CV.ContactPoint) in g

    def test_distribution_from_access_url(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        dist = next(g.objects(None, DCAT.distribution))
        assert str(g.value(dist, DCAT.accessURL)) == full_config.access_url

    def test_provenance_and_type(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        uri = rdf.dataset_uri(full_config, dictionary_project)
        prov = g.value(uri, DCTERMS.provenance)
        assert (prov, RDF.type, DCTERMS.ProvenanceStatement) in g
        assert "REDCap" in str(g.value(prov, RDFS.label))
        assert str(g.value(uri, DCTERMS.type)) == full_config.dataset_type

    def test_missing_access_url_and_type_are_reported(self):
        gaps = Config().missing_mandatory()
        assert "dcat:distribution (access_url)" in gaps
        assert "dct:type (dataset_type)" in gaps


class TestConformance:
    def test_full_configuration_is_conformant(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        assert validate(g).conforms

    def test_empty_configuration_is_not(self, dictionary_project):
        g = rdf.build(dictionary_project, Config())
        missing = check_mandatory(g)
        assert "healthdcatap:hdab" in missing
        assert "healthdcatap:healthCategory" in missing

    def test_config_reports_its_own_gaps(self):
        # HDAB-ES is not designated yet; the tool must not invent the value.
        assert "healthdcatap:hdab" in Config().missing_mandatory()

    def test_serialises_to_turtle_and_jsonld(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        assert "dcat:Dataset" in g.serialize(format="turtle")
        assert g.serialize(format="json-ld").strip().startswith(("{", "["))


class TestCatalogue:
    def test_wraps_datasets(self, dictionary_project, full_config):
        uri = rdf.dataset_uri(full_config, dictionary_project)
        g = rdf.build_catalogue([uri], full_config)
        assert (None, RDF.type, DCAT.Catalog) in g
        assert (None, DCAT.dataset, uri) in g
