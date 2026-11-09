from redcap2hdcat.core.audit import audit


class TestIdentifierDetection:
    def test_flags_unflagged_medical_record_number(self, dictionary_project):
        # The headline metric of the empirical study.
        rules = {(f.rule, f.variable) for f in audit(dictionary_project).findings}
        assert ("unflagged-identifier", "nhc") in rules

    def test_flags_email_by_validation_type(self, dictionary_project):
        rules = {(f.rule, f.variable) for f in audit(dictionary_project).findings}
        assert ("unflagged-identifier", "email_contacto") in rules

    def test_does_not_flag_correctly_marked_field(self, dictionary_project):
        offenders = {f.variable for f in audit(dictionary_project).findings
                     if f.rule == "unflagged-identifier"}
        assert "fecha_nacimiento" not in offenders

    def test_record_id_is_exempt(self, dictionary_project):
        offenders = {f.variable for f in audit(dictionary_project).findings
                     if f.rule == "unflagged-identifier"}
        assert "record_id" not in offenders


class TestDesignRules:
    def test_detects_dangling_branching_reference(self, dictionary_project):
        findings = [f for f in audit(dictionary_project).findings
                    if f.rule == "dangling-branching-reference"]
        assert len(findings) == 1
        assert findings[0].detail == "inexistente"

    def test_branching_reference_to_declared_variable_is_fine(self, dictionary_project):
        details = {f.detail for f in audit(dictionary_project).findings
                   if f.rule == "dangling-branching-reference"}
        assert "peso" not in details

    def test_detects_numeric_without_range(self, dictionary_project):
        offenders = {f.variable for f in audit(dictionary_project).findings
                     if f.rule == "numeric-without-range"}
        assert "altura" in offenders
        assert "peso" not in offenders  # declares 30..250

    def test_detects_inconsistent_coding(self, dictionary_project):
        # 'sexo' and 'tratamiento' share a label but not a value set.
        rules = {f.rule for f in audit(dictionary_project).findings}
        assert "inconsistent-coding" in rules

    def test_detects_unconstrained_free_text(self, dictionary_project):
        offenders = {f.variable for f in audit(dictionary_project).findings
                     if f.rule == "unconstrained-text"}
        assert "observaciones" in offenders


class TestReport:
    def test_serialises_for_the_corpus_study(self, dictionary_project):
        payload = audit(dictionary_project).to_dict()
        assert payload["variable_count"] == 12
        assert payload["form_count"] == 3
        assert payload["error_count"] > 0
        assert payload["counts_by_rule"]["unflagged-identifier"] == 2
        assert all({"rule", "severity", "variable"} <= set(f) for f in payload["findings"])

    def test_longitudinal_flag_recorded(self, odm_project, dictionary_project):
        assert audit(odm_project).to_dict()["is_longitudinal"] is True
        assert audit(dictionary_project).to_dict()["is_longitudinal"] is False
