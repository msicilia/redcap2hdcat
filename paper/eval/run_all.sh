#!/usr/bin/env bash
# Reproduce every number of the evaluation, in order. Network is needed only for step 1
# (and for the optional online validator call in step 5).
#
# Inputs not fetched here:
#   ../../../workspace/ejemplo-test/proyecto-limpio.xml (+ CSV dictionary)  internal rectal project
#   ../../tests/fixtures/dmp.json                      synthetic DMP fixture
#   shapes/release-8/                                                     pinned HealthDCAT-AP Release 8
#                                                                          (see shapes/PIN.txt for URLs + sha256)
#   results/ir2026_2098/                                                  EUR-Lex text of IR (EU) 2026/2098
set -euo pipefail
cd "$(dirname "$0")"
PY=(uv run --project ../.. --extra shacl --extra dmp python)

./fetch_corpus.sh                       # 1. corpus/ + corpus/SOURCES.tsv
"${PY[@]}" run_corpus.py                # 2. results/corpus.csv, audit*.{json,csv}, records*/
"${PY[@]}" contribution.py              # 4. results/contribution*.csv, ir2026_2098_elements.csv, rectal/
"${PY[@]}" shacl_check.py               # 3. results/shacl_*.csv (needs records from steps 2 and 4)
"${PY[@]}" explain_shacl.py             # 3b. results/shacl_explained.csv (cause per result group)
# 3c. the tool's own `check --shapes` on the Release 8 shapes directory (crashes; kept as evidence)
uv run --project ../.. --extra shacl --extra dmp redcap2hdcat check \
  results/records/rtd-case07-longitudinal.ttl --shapes shapes/release-8/ehds/shapes --json \
  > results/logs/tool_check_shapes_dir.txt 2>&1 || echo "exit=$?" >> results/logs/tool_check_shapes_dir.txt
# 5. optional, sends ONE public corpus record to the official HealthData@EU validator:
# ./itb_validate.sh results/records/rtd-case07-longitudinal.ttl
"${PY[@]}" itb_compare.py rtd-case07-longitudinal   # uses the stored online report in results/itb/
