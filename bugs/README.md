# RMLMapper bug reproducers

Minimal failing examples for the four bugs that force preprocessing in
[preprocessing/preprocess.py](../preprocessing/preprocess.py). Each bug
corresponds to one file in [data/generated/](../data/generated/) that
RML/YARRRML should in principle express directly.

## Toolchain under test

| Component | Version / build |
|---|---|
| `rmlmapper.jar` | 191904491 bytes, mtime 2026-05-03 (jar in repo root) |
| `@rmlio/yarrrml-parser` | 1.12.2 (via `npx`) |
| Java | OpenJDK 21.0.11 |

## How to run

```bash
./bugs/run_all.sh           # runs all four
./bugs/bug1_lookup_cache/run.sh
./bugs/bug2_composite_key_join/run.sh
./bugs/bug3_split_collapse/run.sh
./bugs/bug4_boolean_and_compile/run.sh
```

Each `run.sh` compiles its YARRRML, invokes RMLMapper, and prints the
relevant slice of output. Run from the repo root (each script `cd`s
there itself).

## Summary

| # | Bug | Generated CSV that works around it | Verified |
|---|---|---|---|
| 1 | `idlab-fn:lookup` cache keys on the search string alone, ignoring `inputFile` / `fromColumn` / `toColumn` | `title_structure_lookup.csv` | yes |
| 2 | Composite-key template joins (`$(a)\|$(b)` on both sides of `equal`) emit zero triples even when both columns are non-empty | `title_principal_resolved.csv` | yes |
| 3 | Iteration over `grel:string_split` collapses to first-element-only when the split is wrapped by a single-string function (e.g. `grel:escape`) | `characters.csv` | yes |
| 4 | YARRRML→RML compiler emits `fno:executes "undefined"` when a function appears as a list element inside `grel:boolean_and` | `region_iso_lookup.csv` | yes |

## Observed outputs (this build)

### Bug 1 — lookup cache

Two `idlab-fn:lookup` calls per row, pointing at **different** files
(`lookupA.csv` returns `A1/A2/A3`, `lookupB.csv` returns `B1/B2/B3`).
Expected per row: `ex:lookupA "An"`, `ex:lookupB "Bn"`.

Observed:
```
<…/row/k1> <…/lookupA> "A1" .
<…/row/k1> <…/lookupB> "A1" .   ← should be "B1"
<…/row/k2> <…/lookupA> "A2" .
<…/row/k2> <…/lookupB> "A2" .   ← should be "B2"
<…/row/k3> <…/lookupA> "A3" .
<…/row/k3> <…/lookupB> "A3" .   ← should be "B3"
```

`A == B` for every key. The second-declared lookup is returning values
from the first-declared lookup's file. Cache key only uses the search
string.

### Bug 2 — composite-key join

Same data, two mappings differing only in the `equal` condition:

| Condition | Triples emitted |
|---|---|
| `equal($(key1), $(key1))` (single column) | 3 |
| `equal($(key1)\|$(key2), $(key1)\|$(key2))` (composite) | 0 |

Both `key1` and `key2` are non-empty in every row. The control proves
the data, sources, and parentTriplesMap wiring are correct; only the
template-on-both-sides composite key fails.

### Bug 3 — list-iteration collapse

Source row `r1 = "Herself,Host"`, `r2 = "Alice,Bob,Carol"`.

| Term map | Triples for r1 | Triples for r2 |
|---|---|---|
| `grel:string_split` alone | 2 | 3 |
| `grel:escape(grel:string_split(...))` | 1 (`"Herself"` only) | 1 (`"Alice"` only) |

Wrapping the split in any single-string function discards all but the
first list element.

### Bug 4 — `grel:boolean_and` compile

YARRRML uses two `idlab-fn:notEqual` calls as list elements of
`grel:param_rep_b`. The compiled RML at
[bug4_boolean_and_compile/mapping.rml.ttl](bug4_boolean_and_compile/mapping.rml.ttl)
contains:

```turtle
:omexec_002 rr:constant "undefined";
    rr:termType rr:IRI.
```

i.e. one of the inner functions has been lowered to the literal string
`"undefined"` rather than its function IRI. At runtime, RMLMapper
throws an exception trying to resolve it (stack trace in
`bug4_boolean_and_compile/out.nq`'s stderr). The condition then fails
open and the predicate-object is emitted unconditionally, which is the
worst possible failure mode — wrong output, no clean error.

## Notes on what this proves

- The four transformations are expressible in RML in principle.
  `idlab-fn:lookup` is a standard FnO function, composite-key joins are
  a standard RML feature, list iteration over `grel:string_split` is
  documented behaviour, and `grel:boolean_and` is in the GREL function
  library.
- The workarounds in [preprocessing/preprocess.py](../preprocessing/preprocess.py)
  exist to compensate for engine and compiler defects, not for language
  expressivity gaps.
- A different RMLMapper build, or a different RML processor, would in
  principle remove the need for these four CSVs.
