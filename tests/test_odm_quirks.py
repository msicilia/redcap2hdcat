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


_SPLIT_CHECKBOX = """<?xml version="1.0" encoding="UTF-8"?>
<ODM xmlns="http://www.cdisc.org/ns/odm/v1.3" xmlns:redcap="https://projectredcap.org"
     SourceSystem="REDCap" SourceSystemVersion="14.0.0">
 <Study OID="S">
  <GlobalVariables><StudyName>Split checkbox</StudyName></GlobalVariables>
  <MetaDataVersion OID="M" Name="M">
   <FormDef OID="Form.f" Name="F" redcap:FormName="f">
    <ItemGroupRef ItemGroupOID="f.record_id" Mandatory="No"/>
   </FormDef>
   <ItemGroupDef OID="f.record_id" Name="F">
    <ItemRef ItemOID="record_id" Mandatory="No"/>
    <ItemRef ItemOID="dx___a" Mandatory="No"/>
    <ItemRef ItemOID="dx___b" Mandatory="No"/>
   </ItemGroupDef>
   <ItemDef OID="record_id" Name="record_id" DataType="text" redcap:FieldType="text">
    <Question><TranslatedText>Record ID</TranslatedText></Question>
   </ItemDef>
   <ItemDef OID="dx___a" Name="dx___a" DataType="boolean" redcap:Variable="dx"
            redcap:FieldType="checkbox" redcap:RequiredField="y">
    <Question><TranslatedText>Diagnosis</TranslatedText></Question>
    <CodeListRef CodeListOID="dx___a.choices"/>
   </ItemDef>
   <ItemDef OID="dx___b" Name="dx___b" DataType="boolean" redcap:Variable="dx"
            redcap:FieldType="checkbox" redcap:RequiredField="y">
    <Question><TranslatedText>Diagnosis</TranslatedText></Question>
    <CodeListRef CodeListOID="dx___b.choices"/>
   </ItemDef>
   <CodeList OID="dx___a.choices" Name="dx___a" DataType="boolean" redcap:Variable="dx"
             redcap:CheckboxChoices="a, Asthma | b, Bronchitis">
    <CodeListItem CodedValue="1">
     <Decode><TranslatedText>Checked</TranslatedText></Decode>
    </CodeListItem>
    <CodeListItem CodedValue="0">
     <Decode><TranslatedText>Unchecked</TranslatedText></Decode>
    </CodeListItem>
   </CodeList>
   <CodeList OID="dx___b.choices" Name="dx___b" DataType="boolean" redcap:Variable="dx"
             redcap:CheckboxChoices="a, Asthma | b, Bronchitis">
    <CodeListItem CodedValue="1">
     <Decode><TranslatedText>Checked</TranslatedText></Decode>
    </CodeListItem>
    <CodeListItem CodedValue="0">
     <Decode><TranslatedText>Unchecked</TranslatedText></Decode>
    </CodeListItem>
   </CodeList>
  </MetaDataVersion>
 </Study>
</ODM>
"""


class TestPreSplitCheckboxes:
    """Newer exports already split a checkbox into one ItemDef per option. Splitting
    them again produced columns such as dx___a___0 and dx___a___1."""

    @pytest.fixture
    def project(self, tmp_path):
        path = tmp_path / "split.xml"
        path.write_text(_SPLIT_CHECKBOX, encoding="utf-8")
        return odm.load(path)

    def test_options_fold_into_one_field(self, project):
        assert [v.name for v in project.variables] == ["record_id", "dx"]
        dx = project.by_name("dx")
        assert dx.field_type == FieldType.CHECKBOX
        assert [(c.code, c.label) for c in dx.choices] == [("a", "Asthma"), ("b", "Bronchitis")]
        assert dx.required

    def test_columns_are_not_split_twice(self, project):
        from redcap2hdcat.core.columns import expand
        assert [c.name for c in expand(project)] == [
            "record_id", "dx___a", "dx___b", "f_complete"]
