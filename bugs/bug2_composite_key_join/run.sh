#!/usr/bin/env bash
# Repro: composite-key (two-column) template joins emit zero triples even
# when both columns are non-empty. A single-column join with identical
# data fires correctly.
#
# Control:  condition uses one column      -> 3 ex:joined triples
# Bug:      condition concatenates two cols -> 0 ex:joined triples
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
DIR=bugs/bug2_composite_key_join
run_case() {
    local tag="$1" yarrrml="$2"
    npx --yes -p @rmlio/yarrrml-parser yarrrml-parser \
        -i "$yarrrml" -o "$DIR/out_${tag}.rml.ttl" 2>/dev/null
    java -jar rmlmapper.jar -m "$DIR/out_${tag}.rml.ttl" \
        -s nquads -o "$DIR/out_${tag}.nq" 2>/dev/null
    local n
    n=$(grep -c "ex:joined\|/joined" "$DIR/out_${tag}.nq" 2>/dev/null || echo 0)
    n=$(grep -c "joined" "$DIR/out_${tag}.nq" || echo 0)
    echo "[$tag] join triples emitted: $n"
    grep "joined" "$DIR/out_${tag}.nq" || true
}
echo "=== single-column join (control) ==="
run_case single "$DIR/mapping_single.yarrrml"
echo
echo "=== composite-key join (bug) ==="
run_case composite "$DIR/mapping_composite.yarrrml"
