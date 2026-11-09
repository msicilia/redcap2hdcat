Results of the evaluation run on 2026-11-08 against redcap2hdcat 0.1.0 (git tag
eval-baseline), before the Release 8 conformance fixes. Kept for traceability.

itb/ holds the only call made to the official HealthData@EU validator (one public record,
rtd-case07-longitudinal). Its comparison with the local pySHACL set-up
(itb/compare_*.csv) shows that the local checker reproduces the official validator group by
group; that finding does not depend on the tool version.

The rectal-project counterpart is in ../rectal/baseline-0.1.0/ (local only).
