import type { FilterDef } from "../../sparql/discovery";

interface Props {
  filter: FilterDef;
  value: boolean | null;
  onChange: (v: boolean | null) => void;
}

export function BooleanFilter({ filter, value, onChange }: Props) {
  return (
    <div className="filter">
      <div className="filter-heading">{filter.property.label}</div>
      <div className="filter-bool">
        <label>
          <input
            type="radio"
            checked={value === null}
            onChange={() => onChange(null)}
          />{" "}
          any
        </label>
        <label>
          <input
            type="radio"
            checked={value === true}
            onChange={() => onChange(true)}
          />{" "}
          yes
        </label>
        <label>
          <input
            type="radio"
            checked={value === false}
            onChange={() => onChange(false)}
          />{" "}
          no
        </label>
      </div>
    </div>
  );
}
