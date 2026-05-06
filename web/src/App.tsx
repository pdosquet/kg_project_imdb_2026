import { useEffect, useMemo, useState } from "react";
import { ROOTS } from "./config";
import { useAppState } from "./state/filterState";
import {
  buildFilters,
  discoverLabelProperties,
  discoverProperties,
  fetchClassLabel,
  type FilterDef,
} from "./sparql/discovery";
import { runResultQuery, type ResultRow } from "./sparql/results";
import { fetchFacetCounts, type FacetCounts } from "./sparql/facetCounts";
import { Header } from "./components/Header";
import { SearchBar } from "./components/SearchBar";
import { FilterPanel } from "./components/FilterPanel";
import { ResultsPanel } from "./components/ResultsPanel";

interface RootOption {
  iri: string;
  label: string;
}

export function App() {
  const { state, setRoot, setPage, setFilter, setQ, resetFilters } = useAppState(ROOTS[0]);
  const [rootOptions, setRootOptions] = useState<RootOption[]>([]);
  const [filters, setFilters] = useState<FilterDef[]>([]);
  const [labelProps, setLabelProps] = useState<string[]>([]);
  const [discoveryLoading, setDiscoveryLoading] = useState(true);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);

  const [rows, setRows] = useState<ResultRow[]>([]);
  const [total, setTotal] = useState(0);
  const [capped, setCapped] = useState(false);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [resultsError, setResultsError] = useState<string | null>(null);
  const [facetCounts, setFacetCounts] = useState<FacetCounts | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all(
      ROOTS.map(async (iri) => ({ iri, label: await fetchClassLabel(iri) })),
    )
      .then((opts) => {
        if (!cancelled) setRootOptions(opts);
      })
      .catch(() => {
        if (!cancelled) setRootOptions(ROOTS.map((iri) => ({ iri, label: iri })));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setDiscoveryLoading(true);
    setDiscoveryError(null);
    setFacetCounts(null);
    (async () => {
      try {
        const [props, lps] = await Promise.all([
          discoverProperties(state.root),
          discoverLabelProperties(state.root),
        ]);
        const fs = await buildFilters(state.root, props);
        if (cancelled) return;
        setFilters(fs);
        setLabelProps(lps);
      } catch (e) {
        if (!cancelled) setDiscoveryError((e as Error).message);
      } finally {
        if (!cancelled) setDiscoveryLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [state.root]);

  const filterFingerprint = useMemo(() => JSON.stringify(state.filters), [state.filters]);

  // Result query — re-runs on root/page/filter/q change.
  useEffect(() => {
    if (discoveryLoading) return;
    let cancelled = false;
    setResultsLoading(true);
    setResultsError(null);
    runResultQuery(state.root, filters, state.filters, labelProps, state.page, state.q)
      .then((res) => {
        if (cancelled) return;
        setRows(res.rows);
        setTotal(res.total);
        setCapped(res.capped);
      })
      .catch((e: Error) => {
        if (!cancelled) setResultsError(e.message);
      })
      .finally(() => {
        if (!cancelled) setResultsLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.root, state.page, state.q, filterFingerprint, discoveryLoading, filters, labelProps]);

  // Facet counts — re-runs on filter/q change (page change does NOT recompute facets).
  useEffect(() => {
    if (discoveryLoading) return;
    let cancelled = false;
    setFacetCounts(null);
    fetchFacetCounts(state.root, filters, state.filters, labelProps, state.q)
      .then((c) => {
        if (!cancelled) setFacetCounts(c);
      })
      .catch(() => {
        if (!cancelled) setFacetCounts(new Map());
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.root, state.q, filterFingerprint, discoveryLoading, filters, labelProps]);

  return (
    <div className="app">
      <Header
        roots={rootOptions.length ? rootOptions : ROOTS.map((iri) => ({ iri, label: iri }))}
        activeRoot={state.root}
        onChangeRoot={setRoot}
      />
      <div className="search-row">
        <SearchBar value={state.q} onChange={setQ} />
      </div>
      {discoveryError && <div className="error">Discovery error: {discoveryError}</div>}
      <div className="body">
        <FilterPanel
          filters={filters}
          active={state.filters}
          facetCounts={facetCounts}
          loading={discoveryLoading}
          onChange={setFilter}
          onReset={resetFilters}
        />
        <ResultsPanel
          rows={rows}
          total={total}
          capped={capped}
          page={state.page}
          onPage={setPage}
          loading={resultsLoading}
          error={resultsError}
          filters={filters}
          labelProps={labelProps}
        />
      </div>
    </div>
  );
}
