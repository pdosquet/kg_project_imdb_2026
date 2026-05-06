# Faceted search mechanism

This document describes the faceted-search layer added on top of the ontology-driven faceted browser specified in [../web_requirements.md](../web_requirements.md).

The original spec describes a *faceted browser*: filters discovered from the schema, applied to a result list. This document covers what was added to turn it into a *faceted search*: a free-text search bar, per-value facet counts, reactive recomputation, and count-driven ordering.

The point of these notes is to explain **why** each piece works the way it does. The "what" is in the code; the "why" rots if you only read diffs.

---

## 1. The two new dimensions

A faceted search adds two interaction shapes that pure faceted browsing does not have:

1. **A free-text query** orthogonal to the structured facets. Type "Nolan" and the list narrows to anything whose label contains "Nolan", regardless of which checkboxes are ticked. The query is held in app state and serialised as `?q=…` in the URL.

2. **Per-value counts on every facet, kept consistent with the active filter set.** When the user has *Genre = Drama* and *Year ≥ 2000* active, the Type facet shows how many works of each type satisfy *those two filters*. This is the property that distinguishes faceted search from a conventional list of dropdowns: facets become a live preview of "what would I get if I clicked this".

Everything else — discovery, the result query, label resolution, URL state, the root navigator — is unchanged. The faceted-search layer is strictly additive.

---

## 2. State and URL

### 2.1 State extension

`AppState` (in [src/state/filterState.ts](src/state/filterState.ts)) gains a single new field:

```ts
interface AppState {
  root: string;
  page: number;
  q: string;                                // <-- new
  filters: Record<string, FilterValue>;
}
```

A new setter `setQ(q: string)` resets pagination to page 1 (changing the search term invalidates the previous page index) and writes `?q=…` to the URL via the existing `replaceState` plumbing. `setRoot` and `resetFilters` clear `q` along with everything else they were already clearing.

### 2.2 Why `q` is part of state, not a component-local input

Two reasons:

- **Bookmark / share.** `?q=nolan` should produce the same view on reload as it does after typing. Putting `q` next to `filters` keeps the URL the single source of truth for "what is the user looking at".
- **It interacts with facet counts.** Counts must be computed against the same filter set the user can see (and that includes the active text query). Having `q` flow through the same effect that drives counts and results keeps the three views consistent.

The text input itself ([src/components/SearchBar.tsx](src/components/SearchBar.tsx)) holds a local copy of the value and pushes it into `q` after a 250 ms debounce, so each keystroke does not fire a new SPARQL round-trip.

---

## 3. Free-text search clause

### 3.1 Where it plugs in

The result query ([src/sparql/results.ts](src/sparql/results.ts)) is built by `buildWhere(...)`, which was refactored to accept an options bag:

```ts
buildWhere(rootIri, filters, active, labelProps, {
  q?: string;
  exceptProp?: string;
  includeLabels?: boolean;
});
```

When `q` is non-empty, `buildWhere` appends one extra block to the WHERE clause:

```sparql
{ ?work <LABEL_PROP_1> ?lq . }
UNION
{ ?work <LABEL_PROP_2> ?lq . }
UNION
{ ?work <rdfs:label> ?lq . }
FILTER(CONTAINS(LCASE(STR(?lq)), LCASE("<query>")))
```

The label-property list is the same one D5 returned (see web_requirements.md §2.2 D5). For the `cw:CreativeWork` root that means matching against `cw:primaryTitle` and `rdfs:label`; for `cw:RealPerson` it means matching against `cw:name` and `rdfs:label`. The search box never says "search by what?" — the ontology already told us.

### 3.2 Why a UNION rather than `?work ?p ?lq` with a property filter

A SPARQL pattern like `?work ?p ?lq . FILTER(?p IN (...))` works in principle, but ARQ optimises the explicit UNION-of-property-paths variant much better — it can use the property index per branch instead of scanning all triples for `?work`. The dataset is small so it does not matter today; the pattern is chosen so the same code scales when it grows.

### 3.3 Why `CONTAINS(LCASE(STR(?lq)), LCASE("..."))` and not regex

`STR(?lq)` strips language tags, `LCASE` makes the match case-insensitive, and `CONTAINS` is faster than `regex(...)` and good enough for substring search. The query string is escaped for embedded backslashes and double quotes; that is sufficient because the SPARQL parser does not interpret anything else inside a string literal.

### 3.4 Why the search-bar is part of `buildWhere`, not a separate top-level filter

It would be tempting to model `q` as just another `FilterValue` keyed by some synthetic property IRI. Tempting, but wrong:

