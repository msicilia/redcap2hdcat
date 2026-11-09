"""Multi-source composition (REDCap + DMP) and semantic coding (SNOMED)."""

from __future__ import annotations

import pytest
from rdflib.namespace import PROV, RDFS, SKOS

from redcap2hdcat.adapters import csv_dict
from redcap2hdcat.core import rdf, snomed
from redcap2hdcat.core.vocab import CSVW, DCAT, DCTERMS, DPV, FOAF, HEALTHDCATAP

from .conftest import FIXTURES

DMP = FIXTURES / "dmp.json"


class TestFieldNoteAndLabel:
    def test_label_is_the_title(self, dictionary_project, full_config):
        # The label always comes from the form and is the title.
        g = rdf.build(dictionary_project, full_config)
        titles = {str(o) for o in g.objects(None, CSVW.title)}
        assert "Sexo" in titles

    def test_note_is_not_duplicated_from_label(self, tmp_path):
        # A field with a label but no note must have no description (no duplicate).
        path = tmp_path / "d.csv"
        path.write_text(
            "field_name,form_name,field_type,field_label,field_note\n"
            "record_id,f,text,Record ID,\n"
            "peso,f,text,Peso,\n"
        )
        project = csv_dict.load(path)
        assert project.by_name("peso").note == ""
        from redcap2hdcat.core.columns import expand
        peso = next(c for c in expand(project) if c.name == "peso")
        assert peso.description == ""  # no note -> no description, not the label

    def test_note_kept_when_present(self, tmp_path):
        path = tmp_path / "d.csv"
        path.write_text(
            "field_name,form_name,field_type,field_label,field_note\n"
            "record_id,f,text,Record ID,\n"
            "peso,f,text,Peso,Peso en kilogramos\n"
        )
        from redcap2hdcat.core.columns import expand
        peso = next(c for c in expand(csv_dict.load(path)) if c.name == "peso")
        assert peso.description == "Peso en kilogramos"


class TestCodingConvention:
    def test_parses_code_with_version_and_term(self):
        codes = snomed.parse_annotation(
            "@CODE=SNOMED|20230731|22298006 |Myocardial infarction| @HIDDEN"
        )
        assert len(codes) == 1
        c = codes[0]
        assert (c.system, c.version, c.code) == ("SNOMED", "20230731", "22298006")
        assert c.display == "Myocardial infarction"

    def test_version_is_optional(self):
        c = snomed.parse_annotation("@CODE=SNOMED||22298006")[0]
        assert c.version == "" and c.code == "22298006"

    def test_is_terminology_agnostic(self):
        codes = snomed.parse_annotation("@CODE=LOINC|2.74|4548-4 @CODE=ICD10|2019|I21.9")
        assert {(c.system, c.code) for c in codes} == {("LOINC", "4548-4"), ("ICD10", "I21.9")}

    def test_uri_per_system(self):
        assert snomed.Coding("SNOMED", "22298006").uri == "http://snomed.info/id/22298006"
        assert snomed.Coding("LOINC", "4548-4").uri == "https://loinc.org/4548-4"

    def test_expression_has_no_uri_but_is_kept(self):
        c = snomed.parse_annotation("@CODE=SNOMED||243796009:246090004=421720008")[0]
        assert c.is_expression and c.uri == ""
        assert c.code == "243796009:246090004=421720008"

    def test_ignores_plain_action_tags(self):
        assert snomed.parse_annotation("@HIDDEN @READONLY") == []

    def test_demo_mapper_guesses_from_label(self):
        assert snomed.guess_snomed("Sexo del paciente").code == "263495000"
        assert snomed.guess_snomed("Diabetes tipo 2").code == "73211009"
        assert snomed.guess_snomed("campo sin sentido xyz") is None

    def test_explicit_annotation_wins_over_demo(self):
        codes = snomed.code_field("@CODE=SNOMED||99999999", "Sexo", demo=True)
        assert codes[0].code == "99999999"


