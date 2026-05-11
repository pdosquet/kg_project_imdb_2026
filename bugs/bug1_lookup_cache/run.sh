#!/usr/bin/env bash
# Repro: idlab-fn:lookup cache keys on $(searchString) alone — it
# ignores `inputFile` / `fromColumn` / `toColumn`, so two lookups that
# differ only in those args return the SAME value per row.
#
# Expected: each row emits ex:lookupA "A<n>" and ex:lookupB "B<n>".
# Observed (bug): both predicates carry the SAME value per row.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
DIR=bugs/bug1_lookup_cache
npx --yes -p @rmlio/yarrrml-parser yarrrml-parser \
    -i "$DIR/mapping.yarrrml" -o "$DIR/mapping.rml.ttl" 2>/dev/null
java -jar rmlmapper.jar -m "$DIR/mapping.rml.ttl" -s nquads -o "$DIR/out.nq"
echo "--- output ---"
sort "$DIR/out.nq"
echo "--- pivot (A vs B per key) ---"
python3 - <<'PY'
import re, collections
rows = collections.defaultdict(dict)
for line in open("bugs/bug1_lookup_cache/out.nq"):
    m = re.match(r'<http://example\.org/row/(\w+)> <http://example\.org/lookup(\w)> "([^"]+)"', line)
    if m: rows[m.group(1)][m.group(2)] = m.group(3)
print(f"{'key':<6}{'A':<6}{'B':<6}{'A==B?'}")
for k, v in sorted(rows.items()):
    a, b = v.get('A','?'), v.get('B','?')
    print(f"{k:<6}{a:<6}{b:<6}{a==b}")
PY
