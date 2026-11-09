# redcap2hdcat

Derive [HealthDCAT-AP](https://healthdcat-ap.github.io/) catalogue records from REDCap
project metadata.

Article 77 of Regulation (EU) 2025/327 (EHDS) requires Health Data Access Bodies to publish
catalogues describing the datasets under their responsibility. REDCap holds a substantial share
of European public clinical research data — 3,372 institutions, 677,000 projects — and every
one of those projects is a dataset that will have to be catalogued. The metadata already exists
in the data dictionary and the project configuration. Nobody is harvesting it.

This tool reads a REDCap project's **structure** and emits a conformant HealthDCAT-AP record,
asking the human only for what cannot be derived.

**It never writes to REDCap, never reads patient records, and runs entirely on your machine.**

## Install

```bash
pip install redcap2hdcat
```

With SHACL conformance checking:

```bash
pip install "redcap2hdcat[shacl]"
```

## Use

```bash
# 1. Audit a data dictionary. No configuration needed.
redcap2hdcat audit project.xml

# 2. Set up your institution once.
redcap2hdcat init-config -o institution.yaml

# 3. Generate the record for each project.
redcap2hdcat build project.xml -c institution.yaml -o record.ttl

# 3b. Compose with a machine-actionable DMP (fills institute, responsible, licence,
#     description) and add semantic coding. Needs the 'dmp' extra.
redcap2hdcat build project.xml -c institution.yaml \
    --dmp plan.json --snomed -o record.ttl

# 4. Check conformance. --shapes takes the HealthData@EU validator folder published with
#    each HealthDCAT-AP release (the one holding config.properties); the profile follows
#    the record's access rights. A plain folder of .ttl shapes also works.
redcap2hdcat check record.ttl --shapes ./healthdcat-ap/release-8/ehds/

# 5. Generate a synthetic sample distribution.
redcap2hdcat sample project.xml -n 100 -o sample.csv

```

To browse the resulting records as a human-readable catalogue, use the separate,
disposable companion tool [redcap2hdcat-viewer](../viewer/) — it is intentionally not part
of this library.

## Composition: REDCap + DMP + coding

A REDCap export describes the instrument, not the dataset as a governed asset. The
institute, responsible person, licence, legal basis and a real description live in the
study's **data management plan**. Pass a machine-actionable DMP (RDA DMP Common
Standard, read via [madmpy](https://pypi.org/project/madmpy/)) with `--dmp`, and it
fills the fields REDCap cannot — without ever overwriting a value REDCap already has.

Terminology codes attach at three levels: dataset (`healthdcatap:hasCodingSystem`),
form (`dct:subject` on each CSVW table) and field (`skos:exactMatch` on the column).
REDCap has no native slot for codes, so the convention is to write them in the field
annotation as `@CODE=SNOMED:22298006` (repeatable; other action tags are ignored).

> `--snomed` also enables a **demonstration** mapper that guesses SNOMED concepts from
> field labels. The codes are real SNOMED identifiers but the assignment is heuristic
> and **not clinically validated** — a proof of concept, not production annotation.

Exit codes: `0` conformant, `1` non-conformant or errors found, `2` usage or input error.
`audit --json` emits structured findings, so running the tool over many projects produces an
analysable corpus as a by-product.

### Input formats

| Input | Get it from | Coverage |
|---|---|---|
| **Project XML** (preferred) | *Other Functionality* → *Download Project XML*, **metadata only** | Events, arms, repeating instruments, structured code lists |
| **Data dictionary CSV** | *Dictionary* → *Download* | Variables only; no longitudinal structure |

The Project XML export can contain the complete clinical record of your cohort. This tool
**refuses to process any file containing `<ClinicalData>`** and tells you to re-export with
metadata only. Always select "metadata only".

## What it derives

Of the seven mandatory `dcat:Dataset` properties, two are automatic, one is constant, and four
need a human — but three of those four are **institutional configuration set once**, not per
project. The marginal cost of the 200th project approaches zero.

The variable dictionary maps almost 1:1 onto [CSVW](https://www.w3.org/TR/tabular-data-primer/),
which gives the record a second, column-level layer. That layer carries per-column PII labels
derived from REDCap's `Identifier?` flag, which governance catalogues such as OpenMetadata and
DataHub consume natively.

## Audit rules

| Rule | Severity |
|---|---|
| `unflagged-identifier` | error |
| `coded-without-choices` | error |
| `duplicate-choice-code` | error |
| `dangling-branching-reference` | error |
| `inconsistent-coding` | warning |
| `numeric-without-range` | warning |
| `unconstrained-text` | warning |
| `missing-label` | warning |
| `date-not-reviewed` | info |

> Audit reports name fields that leak identifiers. They are for internal use and must never be
> published through the same channel as the catalogue.

## Scope

Deliberately **not** built, because it already exists:

- **Conformance validation** → HealthData@EU Validator and the official SHACL shapes
- **Manual authoring** → Dataset Descriptions Assistant (DG SANTE)
- **Catalogue portal** → CKAN with `ckanext-dcat` (ships the `euro_health_dcat_ap` profile)
- **Terminology mapping** → Usagi (OHDSI), OntoBridge

Also out of scope: OMOP CDM mapping, semantic annotation with SNOMED/LOINC, and any write path
back into REDCap.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
```

Dependencies are pure Python by design (no `lxml`, no `pandas`, no C extensions) so the same
code can run under Pyodide in the browser — a delivery route for users who do not program,
which keeps data on their machine.

## Status

Alpha. The CSV and ODM adapters, the auditor, the RDF and CSVW serialisers and the synthetic
sample generator work. The API adapter is not built yet; record counts and temporal coverage
depend on it.

`healthdcatap:hdab` is mandatory in the specification, but the Spanish HDAB has not been
designated yet. The tool leaves it empty and reports the record as non-conformant rather than
inventing a value.

## Licence

Apache-2.0.
