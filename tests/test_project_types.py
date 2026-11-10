"""Kinds of REDCap project beyond the classic one: repeating instruments and events,
surveys, file and signature fields, and the status columns added on export.

The XML follows the structure of REDCap's own validation exports
(vanderbilt-redcap/redcap_rsvc, Files/cdisc_files), reduced to structure only.
"""

from __future__ import annotations

import os

import pytest

from redcap2hdcat.adapters import odm
from redcap2hdcat.core import rdf
from redcap2hdcat.core.columns import expand
from redcap2hdcat.core.validate import validate

from .test_validate import RELEASE_8

_ODM = """<?xml version="1.0" encoding="UTF-8"?>
<ODM xmlns="http://www.cdisc.org/ns/odm/v1.3" xmlns:redcap="https://projectredcap.org"
     SourceSystem="REDCap" SourceSystemVersion="15.0.0">
 <Study OID="S">
  <GlobalVariables>
   <StudyName>Project types</StudyName>
   <redcap:RepeatingInstrumentsAndEvents>
    <redcap:RepeatingEvent redcap:UniqueEventName="{repeating_event}"/>
    <redcap:RepeatingInstruments>
     <redcap:RepeatingInstrument redcap:UniqueEventName="event_1_arm_1"
         redcap:RepeatInstrument="{repeating_form}" redcap:CustomLabel=""/>
    </redcap:RepeatingInstruments>
   </redcap:RepeatingInstrumentsAndEvents>
   <redcap:SurveysGroup>
    <redcap:Surveys form_name="consent" title="Consent" survey_enabled="1"/>
    <redcap:Surveys form_name="baseline" title="Baseline" survey_enabled="0"/>
   </redcap:SurveysGroup>
  </GlobalVariables>
  <MetaDataVersion OID="M" Name="M">
   <StudyEventDef OID="Event.event_1_arm_1" Name="Event 1 (Arm 1: A)" Repeating="No"
       Type="Common" redcap:EventName="Event 1" redcap:UniqueEventName="event_1_arm_1"
       redcap:ArmName="A"/>
   <StudyEventDef OID="Event.event_2_arm_1" Name="Event 2 (Arm 1: A)" Repeating="No"
       Type="Common" redcap:EventName="Event 2" redcap:UniqueEventName="event_2_arm_1"
       redcap:ArmName="A"/>
   <FormDef OID="Form.baseline" Name="Baseline" Repeating="No" redcap:FormName="baseline">
    <ItemGroupRef ItemGroupOID="baseline.record_id" Mandatory="No"/>
   </FormDef>
   <FormDef OID="Form.consent" Name="Consent" Repeating="No" redcap:FormName="consent">
    <ItemGroupRef ItemGroupOID="consent.agree" Mandatory="No"/>
   </FormDef>
   <ItemGroupDef OID="baseline.record_id" Name="Baseline">
    <ItemRef ItemOID="record_id" Mandatory="No"/>
    <ItemRef ItemOID="age" Mandatory="No"/>
    <ItemRef ItemOID="scan" Mandatory="No"/>
   </ItemGroupDef>
   <ItemGroupDef OID="consent.agree" Name="Consent">
    <ItemRef ItemOID="agree" Mandatory="No"/>
    <ItemRef ItemOID="signature" Mandatory="No"/>
   </ItemGroupDef>
   <ItemDef OID="record_id" Name="record_id" DataType="text" redcap:FieldType="text">
    <Question><TranslatedText>Record ID</TranslatedText></Question>
   </ItemDef>
   <ItemDef OID="age" Name="age" DataType="integer" redcap:FieldType="text"
       redcap:TextValidationType="int">
    <Question><TranslatedText>Age</TranslatedText></Question>
   </ItemDef>
   <ItemDef OID="scan" Name="scan" DataType="text" redcap:FieldType="file">
    <Question><TranslatedText>Imaging report</TranslatedText></Question>
   </ItemDef>
   <ItemDef OID="agree" Name="agree" DataType="text" redcap:FieldType="yesno">
    <Question><TranslatedText>I agree to take part</TranslatedText></Question>
   </ItemDef>
   <ItemDef OID="signature" Name="signature" DataType="text" redcap:FieldType="file"
       redcap:TextValidationType="signature">
    <Question><TranslatedText>Signature</TranslatedText></Question>
   </ItemDef>
  </MetaDataVersion>
 </Study>
</ODM>
"""


def _load(tmp_path, repeating_event="event_2_arm_1", repeating_form="baseline"):
    path = tmp_path / "types.xml"
    path.write_text(_ODM.format(repeating_event=repeating_event,
                                repeating_form=repeating_form), encoding="utf-8")
    return odm.load(path)


@pytest.fixture
def project(tmp_path):
    return _load(tmp_path)


class TestDeclarations:
    def test_repeating_instrument_from_repeat_instrument_attribute(self, project):
        assert project.repeating_forms == ["baseline"]

    def test_repeating_event(self, project):
        assert project.repeating_events == ["event_2_arm_1"]

    def test_only_enabled_surveys(self, project):
        assert project.survey_forms == ["consent"]


class TestColumns:
    def test_export_order(self, project):
        assert [c.name for c in expand(project)] == [
            "record_id", "redcap_event_name", "redcap_repeat_instrument",
            "redcap_repeat_instance", "redcap_survey_identifier",
            "age", "scan", "baseline_complete",
            "consent_timestamp", "agree", "signature", "consent_complete",
        ]

    def test_repeat_columns_for_a_repeating_event_alone(self, tmp_path):
        project = _load(tmp_path, repeating_form="")
        assert project.repeating_forms == []
        names = [c.name for c in expand(project)]
        assert "redcap_repeat_instrument" in names and "redcap_repeat_instance" in names

    def test_file_and_signature_fields_are_string_columns(self, project):
        cols = {c.name: c for c in expand(project)}
        assert cols["scan"].datatype == cols["signature"].datatype == "string"

    def test_status_column_carries_its_codes(self, project):
        status = {c.name: c for c in expand(project)}["consent_complete"]
        assert status.datatype == "integer"
        assert [code for code, _ in status.choices] == ["0", "1", "2"]
        assert status.form == "consent"

    def test_items_already_in_the_export_are_not_added_twice(self, project):
        from redcap2hdcat.model import FieldType, Variable
        project.variables.append(Variable(name="consent_complete", label="Complete?",
                                          field_type=FieldType.DROPDOWN, form="consent"))
        names = [c.name for c in expand(project)]
        assert names.count("consent_complete") == 1

    def test_first_instrument_as_survey_keeps_record_id_first(self, project):
        project.survey_forms = ["baseline"]
        names = [c.name for c in expand(project)]
        assert names[0] == "record_id"
        assert names.index("baseline_timestamp") == names.index("redcap_survey_identifier") + 1


class TestProvenance:
    def test_names_surveys_and_not_case_report_forms(self, project):
        from redcap2hdcat.config import Config
        text = rdf.provenance_statement(project, Config())
        assert "case report" not in text
        assert text.startswith("Data collected in REDCap 15.0.0 on 2 instruments, 1 of them "
                               "enabled as a survey for participants, over 2 longitudinal "
                               "events.")


@pytest.mark.skipif(not RELEASE_8.exists() or not os.environ.get("RUN_SHACL"),
                    reason="needs the pinned Release 8 shapes and RUN_SHACL=1 (slow)")
def test_conforms_to_release_8(project, full_config):
    assert validate(rdf.build(project, full_config), RELEASE_8).violations == []
