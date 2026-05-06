import { select, asIri, asLiteral, localName } from "./client";
import type { FilterDef } from "./discovery";
import type { FilterValue } from "../state/filterState";
import { PAGE_SIZE, RESULT_CAP } from "../config";

export interface ResultRow {
  iri: string;
  label: string;
}

export interface CardField {
  property: string; // property label
  values: string[]; // value labels
}

export interface ResultCardData extends ResultRow {
  fields: CardField[];
}

const lang = `(LANG(?label) = "en" || LANG(?label) = "")`;

function filterBlock(
  filter: FilterDef,
  active: FilterValue,
  varIndex: number,
): { block: string; ok: boolean } {
  const propIri = filter.property.iri;
  const v = `?v_${varIndex}`;
  switch (filter.kind) {
    case "enum": {
      if (active.kind !== "enum" || active.iris.length === 0) return { block: "", ok: false };
      const list = active.iris.map((iri) => `<${iri}>`).join(", ");
      return { block: `?work <${propIri}> ${v} . FILTER(${v} IN (${list}))`, ok: true };
    }
    case "year": {
      if (active.kind !== "year") return { block: "", ok: false };
      if (active.from === undefined && active.to === undefined) return { block: "", ok: false };
      const lines: string[] = [`?work <${propIri}> ${v} .`];
      if (active.from !== undefined)
        lines.push(`FILTER(${v} >= "${active.from}"^^xsd:gYear)`);
      if (active.to !== undefined)
        lines.push(`FILTER(${v} <= "${active.to}"^^xsd:gYear)`);
      return { block: lines.join("\n  "), ok: true };
    }
    case "integer": {
      if (active.kind !== "integer" && active.kind !== "year") return { block: "", ok: false };
      const from = (active as { from?: number }).from;
      const to = (active as { to?: number }).to;
      if (from === undefined && to === undefined) return { block: "", ok: false };
      const lines: string[] = [`?work <${propIri}> ${v} .`];
      if (from !== undefined) lines.push(`FILTER(${v} >= ${from})`);
      if (to !== undefined) lines.push(`FILTER(${v} <= ${to})`);
      return { block: lines.join("\n  "), ok: true };
    }
    case "boolean": {
      if (active.kind !== "boolean" || active.value === null) return { block: "", ok: false };
      return {
        block: `?work <${propIri}> "${active.value}"^^xsd:boolean .`,
        ok: true,
      };
    }
    case "text": {
      if (active.kind !== "text" || !active.value.trim()) return { block: "", ok: false };
      const safe = active.value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
      return {
        block: `?work <${propIri}> ${v} . FILTER(CONTAINS(LCASE(STR(${v})), LCASE("${safe}")))`,
        ok: true,
      };
    }
  }
}

export interface BuildWhereOptions {
  q?: string; // global free-text search across label-properties
  exceptProp?: string; // skip the filter for this property IRI (used for facet counts)
  includeLabels?: boolean; // emit label-property OPTIONALs (default true)
}

export function buildWhere(
  rootIri: string,
  filters: FilterDef[],
  active: Record<string, FilterValue>,
  labelProps: string[],
  opts: BuildWhereOptions = {},
): { where: string; labelVars: string[] } {
  const includeLabels = opts.includeLabels !== false;
  const labelVars: string[] = [];
  // Closure is materialised at build time, so an
  // instance is already typed at every superclass. A direct rdf:type match
  // suffices — no subclass walk needed.
  const lines: string[] = [`?work a <${rootIri}> .`];
  if (includeLabels) {
    labelProps.forEach((lp, i) => {
      const v = `?l${i}`;
      labelVars.push(v);
      lines.push(`OPTIONAL { ?work <${lp}> ${v} . }`);
    });
  }
  let idx = 0;
  for (const f of filters) {
    if (opts.exceptProp && f.property.iri === opts.exceptProp) continue;
    const av = active[f.property.iri];
    if (!av) continue;
    const { block, ok } = filterBlock(f, av, idx++);
    if (ok) lines.push(block);
  }
  if (opts.q && opts.q.trim() && labelProps.length > 0) {
    const safe = opts.q.trim().replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    const unions = labelProps
      .map((lp) => `{ ?work <${lp}> ?lq . }`)
      .join(" UNION ");
    lines.push(unions);
    lines.push(`FILTER(CONTAINS(LCASE(STR(?lq)), LCASE("${safe}")))`);
  }
  return { where: lines.join("\n  "), labelVars };
}