- `q` is **root-dependent** — its WHERE clause is built from the D5 label-properties for the current root. A normal `FilterValue` lives in `state.filters` keyed by a property IRI; we would have to invent a special-case key.
- `q` is **reset on root switch** — adding it to `state.filters` would mean teaching every `setRoot` / `resetFilters` path about it as a special key.
- `q` does not appear in the discovered filter UI — there is no `FilterDef` for it.

Keeping `q` as a peer field of `filters` (rather than a member of it) avoids three "if (key === SEARCH_KEY) ..." special cases.

---

## 4. Facet counts

This is the heart of the change. It lives in [src/sparql/facetCounts.ts](src/sparql/facetCounts.ts).

### 4.1 The problem

For each enumerated facet, we want to render counts like:

> Drama 1,247
> Thriller 812
> Documentary 0
> ...

The naïve approach — "count the rows in the current result set, broken down by the facet's property" — is wrong. To see why, imagine the user has just selected `Genre = Drama`. If we apply that filter and group by genre, we get exactly one bucket: Drama. Every other genre shows zero. The user can no longer see whether selecting Thriller would also yield results, because we baked Drama into the WHERE clause.

The fix is the **standard faceted-search rule**:

> When computing counts for facet *F*, apply every other active filter, **but not F's own**.

This is sometimes called the "self-exclusion" rule. The selected facet's siblings keep their meaningful counts; only that facet sees the unfiltered (with respect to itself) distribution.

### 4.2 How `buildWhere` supports it

`buildWhere` takes an `exceptProp?: string` option. When set, the loop that emits filter blocks skips the filter whose property matches `exceptProp`. So the count query for facet *F* is:

```sparql
SELECT ?v (COUNT(DISTINCT ?work) AS ?n) WHERE {
  ?work a/rdfs:subClassOf* <ROOT> .
  -- every active filter EXCEPT F.property
  -- the global text-search clause (if any)
  ?work <F.property> ?v .
}
GROUP BY ?v
```

The same `buildWhere` that drives the result query drives the count queries. There is exactly one place in the codebase that knows how to translate the active filter state into SPARQL.

### 4.3 Why we drop label OPTIONALs from the count query

The result query emits one `OPTIONAL { ?work <LABEL_PROP> ?l<i> }` per discovered label-property to support `COALESCE(?l1, ?l2, ...)` for sorting. Count queries do not project a label, so emitting these OPTIONALs is dead weight. `buildWhere` accepts `includeLabels: false` to suppress them.

### 4.4 Fan-out

`fetchFacetCounts(...)` issues one SPARQL query per enumerated facet (we never count anything for year-range, integer-range, boolean, or text filters — those have no enumerated value space to count over) and resolves them in parallel:

```ts
await Promise.all(enumFilters.map(async (f) => {
  // build query with exceptProp = f.property.iri
  // run, parse, store in counts.get(f.property.iri)
}));
```

For *N* enumerated facets and any active filter set, that is *N* count queries plus 2 result queries (the page + the total) per state change — see §6 below for the cost discussion.

### 4.5 Why we tolerate per-facet failures

If one count query fails for any reason, the catch block stores an empty map for that facet and the others still render. A single SPARQL parse error in one count branch cannot blank out the whole filter panel. This is consistent with the spec's "no retry, no fallback magic" stance — the failure is silent at the facet level but the rest of the UI keeps working.

---

## 5. Rendering: counts, sort, and dimming

[src/components/filters/EnumeratedFilter.tsx](src/components/filters/EnumeratedFilter.tsx) was updated to:

1. Accept an optional `counts: Map<string, number>` prop.
2. Sort values by count descending, with alphabetical tie-break, when counts are known. When counts have not arrived yet, fall back to the original alphabetical order so the UI is stable on first render and during loading.
3. Show the count next to each value as a `<span class="filter-value-count">` chip.
4. Apply a `.dim` class to a row whose count is zero **and which is not currently selected**. The "not selected" qualifier matters: a zero-count facet value that the user has clicked must stay highlighted, not dimmed, otherwise the UI lies about what is currently active.

### 5.1 Why we sort by count rather than alphabetically

