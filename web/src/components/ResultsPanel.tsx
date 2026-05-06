import type { ResultRow } from "../sparql/results";
import type { FilterDef } from "../sparql/discovery";
import { ResultCard } from "./ResultCard";
import { PAGE_SIZE, RESULT_CAP, MAX_PAGE } from "../config";

interface Props {
  rows: ResultRow[];
  total: number;
  capped: boolean;
  page: number;
  onPage: (p: number) => void;
  loading: boolean;
  error: string | null;
  filters: FilterDef[];
  labelProps: string[];
}

export function ResultsPanel({
  rows, total, capped, page, onPage, loading, error, filters, labelProps,
}: Props) {
  if (loading) return <main className="results-panel">Loading results…</main>;
  if (error) return <main className="results-panel"><div className="error">SPARQL error: {error}</div></main>;
  const start = (page - 1) * PAGE_SIZE + 1;
  const end = Math.min(page * PAGE_SIZE, capped ? RESULT_CAP : total);
  const totalLabel = capped ? `${RESULT_CAP}+` : String(total);
  const lastPage = Math.min(MAX_PAGE, Math.max(1, Math.ceil((capped ? RESULT_CAP : total) / PAGE_SIZE)));
  return (
    <main className="results-panel">
      <div className="results-header">
        {total === 0 ? "No results" : `Showing ${start}–${end} of ${totalLabel}`}
      </div>
      <div className="results-list">
        {rows.map((r) => (
          <ResultCard key={r.iri} row={r} filters={filters} labelProps={labelProps} />
        ))}
      </div>
      {total > PAGE_SIZE && (
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => onPage(page - 1)}>
            Previous
          </button>
          <span>Page {page} / {lastPage}</span>
          <button disabled={page >= lastPage} onClick={() => onPage(page + 1)}>
            Next
          </button>
        </div>
      )}
    </main>
  );
}
