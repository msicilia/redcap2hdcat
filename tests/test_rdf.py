from rdflib import URIRef
from rdflib.namespace import RDF

from redcap2hdcat.config import Config
from redcap2hdcat.core import rdf
from redcap2hdcat.core.validate import check_mandatory, validate
from redcap2hdcat.core.vocab import CSVW, DCAT, DCTERMS, DPV, EHDS_LEGISLATION


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
        assert len(list(g.subjects(RDF.type, CSVW.Column))) == 14

    def test_declares_primary_key(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        assert str(next(g.objects(None, CSVW.primaryKey))) == "record_id"

    def test_dataset_conforms_to_dictionary(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        assert (None, DCTERMS.conformsTo, None) in g


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