For a long facet (many genres, many roles), the user almost always wants to see the populous values first — they are the ones likely to be useful filters. Alphabetical order buries the long tail of the distribution at the top (most ontologies' alphabet starts with rarely-occurring terms like "Adventure" or "Action").

Tie-break alphabetically because count-only ordering is unstable: two genres with the same count would re-shuffle on every state change.

### 5.2 Why we keep zero-count values visible

This was an explicit choice:

- The web spec §4.5 mandates that values declared in the ontology must be reachable through the filter UI even when they have zero data occurrences. That constraint applies to baseline ontology coverage, not to dynamic facet narrowing — but the UX justification carries over: a *visible-but-dimmed* zero is more informative than a *hidden* one because it tells the user *why* their pivot is empty, instead of leaving them wondering whether the facet ever supported that value.
- The cost is one greyed `<label>` per dead value. Cheap.

### 5.3 Why dimming is a pure CSS class

Dimming is purely visual. The checkbox is still clickable — clicking a zero-count value applies the filter and the user sees an empty result list, which is the correct outcome. We do not disable the input because that would couple presentation to interactivity in a way that the spec's "no silent hides" rule already rejects.

---

## 6. Cost

Per state change (root, q, or filter), the app issues:

| Query | Count |
|---|---|
| Result page (D-result) | 1 |
| Result count (`COUNT(DISTINCT ?work)`) | 1 |
| Per-card data (D6) | up to 50 (one per visible card) |
| Per-facet count | one per *enumerated* facet |

Page changes do **not** trigger facet recomputation — only D-result and D6 fire — because pagination is orthogonal to the filter set. This is enforced by the dependency arrays of the two effects in [src/App.tsx](src/App.tsx): the facet-count effect depends on `state.q`, `state.filters`, `state.root`, but not on `state.page`.

For the IMDB demo dataset (a few thousand persons, a few thousand works) the round-trip cost is invisible. The Vite proxy, the Cloudflare Tunnel hop, and Fuseki's in-memory store are each well under 50 ms. The total wall-clock latency on a state change is dominated by the slowest count query, not by their count.

If it ever does become a problem, the lever is to fold all facet counts into a single SPARQL query via SPARQL `UNION` blocks plus a `?facet` selector variable, or to push a longer debounce on `setFilter`. We have not done that because the present cost is not measurable.

---

## 7. What is *not* part of this change

To keep the boundaries clean:

- **No facet ordering between facets.** The order in which facets appear in the panel is still the alphabetical-by-property-label order returned by `buildFilters`. Faceted search systems sometimes reorder *facets themselves* by usefulness; we do not.
- **No range-filter histograms.** Year and integer ranges still have only `from`/`to` inputs. A faceted-search refinement would render a histogram over the year distribution and let the user drag-to-select. Out of scope.
- **No "remove this filter" chips above the result list.** The user removes filters by interacting with the same control that set them. Cheap to add later but not mandatory.
- **No multi-token query.** `q="kubrick stanley"` is treated as one substring, not two terms ANDed across the label. Multi-token search would need either client-side splitting + `&&` of CONTAINS clauses, or full-text indexing on Fuseki (`text:query`).
- **No spelling correction, stemming, or relevance ranking.** The result list is sorted by label, not by match quality.

These are deliberate omissions. Any of them is half a day of work on top of the current scaffolding; none of them changes the underlying mechanism described above.

---

## 8. Files touched

| File | Change |
|---|---|
| [src/state/filterState.ts](src/state/filterState.ts) | Added `q: string` to `AppState`; `Q_KEY` URL param; `setQ` setter; `q` cleared by `setRoot` / `resetFilters`. |
| [src/sparql/results.ts](src/sparql/results.ts) | `buildWhere` exported with options `{ q, exceptProp, includeLabels }`. `runResultQuery` now takes a `q` argument and forwards it. |
| [src/sparql/facetCounts.ts](src/sparql/facetCounts.ts) | **New.** `fetchFacetCounts` runs one count query per enumerated facet using `exceptProp` self-exclusion. |
| [src/components/SearchBar.tsx](src/components/SearchBar.tsx) | **New.** Debounced text input. |
| [src/components/filters/EnumeratedFilter.tsx](src/components/filters/EnumeratedFilter.tsx) | Accepts `counts` prop; sorts by count desc with alphabetical tie-break; renders count chip; dims zero-count rows that are not selected. |
| [src/components/FilterPanel.tsx](src/components/FilterPanel.tsx) | Forwards `facetCounts` map to enumerated filters. |
| [src/App.tsx](src/App.tsx) | Wires `setQ` and `<SearchBar>`; second `useEffect` fetches facet counts on root/filter/q change (not page); passes counts down. |
| [src/styles.css](src/styles.css) | `.search-row`, `.search-bar`, `.filter-value.dim`, `.filter-value-count`. |

No changes to the discovery module, the SPARQL client, the result card, the header, or the root navigator. The faceted-search layer is bolted on, not bolted in.
