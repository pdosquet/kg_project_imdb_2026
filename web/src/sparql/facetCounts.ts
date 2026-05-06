import { select, asIri, asLiteral } from "./client";
import { buildWhere } from "./results";
import type { FilterDef } from "./discovery";
import type { FilterValue } from "../state/filterState";

export type FacetCounts = Map<string, Map<string, number>>;

export async function fetchFacetCounts(
  rootIri: string,
  filters: FilterDef[],
  active: Record<string, FilterValue>,
  labelProps: string[],
  q: string,
): Promise<FacetCounts> {
  const enumFilters = filters.filter((f) => f.kind === "enum");
  const counts: FacetCounts = new Map();

  await Promise.all(
    enumFilters.map(async (f) => {
      const { where } = buildWhere(rootIri, filters, active, labelProps, {
        q,
        exceptProp: f.property.iri,
        includeLabels: false,
      });
      const query = `
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
SELECT ?v (COUNT(DISTINCT ?work) AS ?n) WHERE {
  ${where}
  ?work <${f.property.iri}> ?v .
}
GROUP BY ?v`;
      try {
        const r = await select(query);
        const m = new Map<string, number>();
        for (const b of r.results.bindings) {
          const iri = asIri(b.v);
          const n = Number(asLiteral(b.n) ?? "0");
          if (iri) m.set(iri, n);
        }
        counts.set(f.property.iri, m);
      } catch {
        counts.set(f.property.iri, new Map());
      }
    }),
  );

  return counts;
}