class TestSnomedInRdf:
    def test_no_codes_without_demo_flag(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config, snomed_demo=False)
        assert not list(g.subject_objects(SKOS.exactMatch))

    def test_three_levels_with_demo(self, dictionary_project, full_config):
        g = rdf.build(dictionary_project, full_config, snomed_demo=True)
        # Field level.
        assert list(g.subject_objects(SKOS.exactMatch))
        # Form level.
        assert list(g.objects(None, DCTERMS.subject))
        # Dataset level.
        systems = list(g.objects(None, HEALTHDCATAP.hasCodingSystem))
        assert snomed.CODING_SYSTEM["SNOMED"] in {str(s) for s in systems}


class TestDmpComposition:
    @pytest.fixture
    def composed(self, dictionary_project, full_config):
        pytest.importorskip("madmpy")
        from redcap2hdcat.adapters import dmp
        overlay = dmp.load(DMP)
        overlay.apply(dictionary_project)
        return rdf.build(dictionary_project, full_config)

    def test_description_comes_from_dmp(self, composed):
        descs = " ".join(str(o) for o in composed.objects(None, DCTERMS.description))
        assert "radiómica" in descs or "cáncer de recto" in descs

    def test_creator_comes_from_dmp(self, composed):
        names = {str(o) for o in composed.objects(None, FOAF.name)}
        assert "Dra. Responsable del Estudio" in names

    def test_license_comes_from_dmp_on_the_distribution(self, composed):
        dist = next(composed.objects(None, DCAT.distribution))
        assert composed.value(dist, DCTERMS.license) is not None
        assert not [s for s, _ in composed.subject_objects(DCTERMS.license) if s != dist]

    def test_grant_identifies_the_generating_project(self, composed):
        # A grant number is not an IRI, so it cannot be dct:isReferencedBy; it
        # identifies the project that generated the data.
        activity = next(composed.objects(None, PROV.wasGeneratedBy))
        assert str(composed.value(activity, DCTERMS.identifier)) == "PMP24/00024"
        assert not list(composed.objects(None, DCTERMS.isReferencedBy))

    def test_language_from_dmp_is_an_eu_language_iri(self, composed):
        # Regression: the madmpy enum repr 'LanguageEnum.spa' used to give "La".
        langs = {str(o) for o in composed.objects(None, DCTERMS.language)}
        assert langs == {"http://publications.europa.eu/resource/authority/language/SPA"}

    def test_dmp_texts_carry_the_dmp_language(self, composed):
        descs = [o for o in composed.objects(None, DCTERMS.description)
                 if "radiómica" in str(o)]
        assert descs and all(d.language == "es" for d in descs)

    def test_dmp_asserts_personal_data(self, composed):
        # The REDCap dictionary flags an identifier too, but the DMP would assert it
        # even if none were flagged. Either way it must be present.
        assert (None, DPV.hasPersonalData, None) in composed

    def test_keywords_merged(self, composed):
        kw = {str(o) for o in composed.objects(None, DCAT.keyword)}
        assert "radiómica" in kw

    def test_dmp_does_not_overwrite_existing_title(self, dictionary_project):
        pytest.importorskip("madmpy")
        from redcap2hdcat.adapters import dmp
        dictionary_project.metadata.title = "Título REDCap original"
        dmp.load(DMP).apply(dictionary_project)
        assert dictionary_project.metadata.title == "Título REDCap original"


class TestCalcFormula:
    def test_formula_captured_and_emitted(self, tmp_path, full_config):
        path = tmp_path / "d.csv"
        path.write_text(
            "field_name,form_name,field_type,field_label,"
            "select_choices_or_calculations,field_note\n"
            "record_id,f,text,Record ID,,\n"
            "imc,f,calc,IMC,[peso]/([altura]*[altura]),\n"
        )
        project = csv_dict.load(path)
        assert project.by_name("imc").calculation == "[peso]/([altura]*[altura])"
        g = rdf.build(project, full_config)
        comments = {str(o) for o in g.objects(None, RDFS.comment)}
        assert "[peso]/([altura]*[altura])" in comments
