"""Codes written by the ROME module in the @ONTOLOGY action tag."""

from __future__ import annotations

import csv
import io
import json
import os

import pytest
from rdflib import URIRef
from rdflib.namespace import RDF, SKOS

from redcap2hdcat.adapters import csv_dict
from redcap2hdcat.core import rdf, snomed
from redcap2hdcat.core.columns import expand
from redcap2hdcat.core.validate import validate
from redcap2hdcat.core.vocab import CSVW, DCTERMS, HEALTHDCATAP

from .test_validate import RELEASE_8

SMOKER = {"dataElement": {
    "coding": [{"system": "http://loinc.org", "code": "72166-2",
                "display": "Tobacco smoking status"}],
    "valueCodingMap": {
        "1": {"coding": [{"system": "http://snomed.info/sct", "code": "8517006",
                          "display": "Ex-smoker"}]},
        "2": {"coding": [{"system": "http://snomed.info/sct", "code": "8392000",
                          "display": "Non-smoker"}]},
    }}}
SYMPTOMS = {"dataElement": {"valueCodingMap": {
    "1": {"coding": [{"system": "https://snomed.info/sct", "code": "49727002",
                      "display": "Cough"}]},
    "2": {"coding": [{"system": "http://snomed.info/sct", "code": "267036007",
                      "display": "Dyspnea"}]},
}}}
HEIGHT = {"dataElement": {
    "coding": [{"system": "http://loinc.org", "code": "8302-2", "display": "Body height"}],
    "unit": {"coding": [{"system": "http://unitsofmeasure.org", "code": "cm"}]}}}


def tag(obj: dict, quote: str = "'") -> str:
    return f"@ONTOLOGY={quote}{json.dumps(obj)}{quote}"


@pytest.fixture
def rome_project(tmp_path):
    rows = [
        ["field_name", "form_name", "field_type", "field_label",
         "select_choices_or_calculations", "field_annotation"],
        ["record_id", "baseline", "text", "Record ID", "", ""],
        ["smoker", "baseline", "radio", "Smoking status", "1, Ex-smoker | 2, Never",
         "@HIDDEN-SURVEY " + tag(SMOKER)],
        ["symptoms", "baseline", "checkbox", "Symptoms", "1, Cough | 2, Dyspnoea | 3, Other",
         tag(SYMPTOMS, quote="")],
        ["height", "baseline", "text", "Height", "",
         tag(HEIGHT, quote='"') + " @CODE=SNOMED||50373000"],
    ]
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    path = tmp_path / "rome.csv"
    path.write_text(buf.getvalue(), encoding="utf-8")
    return csv_dict.load(path)


class TestParser:
    def test_field_value_and_unit_codings(self):
        rome = snomed.parse_rome(tag(SMOKER))
        assert [(c.system, c.code) for c in rome.coding] == [("LOINC", "72166-2")]
        assert set(rome.values) == {"1", "2"}
        assert rome.values["2"][0].uri == "http://snomed.info/id/8392000"
        assert snomed.parse_rome(tag(HEIGHT)).unit[0].system == "UCUM"

    @pytest.mark.parametrize("quote", ["", "'", '"'])
    def test_quoted_and_unquoted(self, quote):
        assert snomed.parse_rome(f"@READONLY {tag(SMOKER, quote)} @HIDDEN") is not None

    def test_https_system_and_braces_inside_strings(self):
        obj = {"dataElement": {"coding": [
            {"system": "https://snomed.info/sct", "code": "1", "display": "a } b {"}]}}
        c = snomed.parse_rome(tag(obj)).coding[0]
        assert (c.system, c.display) == ("SNOMED", "a } b {")

    def test_last_valid_tag_wins(self):
        text = tag(SMOKER) + " @ONTOLOGY='{broken' " + tag(HEIGHT)
        assert snomed.parse_rome(text).coding[0].code == "8302-2"
        assert snomed.parse_rome(tag(HEIGHT) + " @ONTOLOGY='{broken'").coding[0].code == "8302-2"

    def test_no_tag_or_invalid_json(self):
        assert snomed.parse_rome("@HIDDEN") is None
        assert snomed.parse_rome("@ONTOLOGY='{\"x\": 1}'") is None

    def test_unknown_system_kept_without_uri(self):
        obj = {"dataElement": {"coding": [{"system": "http://example.org/cs", "code": "A1"}]}}
        c = snomed.parse_rome(tag(obj)).coding[0]
        assert (c.system, c.uri) == ("http://example.org/cs", "")

    def test_code_and_ontology_tags_combine(self):
        codes = snomed.parse_annotation(tag(HEIGHT) + " @CODE=SNOMED||50373000")
        assert [(c.system, c.code) for c in codes] == [("SNOMED", "50373000"), ("LOINC", "8302-2")]


class TestColumns:
    def test_radio_keeps_option_codes(self, rome_project):
        smoker = next(c for c in expand(rome_project) if c.name == "smoker")
        assert [c.code for c in smoker.codings] == ["72166-2"]
        assert set(smoker.value_codings) == {"1", "2"}

    def test_checkbox_option_column_carries_its_code(self, rome_project):
        cols = {c.name: c for c in expand(rome_project)}
        assert [c.code for c in cols["symptoms___1"].codings] == ["49727002"]
        assert [c.code for c in cols["symptoms___2"].codings] == ["267036007"]
        assert cols["symptoms___3"].codings == []


class TestRecord:
    def test_option_concepts_and_coding_systems(self, rome_project, full_config):
        g = rdf.build(rome_project, full_config)
        options = list(g.objects(None, DCTERMS.references))
        assert len(options) == 2
        never = next(o for o in options if str(g.value(o, SKOS.notation)) == "2")
        assert (never, RDF.type, SKOS.Concept) in g
        assert str(g.value(never, SKOS.prefLabel)) == "Never"
        assert g.value(never, SKOS.exactMatch) == URIRef("http://snomed.info/id/8392000")
        # Option concepts are also subjects of the form.
        tables = list(g.subjects(RDF.type, CSVW.Table))
        assert (tables[0], DCTERMS.subject, URIRef("http://snomed.info/id/49727002")) in g
        systems = set(g.objects(None, HEALTHDCATAP.hasCodingSystem))
        assert systems == {URIRef(snomed.CODING_SYSTEM["SNOMED"]),
                           URIRef(snomed.CODING_SYSTEM["LOINC"])}

    @pytest.mark.skipif(not RELEASE_8.exists() or not os.environ.get("RUN_SHACL"),
                        reason="needs the pinned Release 8 shapes and RUN_SHACL=1 (slow)")
    def test_conforms_to_release_8(self, rome_project, full_config):
        result = validate(rdf.build(rome_project, full_config), RELEASE_8)
        assert result.violations == []
