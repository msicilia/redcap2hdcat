# REDCap → HealthDCAT-AP mapping

**Goal:** automatically derive a conformant HealthDCAT-AP record from a REDCap project,
asking the human only for what cannot be derived.

**Reference version:** HealthDCAT-AP Release 5 (EC Draft Specification, 2025-09-22).
⚠️ Release 5 is marked *deprecated*; a `latest` version exists. Pin the version before
implementing.

**REDCap sources used:** REST API, endpoints `content=project`, `content=metadata`,
`content=instrument`, `content=exportFieldNames`, `content=user`, `content=record`
(aggregates only), `content=event` / `content=repeatingFormsEvents` (longitudinal projects).

**Derivability legend:**

| Code | Meaning |
|---|---|
| **AUTO** | Derived without human intervention |
| **CONST** | Known constant (configured once, not per project) |
| **SEMI** | Derived heuristically; needs human confirmation |
| **MANUAL** | Not derivable; supplied by the human or institutional configuration |

---

## 1. Dataset class — mandatory properties

These seven are blocking: without them there is no conformance.

| Property | Card. | REDCap source | Deriv. | Notes |
|---|---|---|---|---|
| `dct:title` | 1..* | `project.project_title` | **AUTO** | Add a language tag (mandatory on free text) |
| `dct:description` | 1..* | `project.project_notes` | **SEMI** | Optional in REDCap and often empty → needs a human fallback |
| `dct:identifier` | 1..n | `project.project_id` + instance base URL | **AUTO** | Build a global URI; see §5 on identifiers |
| `dct:accessRights` | 1 | — | **MANUAL** | NAL access-right. Reasonable default: `NON_PUBLIC` |
| `dcatap:applicableLegislation` | 1..n | — | **CONST** | `http://data.europa.eu/eli/reg/2025/327/oj` |
| `healthdcatap:healthCategory` | 1..* | — | **MANUAL** | Mandatory EHDS Art. 51 vocabulary |
| `healthdcatap:hdab` | 1..1 | — | **MANUAL** | Institutional configuration, not per project |

**Reading:** of seven mandatory properties, two are AUTO, one is constant, and four need a
human — but **three of those four are configured once per institution**, not per project.
The marginal cost per project is low.

---

## 2. Dataset class — derivable properties (the real value)

| Property | Card. | REDCap source | Deriv. | Notes |
|---|---|---|---|---|
| `dct:language` | 0..* | `project.project_language` | **AUTO** | Needs a table → NAL `language` (URI, not ISO literal) |
| `dct:issued` | 0..1 | `project.creation_time` | **AUTO** | |
| `dct:modified` | 0..1 | `content=log` (last change) | **SEMI** | Cheap alternative: export date |
| `healthdcatap:numberOfRecords` | 0..1 | `count(records)` | **AUTO** | In longitudinal = rows, not patients |
| `healthdcatap:numberOfUniqueIndividuals` | 0..1 | `distinct(record_id)` | **AUTO** | Distinguish from the previous |
| `dct:temporal` | 0..* | min/max of date fields | **AUTO** | Date fields identified by `text_validation_type` |
| `healthdcatap:minTypicalAge` / `maxTypicalAge` | 0..1 | age or birth-date field | **SEMI** | Heuristic detection by name/label |
| `dpv:hasPersonalData` | 0..1 | dictionary `identifier` flag | **SEMI** | If ≥1 field flagged → `true`. Beware the false negative (§4) |
| `dcat:contactPoint` | 0..n | `project_pi_*` + `content=user` | **SEMI** | Email with mandatory `mailto:` prefix |
| `dct:creator` | 0..* | `project_pi_firstname/lastname` | **SEMI** | |
| `dpv:hasPurpose` | 0..* | `project.purpose` (0–4) | **SEMI** | Partial mapping: 2=Research, 3=Quality Improvement… |
| `dcat:keyword` | 0..* | instrument labels | **SEMI** | Weak heuristic; useful as a suggestion |
| `dct:isReferencedBy` | 0..* | `project_irb_number`, `project_grant_number` | **MANUAL** | Not publications, but help find them |

---

## 3. Dataset class — not derivable

Nothing in REDCap holds this information. It goes to configuration or a human form.

`dct:publisher` (+ its mandatory `contactPoint` and NAL Health Publisher Types `type`) ·
`dcat:theme` (NAL data-theme; in practice almost always `HEAL`) · `healthdcatap:healthTheme` ·
`dpv:hasLegalBasis` · `healthdcatap:retentionPeriod` · `dct:accrualPeriodicity` ·
`prov:wasGeneratedBy` (NAL Health Activity) · `dct:conformsTo` · `healthdcatap:hasCodingSystem` ·
`dqv:hasQualityAnnotation` · licence and `dct:rights`.

> **Useful hook:** the dictionary `field_annotation` field accepts `@` action tags. Some
> institutions already use it for ontology codes. If populated, `hasCodingSystem` and
> `csvw:propertyUrl` stop being MANUAL. It is the natural entry point for OntoBridge.

---

