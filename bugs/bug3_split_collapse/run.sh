#!/usr/bin/env bash
# Repro: grel:string_split is iterated correctly when it is the OUTERMOST
# function in the term map. The moment a single-string function (e.g.
# grel:escape) wraps it, iteration collapses to the first element only.
#
# Source row r1: "Herself,Host"  -> expect 2 ex:name objects
# Source row r2: "Alice,Bob,Carol" -> expect 3 ex:name objects
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
DIR=bugs/bug3_split_collapse
run_case() {
    local tag="$1" yarrrml="$2"
    npx --yes -p @rmlio/yarrrml-parser yarrrml-parser \
        -i "$yarrrml" -o "$DIR/out_${tag}.rml.ttl" 2>/dev/null
    java -jar rmlmapper.jar -m "$DIR/out_${tag}.rml.ttl" \
        -s nquads -o "$DIR/out_${tag}.nq" 2>/dev/null
    echo "[$tag]"
    sort "$DIR/out_${tag}.nq"
    echo "[$tag] per-row counts:"
    grep -oE 'row/r[0-9]+' "$DIR/out_${tag}.nq" | sort | uniq -c
}
echo "=== bare grel:string_split (control) ==="
run_case bare "$DIR/mapping_bare.yarrrml"
echo
echo "=== grel:escape(grel:string_split(...)) (bug) ==="
run_case wrapped "$DIR/mapping_wrapped.yarrrml"
