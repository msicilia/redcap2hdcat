import pytest

from redcap2hdcat.adapters import csv_dict, load_project, odm
from redcap2hdcat.model import FieldType

from .conftest import FIXTURES


class TestCsvDictionary:
    def test_reads_every_variable(self, dictionary_project):
        assert len(dictionary_project.variables) == 12

    def test_record_id_is_first_field(self, dictionary_project):
        assert dictionary_project.record_id_field == "record_id"

    def test_groups_by_form(self, dictionary_project):
        assert dictionary_project.forms == ["demographics", "clinical", "followup"]

    def test_parses_choices(self, dictionary_project):
        sexo = dictionary_project.by_name("sexo")
        assert [c.code for c in sexo.choices] == ["1", "2", "3"]
        assert sexo.choices[0].label == "Hombre"

    def test_reads_identifier_flag(self, dictionary_project):
        assert dictionary_project.by_name("fecha_nacimiento").identifier is True
        assert dictionary_project.by_name("nhc").identifier is False

    def test_rejects_non_dictionary(self, tmp_path):
        path = tmp_path / "other.csv"
        path.write_text("a,b,c\n1,2,3\n")
        with pytest.raises(ValueError, match="not a REDCap data dictionary"):
            csv_dict.load(path)

    def test_reads_api_style_headers(self):
        # REDCap dictionaries ship in two header conventions: the UI download
        # ("Variable / Field Name") and the API/raw metadata ("field_name").
        # A real IeDEA/test-dataset export uses the latter.
        project = csv_dict.load(FIXTURES / "dictionary_api_headers.csv")
        assert [v.name for v in project.variables] == ["record_id", "edad", "sexo", "nhc"]
        assert project.by_name("edad").validation == "integer"
        assert [c.label for c in project.by_name("sexo").choices] == ["Hombre", "Mujer"]
        assert project.forms == ["demographics"]


class TestChoiceParsing:
    def test_label_may_contain_commas(self):
        choices = csv_dict.parse_choices("1, Yes, definitely | 2, No")
        assert choices[0].label == "Yes, definitely"
        assert len(choices) == 2

    def test_empty_is_empty(self):
        assert csv_dict.parse_choices("") == []


class TestOdm:
    def test_reads_items_in_form_order(self, odm_project):
        assert [v.name for v in odm_project.variables] == [
            "record_id", "nhc", "sexo", "peso", "comorbilidades"
        ]

    def test_reads_events(self, odm_project):
        assert [e.unique_name for e in odm_project.events] == ["baseline_arm_1", "month12_arm_1"]
        assert odm_project.metadata.is_longitudinal is True

    def test_reads_codelists_without_regex(self, odm_project):
        assert [c.label for c in odm_project.by_name("sexo").choices] == ["Hombre", "Mujer"]

    def test_reads_validation_bounds(self, odm_project):
        peso = odm_project.by_name("peso")
        assert (peso.validation, peso.validation_min, peso.validation_max) == \
            ("number_1dp", "30", "250")

    def test_field_type_from_vendor_attribute(self, odm_project):
        assert odm_project.by_name("comorbilidades").field_type is FieldType.CHECKBOX

    def test_records_source_system_version(self, odm_project):
        assert odm_project.metadata.source_system_version == "14.5.11"

    def test_refuses_clinical_data(self):
        # Blocking by design: never process patient records silently.
        with pytest.raises(odm.ClinicalDataPresent, match="1 subject record"):
            odm.load(FIXTURES / "with_clinical_data.xml")


class TestDispatch:
    def test_picks_adapter_by_extension(self):
        assert load_project(FIXTURES / "project.xml").events
        assert load_project(FIXTURES / "dictionary.csv").variables

    def test_rejects_unknown_extension(self, tmp_path):
        path = tmp_path / "x.json"
        path.write_text("{}")
        with pytest.raises(ValueError, match="unsupported input"):
            load_project(path)