## 4. Variable dictionary → CSVW

**This is the strong finding.** The specification defines the variable dictionary through
CSVW, linked from the *sample distribution*'s `dcat:downloadURL`. The REDCap dictionary maps
almost 1:1.

| `csvw:Column` | Card. | REDCap dictionary column | Deriv. |
|---|---|---|---|
| `csvw:name` | 1..n | `field_name` | **AUTO** |
| `csvw:titles` | 1..n | `field_label` | **AUTO** |
| `dct:description` | 1..n | `field_note` (only when present) | **AUTO** |
| `csvw:datatype` | 1 | `field_type` + `text_validation_type_or_show_slider_number` | **AUTO** |
| `csvw:propertyUrl` | 0..1 | `field_annotation` if codes present | **MANUAL** |

### Type table

| REDCap `field_type` | + validation | `csvw:datatype` |
|---|---|---|
| `text` | `integer` | `integer` |
| `text` | `number`, `number_1dp`… | `decimal` |
| `text` | `date_ymd`, `date_dmy`, `date_mdy` | `date` |
| `text` | `datetime_*`, `datetime_seconds_*` | `dateTime` |
| `text` | `time` | `time` |
| `text` | `email`, `phone`, `zipcode` | `string` |
| `text` | (none) | `string` |
| `notes` | — | `string` |
| `radio`, `dropdown`, `yesno`, `truefalse` | — | `integer` if numeric codes, else `string` |
| `checkbox` | — | **explodes into N boolean columns** — see below |
| `calc` | — | `decimal` |
| `slider` | — | `integer` |
| `descriptive`, `file`, `signature` | — | not data columns → omit |

### Known pitfalls

1. **`checkbox` explodes.** A checkbox field with 5 options produces 5 columns
   `field___1 … field___5` on export. The CSVW dictionary must describe **the exported
   shape**, not the dictionary shape. → use `content=exportFieldNames`, do not derive by hand.
2. **Longitudinal / repeating.** `redcap_event_name`, `redcap_repeat_instrument` and
   `redcap_repeat_instance` appear in the export but **do not exist in the dictionary**.
   Add them from `content=event` / `content=repeatingFormsEvents`.
3. **`record_id`** (first field) is the identifier; its name is configurable.
4. **The sample distribution must be synthetic and anonymised.** Real data cannot be
   published. See §6.

---

## 5. Support classes

| Class | Requirement | Deriv. |
|---|---|---|
| **Catalogue** | `title` 1..*, `description` 1..*, `applicableLegislation` 1..*, `themeTaxonomy` must include the NAL data-theme | **MANUAL** (one per institution, not per project) |
| **Distribution** | `accessURL` 1..*, `applicableLegislation` 1..* | **SEMI** — the project URL or API endpoint |
| **Kind** (contact point) | email with `mailto:` prefix **or** a contact page | **SEMI** |
| **Publisher** | `contactPoint` 1 (mandatory), NAL `type` | **MANUAL** |
| **HDAB** | `name` 1..*, `contactPoint` 1 | **MANUAL** |

**Identifiers:** DCAT-AP assumes global URIs because it is designed for harvesting
networks. A REDCap `project_id` is local to the instance. Build a stable URI of the form
`https://{instance}/dataset/{project_id}` and document the policy.

---

## 6. A useful by-product

The spec requires the *sample distribution* to be a **synthetic and anonymised** sample,
and the CSVW dictionary describes its columns.

Since the REDCap dictionary already gives types, ranges (`text_validation_min/max`) and
option sets (`select_choices_or_calculations`), **generating that synthetic CSV is nearly
free**: it respects the structure without touching a single real value. It is the tractable
version of the synthetic-data idea that was otherwise too hard.

---

## 7. Effort estimate

| Block | Effort |
|---|---|
| Dictionary parsing + CSVW generation | 1–2 days |
| Dataset skeleton with AUTO/CONST fields | 1 day |
| Institutional config (publisher, HDAB, catalogue) | 0.5 day |
| RDF serialisation (`rdflib`) | 0.5 day |
| Record aggregates (count, temporal, ages) | 1–2 days |
| Checkbox / longitudinal handling | 2–3 days ← **the risk is here** |
| Synthetic sample generator | 1–2 days |
| Validation against the official validator | 0.5 day |

**Realistic MVP: 1–2 weeks** of effective work, not a month. Most of the risk is not in
HealthDCAT-AP but in REDCap export quirks.

**Do not build:** a custom validator (the HealthData@EU Validator exists, based on the
published SHACL shapes) nor a manual editor (the Dataset Descriptions Assistant exists).

---

## 8. Next steps

1. Get a real or example REDCap dictionary and run parsing → CSVW.
2. Download `non-public-shapes.ttl` + `range.ttl` + `mdr-vocabularies.shape.ttl` and validate
   locally with `pySHACL` before touching the official validator.
3. Check what changes in the `latest` version compared to Release 5.
4. Open an issue at `https://code.europa.eu/healthdataeu/healthdcat-ap/-/issues` asking
   whether there is prior work on automated harvesting from data-capture systems.
