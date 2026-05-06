import { useMemo, useState } from "react";
import type { FilterDef, EnumValue } from "../../sparql/discovery";
import { ENUM_COMBOBOX_THRESHOLD } from "../../config";

interface Props {
  filter: FilterDef;
  selected: string[];
  counts?: Map<string, number>; // facet counts; undefined while loading
  onChange: (iris: string[]) => void;
}

export function EnumeratedFilter({ filter, selected, counts, onChange }: Props) {
  const [search, setSearch] = useState("");
  const values = filter.values ?? [];
  const useCombobox = values.length > ENUM_COMBOBOX_THRESHOLD;

  // Sort by count desc (selected and counts known), with ties broken alphabetically.
  // Values with unknown counts (counts === undefined) keep alphabetical order.
  const ordered = useMemo<EnumValue[]>(() => {
    const list = [...values];
    if (counts) {
      list.sort((a, b) => {
        const ca = counts.get(a.iri) ?? 0;
        const cb = counts.get(b.iri) ?? 0;
        if (cb !== ca) return cb - ca;
        return a.label.localeCompare(b.label);
      });
    } else {
      list.sort((a, b) => a.label.localeCompare(b.label));
    }
    return list;
  }, [values, counts]);

  const filtered = useMemo<EnumValue[]>(() => {
    if (!useCombobox || !search.trim()) return ordered;
    const q = search.trim().toLowerCase();
    return ordered.filter((v) => v.label.toLowerCase().includes(q));
  }, [ordered, search, useCombobox]);

  const toggle = (iri: string) => {
    if (selected.includes(iri)) onChange(selected.filter((s) => s !== iri));
    else onChange([...selected, iri]);
  };

  return (
    <div className="filter">
      <div className="filter-heading">{filter.property.label}</div>
      {useCombobox && (
        <input
          className="filter-search"
          type="text"
          placeholder="Search…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      )}
      <div className="filter-values">
        {filtered.map((v) => {
          const n = counts?.get(v.iri) ?? 0;
          const dim = counts !== undefined && n === 0 && !selected.includes(v.iri);
          return (
            <label
              key={v.iri}
              className={`filter-value ${dim ? "dim" : ""}`}
            >
              <input
                type="checkbox"
                checked={selected.includes(v.iri)}
                onChange={() => toggle(v.iri)}
              />
              <span className="filter-value-label">{v.label}</span>
              {counts !== undefined && (
                <span className="filter-value-count">{n}</span>
              )}
            </label>
          );
        })}
        {filtered.length === 0 && <div className="filter-empty">no values</div>}
      </div>
    </div>
  );
}
