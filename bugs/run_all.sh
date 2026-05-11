#!/usr/bin/env bash
# Run all four RMLMapper bug reproducers and print a concise verdict line
# for each. Run from the repo root (each child script cd's there).
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
for d in bugs/bug1_lookup_cache bugs/bug2_composite_key_join \
         bugs/bug3_split_collapse bugs/bug4_boolean_and_compile; do
    echo
    echo "########################################################"
    echo "# $d"
    echo "########################################################"
    bash "$d/run.sh"
done
