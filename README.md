# redcap2hdcat

redcap2hdcat composes a [HealthDCAT-AP](https://data.health.europa.eu/healthdcat-ap/) dataset
description, the metadata profile required for dataset catalogues under the European Health
Data Space, from three sources: the structure of a REDCap project (Project XML or data
dictionary CSV), institutional settings written once, and optionally a machine-actionable
data management plan (RDA DMP Common Standard). The variables are described with CSV on the
Web, terminology codes are read from `@CODE` and ROME `@ONTOLOGY` field annotations, and the
record is validated against the official SHACL shapes. The tool reads only the structure of a
project and rejects an export that contains patient records.

## Install

```bash
pip install "redcap2hdcat[shacl,dmp] @ git+https://github.com/msicilia/redcap2hdcat"
```

Python 3.10 or later. The `shacl` extra enables `check`; the `dmp` extra enables `--dmp`.

## Use

```bash
# Institutional settings, written once (YAML, or Turtle as a partial HealthDCAT-AP record).
redcap2hdcat init-config -o institution.yaml

# The record of a project; add --dmp to complete it from the study's plan.
redcap2hdcat build project.xml -c institution.yaml -o record.ttl
redcap2hdcat build project.xml -c institution.yaml --dmp plan.json -o record.ttl

# Conformance against the validator folder published with a HealthDCAT-AP release.
redcap2hdcat check record.ttl --shapes ./healthdcat-ap/release-8/ehds/

# Design problems in a data dictionary; a synthetic sample; an export without records.
redcap2hdcat audit project.xml
redcap2hdcat sample project.xml -n 100 -o sample.csv
redcap2hdcat strip export.xml -o project.xml
```

Export the Project XML with *metadata only*. Exit codes: `0` conformant, `1` non-conformant or
findings, `2` usage or input error.

## More

- [MAPPING.md](MAPPING.md): where each HealthDCAT-AP property comes from.
- [eval/run_all.sh](eval/run_all.sh): the evaluation over public REDCap projects;
  `eval/results/viewer.html` shows each record with the source of every element.
- Development: `uv sync`, `uv run pytest`, `uv run ruff check .`

Licence: Apache-2.0.
