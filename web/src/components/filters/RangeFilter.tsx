import type { FilterDef } from "../../sparql/discovery";

interface Props {
  filter: FilterDef;
  from?: number;
  to?: number;
  onChange: (from?: number, to?: number) => void;
  isYear: boolean;
}

export function RangeFilter({ filter, from, to, onChange, isYear }: Props) {
  const bounds = filter.yearBounds;
  const placeholderFrom = bounds?.lo !== undefined ? String(bounds.lo) : "from";
  const placeholderTo = bounds?.hi !== undefined ? String(bounds.hi) : "to";
  const parse = (s: string): number | undefined => {
    if (s.trim() === "") return undefined;
    const n = Number(s);
    return Number.isFinite(n) ? n : undefined;
  };
  return (
    <div className="filter">
      <div className="filter-heading">
        {filter.property.label} {isYear ? "" : "(range)"}
      </div>
      <div className="filter-range">
        <input
          type="number"
          placeholder={placeholderFrom}
          value={from ?? ""}
          onChange={(e) => onChange(parse(e.target.value), to)}
        />
        <span>—</span>
        <input
          type="number"
          placeholder={placeholderTo}
          value={to ?? ""}
          onChange={(e) => onChange(from, parse(e.target.value))}
        />
      </div>
    </div>
  );
}
