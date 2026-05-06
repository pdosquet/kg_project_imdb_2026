#!/usr/bin/env python3
"""
Materialise OWL 2 RL closure over the merged ontology + RML output.

Reads:
  ontologies/*.ttl
  output/*.nt    (excluding output/closed.nt)

Writes:
  output/closed.nt
"""
import glob
import sys
import time
from pathlib import Path

import owlrl
import rdflib

ROOT = Path(__file__).resolve().parents[1]
ONT_DIR = ROOT / "ontologies"
OUT_DIR = ROOT / "output"
CLOSED = OUT_DIR / "closed.nt"


def main():
    g = rdflib.Graph()

    for f in sorted(ONT_DIR.glob("*.ttl")):
        g.parse(f, format="turtle")
    ont_count = len(g)
    print(f"  ontologies: {ont_count} triples from {len(list(ONT_DIR.glob('*.ttl')))} files")

    for f in sorted(OUT_DIR.glob("*.nt")):
        if f.name == CLOSED.name:
            continue
        g.parse(f, format="nt")
    print(f"  + data:     {len(g) - ont_count} triples")

    before = len(g)
    t0 = time.time()
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)
    elapsed = time.time() - t0
    print(f"  closure:   {len(g) - before} new triples added in {elapsed:.1f}s")

    # OWL 2 RL closure produces type triples like `"foo" rdf:type xsd:string`
    # where the subject is a literal. These are invalid in N-Triples and
    # rejected by Fuseki on upload, so drop them.
    dropped = 0
    for s, p, o in list(g):
        if isinstance(s, rdflib.Literal):
            g.remove((s, p, o))
            dropped += 1
    if dropped:
        print(f"  pruned:    {dropped} literal-subject triples (invalid in N-Triples)")

    g.serialize(CLOSED, format="nt")
    print(f"  wrote {CLOSED} ({len(g)} triples total)")


if __name__ == "__main__":
    sys.exit(main())
