#!/usr/bin/env bash
# Re-acquire Corpus A (public REDCap projects) and record exact provenance.
#
# Shallow-clones each source repository into corpus/<repo>/ and writes
# corpus/SOURCES.tsv with repo URL, commit SHA, selected file path and licence.
#
# Licences: NACC forms are copyrighted (https://naccdata.org/data-collection/guidelines-copyright);
# they are used locally and only referenced, never redistributed. corpus/ is git-ignored.
#
# Usage: ./fetch_corpus.sh            (idempotent; re-uses existing clones)
#        FRESH=1 ./fetch_corpus.sh    (delete and re-clone)
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p corpus

clone() { # owner/repo
  local repo="$1" dir="corpus/$(basename "$1")"
  if [[ -n "${FRESH:-}" ]]; then rm -rf "$dir"; fi
  if [[ ! -d "$dir/.git" ]]; then
    git clone --quiet --depth 1 "https://github.com/$repo" "$dir"
  fi
}

clone naccdata/uniform-data-set
clone IeDEA/redcap-dictionaries
clone redcap-tools/redcap-test-datasets
# Searched for the Michigan MDEN / Eisenberg Depression Center "Morning Light Stress Study"
# (1,257 questions). DepressionCenter/MDEN exists, but its REDCap-Examples/ folder holds only a
# README; the KB article (teamdynamix.umich.edu ... ArticleDet?ID=10813) states the XML is
# "for internal use by University of Michigan and Michigan Researchers only". Not public:
# cloned only to record the commit that was checked.
clone DepressionCenter/MDEN

sha() { git -C "corpus/$1" rev-parse HEAD; }

# source_id <TAB> domain <TAB> repo <TAB> path-in-repo <TAB> licence
SELECTION=$(cat <<'EOF'
iedea-Harmonist-CodeLists	HIV cohort data standard (IeDEA DES metadata)	IeDEA/redcap-dictionaries	Harmonist0BCodeLists_2017-12-21_1148.REDCap.xml	no licence file in repo (all rights reserved by default); referenced only
iedea-Harmonist-DataModel	HIV cohort data standard (IeDEA DES metadata)	IeDEA/redcap-dictionaries	Harmonist0ADataModel_2017-12-21_1147.REDCap.xml	no licence file in repo (all rights reserved by default); referenced only
iedea-tblCENTER	HIV care site registry (IeDEA DES)	IeDEA/redcap-dictionaries	IeDEA_tblCENTER_2020-06-30.csv	no licence file in repo (all rights reserved by default); referenced only
nacc-DownSyndromeModule	Dementia / Down syndrome (NACC UDS)	naccdata/uniform-data-set	forms/ds/DownSyndromeModule.REDCap.xml	NACC copyrighted forms (naccdata.org/data-collection/guidelines-copyright); code MPL-2.0; never redistribute
nacc-FormF2COVIDImpactSurvey-Participantv1.3	Dementia cohort COVID impact survey (NACC)	naccdata/uniform-data-set	forms/covid/legacy/f2/FormF2COVIDImpactSurvey-Participantv1.3.REDCap.xml	NACC copyrighted forms (naccdata.org/data-collection/guidelines-copyright); code MPL-2.0; never redistribute
nacc-FormF3COVID-CoParticipant	Dementia cohort COVID impact survey (NACC)	naccdata/uniform-data-set	forms/covid/legacy/f3/FormF3COVIDImpactSurvey-Co-Participantv1.2.REDCap.xml	NACC copyrighted forms (naccdata.org/data-collection/guidelines-copyright); code MPL-2.0; never redistribute
rtd-archer	Synthetic test project (REDCapR 'archer')	redcap-tools/redcap-test-datasets	archer/data-dictionary.csv	GPL-2.0
rtd-case01-crosssectional	Synthetic test project (all field types)	redcap-tools/redcap-test-datasets	case-01/test-case-01-data-dictionary.csv	GPL-2.0
rtd-case07-longitudinal	Synthetic test project (longitudinal, Sitka spruce)	redcap-tools/redcap-test-datasets	case-07/test-case-07-data-dictionary.csv	GPL-2.0
rtd-case20-randomization	Synthetic test project (randomization module)	redcap-tools/redcap-test-datasets	case-20/test-case-20-data-dictionary.csv	GPL-2.0
EOF
)

out=corpus/SOURCES.tsv
printf 'source_id\tdomain\trepo_url\tcommit_sha\tpath\tsha256\tlicence\n' > "$out"
while IFS=$'\t' read -r sid domain repo path licence; do
  dir=$(basename "$repo")
  file="corpus/$dir/$path"
  if [[ ! -f "$file" ]]; then
    echo "MISSING: $sid ($repo:$path)" >&2
    digest="MISSING"
  else
    digest=$(shasum -a 256 "$file" | cut -d' ' -f1)
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$sid" "$domain" "https://github.com/$repo" \
    "$(sha "$dir")" "$path" "$digest" "$licence" >> "$out"
done <<< "$SELECTION"

# Checked but excluded (not public): recorded for the paper's methods section.
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "EXCLUDED:mden-morning-light-stress" \
  "Sleep/mood research (U. Michigan Eisenberg Family Depression Center)" \
  "https://github.com/DepressionCenter/MDEN" "$(sha MDEN)" "REDCap-Examples/README.md (no XML in repo)" \
  "-" "GPL-3.0 repo; project XML internal to U-M (KB article 10813); not obtainable" >> "$out"

cat "$out"
