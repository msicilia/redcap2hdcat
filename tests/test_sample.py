import csv
import io

from redcap2hdcat.core.columns import expand
from redcap2hdcat.core.sample import generate


def _rows(text: str):
    return list(csv.DictReader(io.StringIO(text)))


class TestSyntheticSample:
    def test_header_matches_the_csvw_columns(self, dictionary_project):
        text = generate(dictionary_project, rows=3)
        header = next(csv.reader(io.StringIO(text)))
        assert header == [c.name for c in expand(dictionary_project)]

    def test_row_count(self, dictionary_project):
        assert len(_rows(generate(dictionary_project, rows=7))) == 7

    def test_record_id_is_a_sequence(self, dictionary_project):
        rows = _rows(generate(dictionary_project, rows=4))
        assert [r["record_id"] for r in rows] == ["1", "2", "3", "4"]

    def test_coded_values_come_from_the_value_set(self, dictionary_project):
        rows = _rows(generate(dictionary_project, rows=20))
        assert {r["sexo"] for r in rows} <= {"1", "2", "3"}

    def test_numeric_values_respect_declared_range(self, dictionary_project):
        rows = _rows(generate(dictionary_project, rows=20))
        assert all(30.0 <= float(r["peso"]) <= 250.0 for r in rows)

    def test_checkbox_columns_are_flags(self, dictionary_project):
        rows = _rows(generate(dictionary_project, rows=10))
        assert {r["comorbilidades___1"] for r in rows} <= {"0", "1"}

    def test_deterministic_for_a_given_seed(self, dictionary_project):
        assert generate(dictionary_project, rows=5, seed=42) == \
            generate(dictionary_project, rows=5, seed=42)

    def test_longitudinal_events_are_valid(self, odm_project):
        rows = _rows(generate(odm_project, rows=10))
        assert {r["redcap_event_name"] for r in rows} <= {"baseline_arm_1", "month12_arm_1"}
