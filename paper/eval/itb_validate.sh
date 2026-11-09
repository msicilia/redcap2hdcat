#!/usr/bin/env bash
# Validate ONE public corpus record with the official HealthData@EU (ITB) validator, domain 'ehds',
# validation type 'non-public', and store the reports. Only Corpus A records built with the
# fictional institutional config may be sent; the internal rectal project is never sent.
#
# Usage: ./itb_validate.sh [record.ttl]   (default: results/records/rtd-case07-longitudinal.ttl)
set -euo pipefail
cd "$(dirname "$0")"
REC="${1:-results/records/rtd-case07-longitudinal.ttl}"
case "$REC" in *rectal*) echo "refusing to send the internal rectal project" >&2; exit 2;; esac
BASE="https://health-data-itb-rdf-validator.data.health.europa.eu/shacl"
OUT=results/itb; mkdir -p "$OUT"
name=$(basename "$REC" .ttl)
b64=$(base64 < "$REC" | tr -d '\n')
curl -sS "$BASE/ehds/api/info" -o "$OUT/info.json"
for syntax in text/turtle application/json; do
  ext=$([[ $syntax == text/turtle ]] && echo ttl || echo json)
  printf '{"contentToValidate":"%s","embeddingMethod":"BASE64","contentSyntax":"text/turtle","validationType":"non-public","reportSyntax":"%s","locale":"en"}' \
    "$b64" "$syntax" > "$OUT/request.$ext.json"
  curl -sS -X POST "$BASE/ehds/api/validate" -H 'Content-Type: application/json' \
    --data @"$OUT/request.$ext.json" -D "$OUT/$name.report.$ext.headers.txt" -o "$OUT/$name.report.$ext"
  rm -f "$OUT/request.$ext.json"
done
date -u +"%Y-%m-%dT%H:%M:%SZ  $REC  sha256=$(shasum -a 256 "$REC" | cut -d' ' -f1)" >> "$OUT/SENT.log"
ls -la "$OUT"
