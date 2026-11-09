import json

import pytest

from redcap2hdcat.cli import EXIT_ERROR, EXIT_NONCONFORMANT, EXIT_OK, main

from .conftest import FIXTURES

DICT = str(FIXTURES / "dictionary.csv")


class TestAuditCommand:
    def test_json_output_is_parseable(self, capsys):
        code = main(["audit", DICT, "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert code == EXIT_NONCONFORMANT  # fixture has deliberate errors
        assert payload["counts_by_rule"]["unflagged-identifier"] == 2

    def test_human_output_warns_about_publishing(self, capsys):
        main(["audit", DICT])
        assert "internal use" in capsys.readouterr().out

    def test_refuses_export_with_patient_records(self, capsys):
        code = main(["audit", str(FIXTURES / "with_clinical_data.xml")])
        assert code == EXIT_ERROR
        assert "Refusing to process" in capsys.readouterr().err


class TestBuildCommand:
    def test_writes_turtle(self, capsys):
        code = main(["build", DICT])
        assert code == EXIT_NONCONFORMANT  # no config, so mandatory slots are empty
        assert "dcat:Dataset" in capsys.readouterr().out

    def test_conformant_with_a_full_config(self, tmp_path, capsys):
        config = tmp_path / "inst.yaml"
        config.write_text(
            "base_uri: https://redcap.example.org\n"
            "health_categories: ['https://hdeu-dcat.data.health.europa.eu/resource/authority/"
            "healthcategories/EHRS']\n"
            "access_url: https://redcap.example.org/request\n"
            "dataset_type: https://redcap.example.org/concept/research-data\n"
            "publisher:\n  name: Example\n  email: a@example.org\n"
            "hdab:\n  name: HDAB\n  email: h@example.org\n"
        )
        assert main(["build", DICT, "-c", str(config)]) == EXIT_OK

    def test_rejects_unknown_config_keys(self, tmp_path, capsys):
        config = tmp_path / "bad.yaml"
        config.write_text("base_uri: https://x.org\ntypo_key: 1\n")
        assert main(["build", DICT, "-c", str(config)]) == EXIT_ERROR
        assert "unknown configuration keys" in capsys.readouterr().err

    def test_output_file(self, tmp_path):
        out = tmp_path / "record.ttl"
        main(["build", DICT, "-o", str(out)])
        assert "dcat:Dataset" in out.read_text()


class TestCheckCommand:
    def test_flags_missing_mandatory_properties(self, tmp_path, capsys):
        record = tmp_path / "r.ttl"
        main(["build", DICT, "-o", str(record)])
        assert main(["check", str(record), "--json"]) == EXIT_NONCONFORMANT
        payload = json.loads(capsys.readouterr().out)
        assert "healthdcatap:hdab" in payload["missing_mandatory"]


class TestSampleCommand:
    def test_emits_csv_header(self, capsys):
        assert main(["sample", DICT, "-n", "2"]) == EXIT_OK
        assert capsys.readouterr().out.startswith("record_id,")


class TestInitConfig:
    def test_template_round_trips(self, tmp_path):
        out = tmp_path / "c.yaml"
        main(["init-config", "-o", str(out)])
        from redcap2hdcat.config import Config
        assert Config.load(out).base_uri.startswith("https://")

    def test_will_not_clobber(self, tmp_path):
        out = tmp_path / "c.yaml"
        out.write_text("base_uri: https://mine.org\n")
        assert main(["init-config", "-o", str(out)]) == EXIT_ERROR
        assert out.read_text() == "base_uri: https://mine.org\n"


def test_version_flag():
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
