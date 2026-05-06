import { useEffect, useState } from "react";
import type { ResultRow, ResultCardData } from "../sparql/results";
import { fetchCardData } from "../sparql/results";
import type { FilterDef } from "../sparql/discovery";

interface Props {
  row: ResultRow;
  filters: FilterDef[];
  labelProps: string[];
}

export function ResultCard({ row, filters, labelProps }: Props) {
  const [data, setData] = useState<ResultCardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    fetchCardData(row.iri, filters, labelProps)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [row.iri, filters, labelProps]);

  return (
    <div className="card">
      <div className="card-title">{data?.label ?? row.label}</div>
      {error && <div className="card-error">Error: {error}</div>}
      {!data && !error && <div className="card-loading">…</div>}
      {data && (
        <dl className="card-fields">
          {data.fields.map((f) => (
            <div className="card-field" key={f.property}>
              <dt>{f.property}</dt>
              <dd>{f.values.join(", ")}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
