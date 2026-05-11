#!/usr/bin/env bash
# Repro: when a function appears as a list element (i.e. one of multiple
# values to grel:param_rep_b for grel:boolean_and), the YARRRML→RML
# compiler emits fno:executes "undefined" for that inner function instead
# of the function's IRI. The compiled RML is unexecutable.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
DIR=bugs/bug4_boolean_and_compile
npx --yes -p @rmlio/yarrrml-parser yarrrml-parser \
    -i "$DIR/mapping.yarrrml" -o "$DIR/mapping.rml.ttl" 2>/dev/null
echo "--- fno:executes occurrences in compiled RML ---"
grep -n "fno:executes" "$DIR/mapping.rml.ttl" || echo "(none found)"
echo
echo "--- 'undefined' literal occurrences ---"
grep -n '"undefined"' "$DIR/mapping.rml.ttl" || echo "(none found)"
echo
echo "--- attempt to run rmlmapper (expected to fail or emit zero) ---"
java -jar rmlmapper.jar -m "$DIR/mapping.rml.ttl" -s nquads -o "$DIR/out.nq" 2>&1 \
  | tail -10 || true
echo "--- output triples ---"
wc -l "$DIR/out.nq" 2>/dev/null && cat "$DIR/out.nq" || echo "no output"
