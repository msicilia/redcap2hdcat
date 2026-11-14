"""The institutional settings as a partial HealthDCAT-AP record (Turtle), equivalent to
the YAML form."""

from __future__ import annotations

import pytest
from rdflib import Graph
from rdflib.compare import isomorphic

from redcap2hdcat.cli import main
from redcap2hdcat.config import TEMPLATE, TEMPLATE_TTL, Agent, Config
from redcap2hdcat.core import rdf


@pytest.fixture
def templates(tmp_path):
    (tmp_path / "c.yaml").write_text(TEMPLATE, encoding="utf-8")
    (tmp_path / "c.ttl").write_text(TEMPLATE_TTL, encoding="utf-8")
    return Config.load(tmp_path / "c.yaml"), Config.load(tmp_path / "c.ttl")


class TestTemplates:
    def test_yaml_and_turtle_templates_are_the_same_settings(self, templates):
        yaml_cfg, ttl_cfg = templates
        assert ttl_cfg == yaml_cfg

    def test_turtle_template_is_a_catalogue(self):
        g = Graph().parse(data=TEMPLATE_TTL, format="turtle")
        assert len(list(g.subjects(predicate=None))) > 0
        cfg = Config.from_graph(g)
        assert cfg.base_uri == "https://redcap.example.org"
        assert cfg.language == "en"
        assert cfg.publisher.name == "Example Institute"
        assert cfg.contact.email == "dpo@example.org"
        assert cfg.access_url == "https://example.org/data-access-request"


class TestRoundTrip:
    def test_full_config_survives_graph_round_trip(self, full_config):
        full_config.custodian = Agent(name="Data Office", email="office@example.org",
                                      homepage="https://example.org/office")
        full_config.creator = Agent(name="Group", identifier="https://ror.org/00x")
        full_config.default_description = "Default description"
        full_config.provenance = "Stated provenance"
        full_config.language = "es"
        again = Config.from_graph(full_config.to_graph())
        assert again == full_config

    def test_records_built_from_either_form_are_isomorphic(self, dictionary_project,
                                                           full_config, tmp_path):
        path = tmp_path / "settings.ttl"
        path.write_text(full_config.to_turtle(), encoding="utf-8")
        from_ttl = rdf.build(dictionary_project, Config.load(path))
        from_obj = rdf.build(dictionary_project, full_config)
        assert isomorphic(from_ttl, from_obj)

    def test_graph_without_a_catalogue_is_rejected(self):
        g = Graph().parse(data="<urn:x> a <http://www.w3.org/ns/dcat#Dataset> .",
                          format="turtle")
        with pytest.raises(ValueError, match="dcat:Catalog"):
            Config.from_graph(g)


class TestCli:
    def test_init_config_turtle_by_extension(self, tmp_path):
        out = tmp_path / "institution.ttl"
        assert main(["init-config", "-o", str(out)]) == 0
        assert out.read_text().lstrip("#").strip().startswith("Institutional settings")
        assert Config.load(out).publisher.name == "Example Institute"

    def test_init_config_format_flag(self, tmp_path, capsys):
        assert main(["init-config", "--format", "turtle"]) == 0
        assert "dcat:Catalog" in capsys.readouterr().out

    def test_build_with_turtle_settings(self, tmp_path):
        from .conftest import FIXTURES
        settings = tmp_path / "s.ttl"
        settings.write_text(TEMPLATE_TTL, encoding="utf-8")
        out = tmp_path / "record.ttl"
        main(["build", str(FIXTURES / "dictionary.csv"), "-c", str(settings), "-o", str(out)])
        assert "dcat:Dataset" in out.read_text()
