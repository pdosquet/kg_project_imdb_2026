# Class-hierarchy closure: two strategies

The ontology declares a real subclass hierarchy
(`book:BookContribution ⊑ cw:Contribution`,
`film:FilmContribution ⊑ cw:Contribution`,
`cw:Author ⊑ cw:Creator ⊑ cw:Role`, etc.). RML mappings emit instances at
the leaf type only. Without intervention, SPARQL queries on parent classes
return zero results — RDF stores do not consult `rdfs:subClassOf` axioms
unless a reasoner runs.

Two strategies were considered.

## Strategy 1: emit parent types in the mapping

Add additional `rdf:type` triples in YARRRML so each instance is typed
both at the leaf and at the relevant parent class:

```yaml
po:
  - [a, film:FilmContribution~iri]
  - [a, cw:Contribution~iri]      # added manually
```

**Pros**
- No new dependency, no extra pipeline step.
- Triples are explicit; provenance is visible in the mapping.

**Cons**
- The mapping has to know the ontology's hierarchy. Every time the
  ontology changes (new subclass, refactored superclass), every mapping
  has to be revisited.
- Only handles `rdf:type` closure. Inverse-property closure
  (`cw:hasAltTitle`/`cw:isAltTitleOf`), `owl:sameAs` symmetry/transitivity,
  and any further entailments still require manual handling or are simply
  absent.
- Doesn't scale: at ten subclasses across three hierarchies you are
  hand-maintaining redundant typing across many YARRRML files.

## Strategy 2: materialise OWL 2 RL closure (chosen)

Run a one-shot reasoner over the merged ontology + RML output and write
the closed graph back to disk. The triplestore serves the closed graph
as plain triples; no runtime reasoning is required.

Implementation: [preprocessing/infer_closure.py](preprocessing/infer_closure.py)
using [`owlrl`](https://pypi.org/project/owlrl/) (pure-Python OWL 2 RL
reasoner on top of `rdflib`). New pipeline step
`./run_pipeline.sh close` between mapping and load.

**Pros**
- Mappings stay focused on what the source data says; the ontology is the
  single source of truth for class hierarchy.
- Closes more than just subclass typing: inverse properties,
  `owl:sameAs` symmetry/transitivity, property-domain/range entailments,
  etc.
- Vendor-neutral: produces plain N-Triples that load into any
  triplestore. Switching to GraphDB later with `OWL 2 RL` ruleset gives
  the same semantics without the build-time step.

**Cons**
- Storage bloat: closed graph is ~2.6× the asserted graph.
- Build-time cost: ~10s on this dataset.
- Loss of provenance in the closed file (asserted vs inferred). The
  per-mapping `output/0*_*.nt` files remain on disk for debugging.
- One more pipeline step and two more Python dependencies (`rdflib`,
  `owlrl`).

## Numbers

| metric | strategy 1 | strategy 2 |
|---|---|---|
| pre-closure data triples | 13,892 | 13,577 |
| triples added by closure | — | 21,336 |
| total triples loaded | 13,892 | 35,785 |
| build-time cost (closure step) | 0 | ~10 s |
| `cw:Contribution` instances reachable | 663 (manual) | 662 (inferred) |
| `cw:Role` instances reachable | 0 | 57 |
| `cw:Creator` instances reachable | 0 | 10 |
| inverse-property triples | one direction only | both directions |
| `owl:sameAs` closure | no | yes |
| ontology change requires mapping edits | yes | no |

Strategy 1 only addressed `cw:Contribution`. The deeper Role/Creator
chain (`cw:Author ⊑ cw:Creator ⊑ cw:Role`) was still unreachable, and
adding manual typings everywhere would have replicated the ontology
inside the mappings.

## Why not a runtime reasoner

A runtime reasoner (Fuseki+inference, GraphDB ruleset) would also close
the graph, at the cost of slower queries and store-specific
configuration. Forward-chaining materialisation at build time achieves
the same query behaviour, keeps the runtime store stateless, and works
identically across triplestores. The choice is:

- **M3 (now)**: build-time materialisation with `owlrl`. Fuseki serves
  plain triples.
- **M4 (planned)**: GraphDB with `OWL 2 RL` ruleset can replace the
  build-time step with load-time materialisation if desired. The
  semantics are equivalent.

