import { useEffect, useState, useCallback } from "react";
import { localName } from "../sparql/client";

export type FilterValue =
  | { kind: "enum"; iris: string[] } // selected IRIs (OR within filter)
  | { kind: "year"; from?: number; to?: number }
  | { kind: "integer"; from?: number; to?: number }
  | { kind: "boolean"; value: boolean | null }
  | { kind: "text"; value: string };

export interface AppState {
  root: string;
  page: number;
  q: string; // global free-text search
  filters: Record<string, FilterValue>; // keyed by property IRI
}

const ROOT_KEY = "root";
const PAGE_KEY = "page";
const Q_KEY = "q";

function parse(search: string, defaultRoot: string): AppState {
  const params = new URLSearchParams(search);
  const root = params.get(ROOT_KEY) ?? defaultRoot;
  const page = Math.max(1, Number(params.get(PAGE_KEY) ?? 1) || 1);
  const q = params.get(Q_KEY) ?? "";
  const filters: Record<string, FilterValue> = {};
  for (const [k, v] of params) {
    if (k === ROOT_KEY || k === PAGE_KEY || k === Q_KEY) continue;
    if (!v) continue;
    // suffix-based key encoding for ranges and bool
    if (k.endsWith("_from") || k.endsWith("_to")) {
      const propKey = k.slice(0, -("_from".length));
      const which = k.endsWith("_from") ? "from" : "to";
      const propIri = decodeURIComponent(propKey);
      const num = Number(v);
      if (!Number.isFinite(num)) continue;
      const existing = filters[propIri] ?? ({ kind: "year", from: undefined, to: undefined } as FilterValue);
      // we don't yet know whether year or integer; resolve at apply-time. Use 'year' tag as a placeholder
      // but the apply-time code maps both via the discovery info.
      if (existing.kind !== "year" && existing.kind !== "integer") {
        filters[propIri] = { kind: "year", from: which === "from" ? num : undefined, to: which === "to" ? num : undefined };
      } else {
        filters[propIri] = { ...existing, [which]: num } as FilterValue;
      }
      continue;
    }
    if (k.endsWith("_bool")) {
      const propIri = decodeURIComponent(k.slice(0, -"_bool".length));
      filters[propIri] = { kind: "boolean", value: v === "true" ? true : v === "false" ? false : null };
      continue;
    }
    if (k.endsWith("_text")) {
      const propIri = decodeURIComponent(k.slice(0, -"_text".length));
      filters[propIri] = { kind: "text", value: v };
      continue;
    }
    // default: enumerated values, comma-separated, percent-encoded
    const propIri = decodeURIComponent(k);
    const iris = v.split(",").map((s) => decodeURIComponent(s)).filter(Boolean);
    filters[propIri] = { kind: "enum", iris };
  }
  return { root, page, q, filters };
}

function serialize(state: AppState): string {
  const params = new URLSearchParams();
  params.set(ROOT_KEY, state.root);
  if (state.page > 1) params.set(PAGE_KEY, String(state.page));
  if (state.q.trim()) params.set(Q_KEY, state.q);
  for (const [propIri, fv] of Object.entries(state.filters)) {
    const k = encodeURIComponent(propIri);
    switch (fv.kind) {
      case "enum":
        if (fv.iris.length) params.set(k, fv.iris.map(encodeURIComponent).join(","));
        break;
      case "year":
      case "integer":
        if (fv.from !== undefined) params.set(`${k}_from`, String(fv.from));
        if (fv.to !== undefined) params.set(`${k}_to`, String(fv.to));
        break;
      case "boolean":
        if (fv.value !== null) params.set(`${k}_bool`, String(fv.value));
        break;
      case "text":
        if (fv.value.trim()) params.set(`${k}_text`, fv.value);
        break;
    }
  }
  return params.toString();
}

export function useAppState(defaultRoot: string) {
  const [state, setState] = useState<AppState>(() => parse(window.location.search, defaultRoot));

  useEffect(() => {
    const onPop = () => setState(parse(window.location.search, defaultRoot));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [defaultRoot]);

  const update = useCallback((next: AppState) => {
    setState(next);
    const qs = serialize(next);
    const url = `${window.location.pathname}?${qs}`;
    window.history.replaceState(null, "", url);
  }, []);

  const setRoot = useCallback(
    (root: string) => update({ root, page: 1, q: "", filters: {} }),
    [update],
  );
  const setPage = useCallback(
    (page: number) => update({ ...state, page }),
    [update, state],
  );
  const setFilter = useCallback(
    (propIri: string, fv: FilterValue | undefined) => {
      const filters = { ...state.filters };
      if (fv === undefined) delete filters[propIri];
      else filters[propIri] = fv;
      update({ ...state, page: 1, filters });
    },
    [update, state],
  );
  const setQ = useCallback(
    (q: string) => update({ ...state, page: 1, q }),
    [update, state],
  );
  const resetFilters = useCallback(
    () => update({ ...state, page: 1, q: "", filters: {} }),
    [update, state],
  );

  return { state, setRoot, setPage, setFilter, setQ, resetFilters };
}

export function describeFilterKey(propIri: string): string {
  return localName(propIri);
}