export async function runResultQuery(
  rootIri: string,
  filters: FilterDef[],
  active: Record<string, FilterValue>,
  labelProps: string[],
  page: number,
  q = "",
): Promise<{ rows: ResultRow[]; total: number; capped: boolean }> {
  const { where, labelVars } = buildWhere(rootIri, filters, active, labelProps, { q });
  const coalesce = `COALESCE(${[...labelVars, "STR(?work)"].join(", ")}) AS ?label`;
  const offset = (page - 1) * PAGE_SIZE;
  const resultQuery = `
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
SELECT DISTINCT ?work (${coalesce}) WHERE {
  ${where}
}
ORDER BY ?label
LIMIT ${PAGE_SIZE} OFFSET ${offset}`;
  const cq = `
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
SELECT (COUNT(DISTINCT ?work) AS ?n) WHERE {
  ${where}
}`;
  const [r, c] = await Promise.all([select(resultQuery), select(cq)]);
  const rows: ResultRow[] = r.results.bindings
    .map((b) => {
      const iri = asIri(b.work);
      if (!iri) return null;
      const label = asLiteral(b.label) ?? localName(iri);
      // if COALESCE fell through to STR(?work), prettify by extracting localName
      const final = label.startsWith("http") ? localName(label) : label;
      return { iri, label: final };
    })
    .filter((x): x is ResultRow => x !== null);
  const total = Number(asLiteral(c.results.bindings[0]?.n) ?? "0");
  return { rows, total, capped: total > RESULT_CAP };
}

// Card-data discovery: for one IRI, return all asserted properties classified.
export async function fetchCardData(
  iri: string,
  filters: FilterDef[],
  labelProps: string[],
): Promise<ResultCardData> {
  // Fetch every (?p, ?o) and group; resolve labels for object-property values.
  const q = `
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
SELECT ?p ?o ?oLabel WHERE {
  <${iri}> ?p ?o .
  FILTER(!isIRI(?o) || (?o != owl:Thing && ?o != owl:NamedIndividual))
  OPTIONAL { ?o rdfs:label ?oLabel . FILTER(${lang}) }
}`;
  const r = await select(q);
  const propsByIri = new Map<string, FilterDef>();
  for (const f of filters) propsByIri.set(f.property.iri, f);
  // labelProps are expressed as IRIs; values for them feed the title, not the field grid.
  const labelPropSet = new Set(labelProps);
  // Resolve title via label-property priority order.
  let title: string | undefined;
  for (const lp of labelProps) {
    const hit = r.results.bindings.find((b) => asIri(b.p) === lp);
    if (hit) {
      const v = asLiteral(hit.o);
      if (v) {
        title = v;
        break;
      }
    }
  }
  if (!title) title = localName(iri);

  // Structural/meta properties that are never meaningful card fields.
  const SKIP_PROPS = new Set([
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
    "http://www.w3.org/2000/01/rdf-schema#subClassOf",
    "http://www.w3.org/2002/07/owl#sameAs",
  ]);

  // Group object-property and datatype-property values keyed by property IRI.
  // Use the same property labels we already discovered (filters) where possible.
  const fieldMap = new Map<string, { propLabel: string; values: string[]; isObject: boolean }>();
  for (const b of r.results.bindings) {
    const p = asIri(b.p);
    if (!p || labelPropSet.has(p) || SKIP_PROPS.has(p)) continue;
    const f = propsByIri.get(p);
    // Use the discovered property label, otherwise local name (no IRI rendering)
    const propLabel = f?.property.label ?? localName(p);
    const o = b.o;
    if (!o) continue;
    let display: string | undefined;
    if (o.type === "uri") {
      display = asLiteral(b.oLabel) ?? localName(o.value);
    } else if (o.type === "literal") {
      display = o.value;
    }
    if (!display) continue;
    const isObject = o.type === "uri";
    const cur = fieldMap.get(p) ?? { propLabel, values: [], isObject };
    cur.values.push(display);
    fieldMap.set(p, cur);
  }

  // Order: object-property fields first (genres, roles, etc.), then datatype.
  const objectFields: CardField[] = [];
  const dataFields: CardField[] = [];
  for (const { propLabel, values, isObject } of fieldMap.values()) {
    const sorted = [...new Set(values)].sort((a, b) => a.localeCompare(b));
    (isObject ? objectFields : dataFields).push({ property: propLabel, values: sorted });
  }
  objectFields.sort((a, b) => a.property.localeCompare(b.property));
  dataFields.sort((a, b) => a.property.localeCompare(b.property));
  return { iri, label: title, fields: [...objectFields, ...dataFields] };
}
