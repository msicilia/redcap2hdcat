"""Form structure emitted in the RDF: one csvw:Table per REDCap form."""

from __future__ import annotations

from rdflib.namespace import RDF

from redcap2hdcat.core import rdf
from redcap2hdcat.core.vocab import CSVW, DCTERMS


class TestFormsAreFirstClass:
    def test_one_table_per_form(self, dictionary_project, full_config):
        # The dictionary fixture has three forms: demographics, clinical, followup.
        g = rdf.build(dictionary_project, full_config)
        tables = list(g.subjects(RDF.type, CSVW.Table))
        assert len(tables) == 3

    def test_tables_carry_the_form_name(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        titles = {str(o) for o in g.objects(None, DCTERMS.title)}
        assert {"demographics", "clinical", "followup"} <= titles

    def test_column_carries_its_redcap_type(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config)
        types = {str(o) for o in g.objects(None, DCTERMS.type)}
        assert "radio" in types and "checkbox" in types
