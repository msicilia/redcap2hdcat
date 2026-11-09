from redcap2hdcat.core.columns import expand
from redcap2hdcat.core.vocab import datatype_for


class TestExpansion:
    def test_checkbox_becomes_one_column_per_choice(self, dictionary_project):
        names = [c.name for c in expand(dictionary_project)]
        assert "comorbilidades" not in names
        assert ["comorbilidades___1", "comorbilidades___2", "comorbilidades___3"] == \
            [n for n in names if n.startswith("comorbilidades")]

    def test_descriptive_fields_are_not_columns(self, dictionary_project):
        # Nothing presentational in this fixture, so counts follow the expansion only.
        columns = expand(dictionary_project)
        assert len(columns) == 11 + 3  # 12 variables - 1 checkbox + 3 expanded

    def test_record_id_is_required_and_identifying(self, dictionary_project):
        record_id = expand(dictionary_project)[0]
        assert record_id.name == "record_id"
        assert record_id.required and record_id.identifier

    def test_structural_columns_added_for_longitudinal(self, odm_project):
        names = [c.name for c in expand(odm_project)]
        assert names[1] == "redcap_event_name"

    def test_no_structural_columns_when_classic(self, dictionary_project):
        names = [c.name for c in expand(dictionary_project)]
        assert "redcap_event_name" not in names


class TestDatatypes:
    def test_validation_drives_text_type(self):
        assert datatype_for("text", "integer") == "integer"
        assert datatype_for("text", "date_dmy") == "date"
        assert datatype_for("text", "datetime_seconds_ymd") == "dateTime"
        assert datatype_for("text", "") == "string"

    def test_email_and_phone_stay_strings(self):
        assert datatype_for("text", "email") == "string"
        assert datatype_for("text", "phone") == "string"

    def test_coded_radio_is_integer(self):
        assert datatype_for("radio", "", coded=True) == "integer"
        assert datatype_for("radio", "", coded=False) == "string"

    def test_yesno_is_boolean(self):
        assert datatype_for("yesno") == "boolean"

    def test_unknown_validation_falls_back_to_string(self):
        assert datatype_for("text", "some_future_type") == "string"
