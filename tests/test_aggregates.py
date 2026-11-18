"""The --aggregates option: records are counted, never read."""

import pytest

from redcap2hdcat.adapters import load_project, odm
from redcap2hdcat.cli import EXIT_NONCONFORMANT, main

from .conftest import FIXTURES

WITH_DATA = FIXTURES / "with_clinical_data.xml"

LONGITUDINAL = """<?xml version="1.0" encoding="UTF-8"?>
<ODM xmlns="http://www.cdisc.org/ns/odm/v1.3" xmlns:redcap="https://projectredcap.org"
     CreationDateTime="2026-07-20T10:00:00" SourceSystem="REDCap">
  <Study OID="Project.L">
    <GlobalVariables><StudyName>L</StudyName></GlobalVariables>
    <MetaDataVersion OID="Metadata.1" Name="L">
      <StudyEventDef OID="Event.visit_1_arm_1" Name="Visit 1" Type="Common" Repeating="No"
                     redcap:UniqueEventName="visit_1_arm_1"/>
      <FormDef OID="Form.base" Name="base" Repeating="No" redcap:FormName="base">
        <ItemGroupRef ItemGroupOID="Group.base" Mandatory="No"/>
      </FormDef>
      <FormDef OID="Form.lab" Name="lab" Repeating="Yes" redcap:FormName="lab">
        <ItemGroupRef ItemGroupOID="Group.lab" Mandatory="No"/>
      </FormDef>
      <ItemGroupDef OID="Group.base" Name="base" Repeating="No" redcap:FormName="base">
        <ItemRef ItemOID="Item.record_id" Mandatory="Yes"/>
      </ItemGroupDef>
      <ItemGroupDef OID="Group.lab" Name="lab" Repeating="No" redcap:FormName="lab">
        <ItemRef ItemOID="Item.value" Mandatory="No"/>
      </ItemGroupDef>
      <ItemDef OID="Item.record_id" Name="record_id" DataType="text" redcap:FieldType="text">
        <Question><TranslatedText>Record ID</TranslatedText></Question>
      </ItemDef>
      <ItemDef OID="Item.value" Name="value" DataType="float" redcap:FieldType="text">
        <Question><TranslatedText>Value</TranslatedText></Question>
      </ItemDef>
    </MetaDataVersion>
  </Study>
  <ClinicalData StudyOID="Project.L" MetaDataVersionOID="Metadata.1">
    <SubjectData SubjectKey="1">
      <StudyEventData StudyEventOID="Event.visit_1_arm_1">
        <FormData FormOID="Form.base"><ItemGroupData ItemGroupOID="Group.base">
          <ItemData ItemOID="Item.record_id" Value="1"/></ItemGroupData></FormData>
        <FormData FormOID="Form.lab" FormRepeatKey="1"><ItemGroupData ItemGroupOID="Group.lab">
          <ItemData ItemOID="Item.value" Value="4.1"/></ItemGroupData></FormData>
        <FormData FormOID="Form.lab" FormRepeatKey="2"><ItemGroupData ItemGroupOID="Group.lab">
          <ItemData ItemOID="Item.value" Value="4.4"/></ItemGroupData></FormData>
      </StudyEventData>
    </SubjectData>
    <SubjectData SubjectKey="2">
      <StudyEventData StudyEventOID="Event.visit_1_arm_1">
        <FormData FormOID="Form.base"><ItemGroupData ItemGroupOID="Group.base">
          <ItemData ItemOID="Item.record_id" Value="2"/></ItemGroupData></FormData>
      </StudyEventData>
    </SubjectData>
  </ClinicalData>
</ODM>
"""


class TestRefusalStaysTheDefault:
    def test_adapter_refuses_without_the_option(self):
        with pytest.raises(odm.ClinicalDataPresent):
            odm.load(WITH_DATA)

    def test_dispatch_refuses_without_the_option(self):
        with pytest.raises(odm.ClinicalDataPresent):
            load_project(WITH_DATA)


class TestCounting:
    def test_classic_export(self):
        project = odm.load(WITH_DATA, with_records=True)
        assert (project.metadata.record_count, project.metadata.unique_individual_count) == (1, 1)
        assert project.provenance["records"] == "counted"
        assert [v.name for v in project.variables] == ["record_id"]

    def test_rows_follow_the_flat_export(self, tmp_path):
        # Subject 1: one row for the non-repeating form, two for the repeating instances;
        # subject 2: one row. Four rows, two individuals.
        src = tmp_path / "l.xml"
        src.write_text(LONGITUDINAL, encoding="utf-8")
        project = odm.load(src, with_records=True)
        assert (project.metadata.record_count, project.metadata.unique_individual_count) == (4, 2)

    def test_metadata_only_export_is_unchanged(self):
        project = odm.load(FIXTURES / "project.xml", with_records=True)
        assert project.metadata.record_count is None
        assert "records" not in project.provenance


class TestBuildFlag:
    def test_counts_reach_the_record(self, capsys):
        code = main(["build", str(WITH_DATA), "--aggregates"])
        captured = capsys.readouterr()
        assert code == EXIT_NONCONFORMANT  # no configuration given
        assert "numberOfRecords" in captured.out
        assert "numberOfUniqueIndividuals" in captured.out
        assert "Records counted, values not read: 1 rows, 1 individuals" in captured.err
