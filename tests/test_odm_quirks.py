"""Regression tests for REDCap ODM quirks found in a real 13.4.11 export.

Every case here silently produced wrong output before being fixed. The fixture is
reduced from a real project; it contains structure only.
"""

from __future__ import annotations

import pytest

from redcap2hdcat.adapters import odm
from redcap2hdcat.model import FieldType

from .conftest import FIXTURES


@pytest.fixture
def quirks():
    return odm.load(FIXTURES / "odm_quirks.xml")


class TestFormNames:
    def test_form_comes_from_formdef_not_itemgroup(self, quirks):
        # ItemGroupDef elements are sections: their Name is the section header and
        # redcap:FormName is absent. Using them yielded 25 "forms" for 5 instruments.
        assert quirks.forms == ["caracteristicas_clinicas", "analisis"]

    def test_items_are_assigned_to_their_instrument(self, quirks):
        assert quirks.by_name("edad").form == "caracteristicas_clinicas"
        assert quirks.by_name("marcador").form == "analisis"


class TestFieldTypeAliases:
    def test_select_is_a_dropdown(self, quirks):
        # The ODM says 'select' where the data dictionary says 'dropdown'.
        assert quirks.by_name("localizacion").field_type is FieldType.DROPDOWN

    def test_textarea_is_notes(self, quirks):
        assert quirks.by_name("comentario").field_type is FieldType.NOTES

    def test_radio_is_unchanged(self, quirks):
        assert quirks.by_name("sexo").field_type is FieldType.RADIO


class TestValidationAliases:
    def test_int_normalises_to_integer(self, quirks):
        # The ODM abbreviates; the dictionary spells it out.
        assert quirks.by_name("edad").validation == "integer"

    def test_date_validation_is_unchanged(self, quirks):
        assert quirks.by_name("fecha_diagnostico").validation == "date_dmy"

    def test_falls_back_to_odm_datatype(self, quirks):
        # No redcap:TextValidationType, but DataType="integer" is mandatory in ODM.
        assert quirks.by_name("recuento").validation == "integer"

    def test_plain_text_stays_unvalidated(self, quirks):
        assert quirks.by_name("comentario").validation == ""


class TestEvents:
    def test_unique_event_name_preferred(self, quirks):
        assert [e.unique_name for e in quirks.events] == ["event_1_arm_1", "event_1_arm_2"]

    def test_label_excludes_the_arm(self, quirks):
        # Name is "Event 1 (Arm 1: PTS 1)"; redcap:EventName is the plain label.
        assert quirks.events[0].label == "Event 1"
        assert quirks.events[0].arm == "PTS 1"


class TestFormCompleteFields:
    def test_complete_fields_are_kept(self, quirks):
        # Real export columns that exist in no data dictionary.
        names = [v.name for v in quirks.variables]
        assert "caracteristicas_clinicas_complete" in names

    def test_data_access_group_is_kept(self, quirks):
        assert quirks.by_name("redcap_data_access_group") is not None
