import type { FilterDef } from "../../sparql/discovery";

interface Props {
  filter: FilterDef;
  value: string;
  onChange: (v: string) => void;
}

export function TextFilter({ filter, value, onChange }: Props) {
  return (
    <div className="filter">
      <div className="filter-heading">{filter.property.label}</div>
      <input
        type="text"
        className="filter-text"
        placeholder="contains…"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
