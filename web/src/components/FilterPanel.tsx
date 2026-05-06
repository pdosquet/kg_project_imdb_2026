import type { FilterDef } from "../sparql/discovery";
import type { FilterValue } from "../state/filterState";
import type { FacetCounts } from "../sparql/facetCounts";
import { EnumeratedFilter } from "./filters/EnumeratedFilter";
import { RangeFilter } from "./filters/RangeFilter";
import { BooleanFilter } from "./filters/BooleanFilter";
import { TextFilter } from "./filters/TextFilter";

interface Props {
  filters: FilterDef[];
  active: Record<string, FilterValue>;
  facetCounts: FacetCounts | null;
  loading: boolean;
  onChange: (propIri: string, fv: FilterValue | undefined) => void;
  onReset: () => void;
}

export function FilterPanel({ filters, active, facetCounts, loading, onChange, onReset }: Props) {
  if (loading) return <aside className="filter-panel">Loading filters…</aside>;
  return (
    <aside className="filter-panel">
      <button className="reset-btn" onClick={onReset}>
        Reset filters
      </button>
      {filters.length === 0 && <div className="empty">No filters discovered for this root.</div>}
      {filters.map((f) => {
        const av = active[f.property.iri];
        switch (f.kind) {
          case "enum":
            return (
              <EnumeratedFilter
                key={f.property.iri}
                filter={f}
                selected={av?.kind === "enum" ? av.iris : []}
                counts={facetCounts?.get(f.property.iri)}
                onChange={(iris) =>
                  onChange(f.property.iri, iris.length ? { kind: "enum", iris } : undefined)
                }
              />
            );
          case "year":
            return (
              <RangeFilter
                key={f.property.iri}
                filter={f}
                from={av?.kind === "year" ? av.from : undefined}
                to={av?.kind === "year" ? av.to : undefined}
                isYear
                onChange={(from, to) => {
                  if (from === undefined && to === undefined) onChange(f.property.iri, undefined);
                  else onChange(f.property.iri, { kind: "year", from, to });
                }}
              />
            );
          case "integer":
            return (
              <RangeFilter
                key={f.property.iri}
                filter={f}
                from={av?.kind === "integer" ? av.from : av?.kind === "year" ? av.from : undefined}
                to={av?.kind === "integer" ? av.to : av?.kind === "year" ? av.to : undefined}
                isYear={false}
                onChange={(from, to) => {
                  if (from === undefined && to === undefined) onChange(f.property.iri, undefined);
                  else onChange(f.property.iri, { kind: "integer", from, to });
                }}
              />
            );
          case "boolean":
            return (
              <BooleanFilter
                key={f.property.iri}
                filter={f}
                value={av?.kind === "boolean" ? av.value : null}
                onChange={(v) =>
                  onChange(f.property.iri, v === null ? undefined : { kind: "boolean", value: v })
                }
              />
            );
          case "text":
            return (
              <TextFilter
                key={f.property.iri}
                filter={f}
                value={av?.kind === "text" ? av.value : ""}
                onChange={(v) =>
                  onChange(f.property.iri, v.trim() ? { kind: "text", value: v } : undefined)
                }
              />
            );
        }
      })}
    </aside>
  );
}
