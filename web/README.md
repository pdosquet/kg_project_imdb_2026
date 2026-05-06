# Cultural Works Browser

Single-page React app implementing the spec in [../web_requirements.md](../web_requirements.md). Ontology-driven faceted browser over a Fuseki SPARQL endpoint.

## Run

```bash
npm install
cp .env.example .env       # adjust if your endpoint differs
npm run dev                # binds 0.0.0.0:8080 — reachable from LAN at http://<server-host>:8080
```

By default the app talks to Fuseki via a Vite dev-server proxy: the browser fetches `/sparql`, Vite forwards it to `http://localhost:3030/culturalworks/sparql` on the host running `npm run dev`. This means CORS does not need to be enabled on Fuseki and the laptop never talks to port 3030 directly. To bypass the proxy, set `VITE_SPARQL_ENDPOINT` to a full URL in `.env` (Fuseki must then allow CORS).

## Build / typecheck

```bash
npm run build       # tsc + vite build
npm run typecheck   # tsc only
```

## Configuration

Environment variables (see `.env.example`):

| Var | Default | Meaning |
|---|---|---|
| `VITE_SPARQL_ENDPOINT` | `http://localhost:3030/culturalworks/sparql` | Fuseki query URL |
| `VITE_ROOTS` | `…#CreativeWork,…#RealPerson` | Comma-separated full IRIs of browseable root classes |
| `VITE_APP_TITLE` | `Cultural Works Browser` | Header bar title |

Switching roots is a UI action (header navigator); no reload needed. Each root entry is labelled via `rdfs:label` resolved per spec §2.4.

## Architecture

```
src/
  config.ts             — env vars, page sizes
  sparql/
    client.ts           — fetch wrapper, SPARQL JSON parser, IRI helpers
    discovery.ts        — D1 (subclasses), D2 (properties), D3a/b (vocab), D5 (label-properties), filter classification
    results.ts          — dynamic result query builder + per-card discovery
  state/filterState.ts  — URL-synced state (root, page, filters)
  components/
    Header.tsx          — title + root navigator + endpoint
    FilterPanel.tsx     — renders discovered filters
    filters/{Enumerated,Range,Boolean,Text}Filter.tsx
    ResultsPanel.tsx    — count, list, pagination
    ResultCard.tsx      — title + object/datatype field grid
  App.tsx               — top-level wiring
  main.tsx, styles.css
```

## Spec-criterion compliance notes

- **No domain-specific IRI string match in code.** `grep -r "cw:\|film:\|imdb:\|culturalworks/" src/` returns only the fallback default in `config.ts:12` (the configurable root class constant — explicitly permitted by criterion 8) and SPARQL templates in `sparql/discovery.ts` and `sparql/results.ts` (also permitted).
- **Discovery, not hardcoding.** Filters, label-properties and card fields are all derived at runtime from D1–D5 queries against the loaded ontology.
- **Reasoning off.** All transitive closures (`rdfs:subClassOf*`, `rdfs:subPropertyOf*`, `owl:unionOf` list walks) are explicit in the SPARQL.
- **Year FILTERs use `xsd:gYear` literal comparison.** Verified safe for the IMDB dataset because the RML mappings emit explicitly typed `xsd:gYear` literals (mappings/01_talent.rml.ttl).

## Deviations / known limitations

- Card field labels use the property's discovered filter label when available, else the property's local name. Properties asserted on a result that are *not* in the discovered filter set do not get their `rdfs:label` looked up at card-render time (would require an extra round-trip per unknown property; deferred). All such labels still avoid raw IRIs.
- No reasoning-based inference: the app does not assume `rdfs:subPropertyOf rdfs:label` materialises label triples. It walks the chain explicitly via D5 and emits one `OPTIONAL` per discovered label-property.
- Pagination capped at 1000 (page 20). Beyond that the user is expected to refine filters.
