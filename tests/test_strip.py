import pytest

from redcap2hdcat.adapters import odm
from redcap2hdcat.cli import EXIT_ERROR, EXIT_OK, main
from redcap2hdcat.core.strip import count_subjects, strip_file

from .conftest import FIXTURES

WITH_DATA = FIXTURES / "with_clinical_data.xml"
METADATA_ONLY = FIXTURES / "project.xml"


class TestCounting:
    def test_counts_subjects(self):
        assert count_subjects(WITH_DATA) == 1

    def test_metadata_only_has_none(self):
        assert count_subjects(METADATA_ONLY) == 0


class TestStripping:
    def test_removes_records(self, tmp_path):
        out = tmp_path / "clean.xml"
        result = strip_file(WITH_DATA, out)
        assert result.subjects_removed == 1
        assert count_subjects(out) == 0

    def test_output_is_parseable_afterwards(self, tmp_path):
        out = tmp_path / "clean.xml"
        strip_file(WITH_DATA, out)
        # The adapter refused the original; it must accept the stripped copy.
        with pytest.raises(odm.ClinicalDataPresent):
            odm.load(WITH_DATA)
        assert odm.load(out).variables

    def test_preserves_metadata(self, tmp_path):
        out = tmp_path / "clean.xml"
        strip_file(WITH_DATA, out)
        project = odm.load(out)
        assert [v.name for v in project.variables] == ["record_id"]
        assert project.metadata.title == "Leaky"

    def test_metadata_only_input_is_unchanged(self, tmp_path):
        out = tmp_path / "clean.xml"
        result = strip_file(METADATA_ONLY, out)
        assert result.subjects_removed == 0
        assert out.read_bytes() == METADATA_ONLY.read_bytes()

    def test_refuses_to_overwrite_source(self, tmp_path):
        source = tmp_path / "x.xml"
        source.write_bytes(WITH_DATA.read_bytes())
        with pytest.raises(ValueError, match="refusing to overwrite"):
            strip_file(source, source)


class TestStripCommand:
    def test_reports_what_it_removed(self, tmp_path, capsys):
        out = tmp_path / "clean.xml"
        assert main(["strip", str(WITH_DATA), "-o", str(out)]) == EXIT_OK
        err = capsys.readouterr().err
        assert "Removed 1 subject record" in err
        # The user must be told the original still holds the records.
        assert "source file still contains" in err

    def test_will_not_clobber(self, tmp_path):
        out = tmp_path / "clean.xml"
        out.write_text("mine")
        assert main(["strip", str(WITH_DATA), "-o", str(out)]) == EXIT_ERROR
        assert out.read_text() == "mine"

    def test_stripped_file_passes_audit(self, tmp_path):
        out = tmp_path / "clean.xml"
        main(["strip", str(WITH_DATA), "-o", str(out)])
        assert main(["audit", str(out)]) in (EXIT_OK, 1)
