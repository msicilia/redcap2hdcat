"""Loading of the official HealthDCAT-AP validator configuration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from rdflib import Graph
from rdflib.namespace import RDF, SH

from redcap2hdcat.core import rdf
from redcap2hdcat.core.validate import (
    _read_properties,
    profile_of,
    repair_pathless_property_shapes,
    validate,
)

RELEASE_8 = Path(__file__).parents[1] / "paper" / "eval" / "shapes" / "release-8" / "ehds"


def test_reads_validator_properties(tmp_path):
    path = tmp_path / "config.properties"
    path.write_text("# comment\nvalidator.shaclFile.non-public = a.ttl, \\\n  b.ttl\nx=1\n")
    props = _read_properties(path)
    assert props["validator.shaclFile.non-public"] == "a.ttl, b.ttl"
    assert props["x"] == "1"


def test_pathless_property_shape_becomes_a_node_shape():
    shapes = Graph().parse(data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://example.org/> .
        ex:S a sh:NodeShape ; sh:targetClass ex:C ;
            sh:property [ sh:or ( [ sh:property [ sh:path ex:p ; sh:minCount 1 ] ] ) ] .
    """, format="turtle")
    assert repair_pathless_property_shapes(shapes) == 1
    # The rule survives as its own node shape with the parent's target.
    assert len(set(shapes.subjects(RDF.type, SH.NodeShape))) == 2
    assert len(set(shapes.subjects(SH.targetClass, None))) == 2
    assert all(shapes.value(p, SH.path) is not None
               for _, p in shapes.subject_objects(SH.property)
               if (p, SH["or"], None) not in shapes)


def test_profile_follows_access_rights(dictionary_project, full_config):
    g = rdf.build(dictionary_project, full_config)
    assert profile_of(g) == "non-public"


@pytest.mark.skipif(not RELEASE_8.exists() or not os.environ.get("RUN_SHACL"),
                    reason="needs the pinned Release 8 shapes and RUN_SHACL=1 (slow)")
def test_full_configuration_conforms_to_release_8(dictionary_project, full_config):
    result = validate(rdf.build(dictionary_project, full_config), RELEASE_8)
    assert result.violations == []
    assert result.conforms