## Why OWL 2 RL specifically

OWL 2 defines three computational profiles (EL, QL, RL) plus the full
DL. The choice between them is not aesthetic — each is optimised for a
different evaluation strategy.

| profile | optimised for | why not here |
|---|---|---|
| RDFS | minimal subclass / subproperty closure | too thin: no `owl:sameAs` closure, no `owl:inverseOf` |
| OWL 2 EL | very large class hierarchies, polynomial subsumption | no `sameAs` closure, no inverse-property reasoning |
| OWL 2 QL | query rewriting (backward chaining over SQL/SPARQL) | wrong evaluation strategy — we want materialisation, not rewriting |
| OWL 2 RL | rule-based forward chaining, polynomial materialisation | **fits** |
| OWL 2 DL (full) | maximum expressivity, undecidable in some configs | needs HermiT/Pellet (Java), seconds-to-minutes per run, far more than we need |

Concretely, OWL 2 RL is the profile *designed* for materialising a closed
graph through forward chaining — which is exactly what
`infer_closure.py` does. It covers the entailments this project actually
relies on:

- `rdfs:subClassOf` and `rdfs:subPropertyOf` closure
- `owl:inverseOf` (both directions of a property pair)
- `owl:sameAs` symmetry and transitivity
- `rdfs:domain` / `rdfs:range` propagation
- `owl:TransitiveProperty`, `owl:SymmetricProperty`

It deliberately omits constructs that are expensive or undecidable in
forward-chaining settings — existential class expressions, qualified
cardinality restrictions, full DL reasoning. None of these are used for
query answering in this project.

A second, pragmatic reason: OWL 2 RL is the ruleset implemented by
nearly every production triplestore (GraphDB, Stardog, RDFox). Picking
RL at build time aligns the M3 build-time materialisation with the M4
GraphDB ruleset, so the graph behaves identically whether closed
offline by `owlrl` or online by GraphDB.

## Implementation gotcha: literal-subject triples

OWL 2 RL is defined in terms of the RDF *abstract* model, where the
distinction between literals and IRIs is a syntactic detail rather than
something the rules check. Two rules in particular fire indiscriminately
on every term that appears as a subject:

- **`cls-thing`** — every subject is `owl:Thing`. Applied blindly, a
  literal `"Roisin Md"` ends up with `"Roisin Md" rdf:type owl:Thing`.
- **`dt-type` family** — every literal is an instance of its declared
  datatype, producing triples like `"Roisin Md" rdf:type xsd:string`.

These are valid RDF *entailments* — semantically a literal *is* an
instance of its datatype — and `owlrl` materialises them faithfully. The
break happens at **serialisation**: the N-Triples and Turtle grammars
explicitly forbid literals in subject position. A subject must be an
IRI or a blank node, never a literal.

The result is that a freshly closed graph contains thousands of triples
that are well-formed in the abstract model but cannot be written to
N-Triples. `rdflib`'s serialiser writes them anyway; Fuseki then rejects
the whole upload on the first invalid line, returning HTTP 400 — and the
endpoint silently ends up holding only the ontology, with no data.

In this project the closure step produced ~5,100 such literal-subject
triples per run before the prune step was added.

[`preprocessing/infer_closure.py`](preprocessing/infer_closure.py) drops
them before serialising:

```python
for s, p, o in list(g):
    if isinstance(s, rdflib.Literal):
        g.remove((s, p, o))
```

Production triplestores (GraphDB, RDFox, Stardog) avoid this entirely:
they apply the same rules but suppress literal-subject triples at the
storage layer, treating them as implicitly true without persisting them.
`owlrl` is a faithful spec implementation that doesn't include this
practical filter, so the prune is left to the caller.

## Limitations of OWL 2 RL

`owlrl` runs the OWL 2 RL profile, which does not cover:

- Exact-cardinality-driven entailments (e.g., the `cw:hasRole` cardinality
  axiom in the ontology). These remain a design-time check via HermiT in
  Protégé and do not fire at materialisation time.
- Cross-endpoint reasoning. Federation queries against Wikidata or
  OpenLibrary are evaluated on the remote graph as-is.

Both limits are inherited from OWL 2 RL itself and would apply equally
to any RL-profile triplestore.
