import { ask, select, asIri, asLiteral, localName } from "./client";

const RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label";
const XSD = "http://www.w3.org/2001/XMLSchema#";
export const XSD_GYEAR = `${XSD}gYear`;
export const XSD_BOOLEAN = `${XSD}boolean`;
export const XSD_INTEGER = `${XSD}integer`;
export const XSD_STRING = `${XSD}string`;
export const XSD_DECIMAL = `${XSD}decimal`;
export const XSD_DOUBLE = `${XSD}double`;
const OWL_DATATYPE_PROP = "http://www.w3.org/2002/07/owl#DatatypeProperty";
const OWL_OBJECT_PROP = "http://www.w3.org/2002/07/owl#ObjectProperty";

export type FilterKind = "enum" | "year" | "integer" | "boolean" | "text";

export interface DiscoveredClass {
  iri: string;
  label: string;
}

export interface DiscoveredProperty {
  iri: string;
  label: string;
  range?: string;
  isObjectProperty: boolean;
  isDatatypeProperty: boolean;
}

export interface EnumValue {
  iri: string;
  label: string;
}

export interface FilterDef {
  property: DiscoveredProperty;
  kind: FilterKind;
  values?: EnumValue[]; // for enum filters
  yearBounds?: { lo?: number; hi?: number }; // for year filters
}

const lang = `(LANG(?label) = "en" || LANG(?label) = "")`;

// D1: enumerate the root + its subclasses
export async function discoverClasses(rootIri: string): Promise<DiscoveredClass[]> {
  const q = `
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?class ?label WHERE {
  ?class rdfs:subClassOf* <${rootIri}> .
  OPTIONAL { ?class rdfs:label ?label . FILTER(${lang}) }
}`;
  const r = await select(q);
  return r.results.bindings
    .map((b) => {
      const iri = asIri(b.class);
      if (!iri) return null;
      return { iri, label: asLiteral(b.label) ?? localName(iri) };
    })
    .filter((x): x is DiscoveredClass => x !== null);
}

// Helper: fetch label for a single class (used for the root navigator)
export async function fetchClassLabel(classIri: string): Promise<string> {
  const q = `
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?label WHERE {
  <${classIri}> rdfs:label ?label . FILTER(${lang})
} LIMIT 1`;
  const r = await select(q);
  return asLiteral(r.results.bindings[0]?.label) ?? localName(classIri);
}

// D2: candidate filter properties for a root
export async function discoverProperties(rootIri: string): Promise<DiscoveredProperty[]> {
  const q = `
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
SELECT DISTINCT ?prop ?label ?range ?propType WHERE {
  ?prop rdfs:domain ?domain .
  ?domain (owl:unionOf/rdf:rest*/rdf:first)? ?effective .
  # owl:Thing is excluded because OWL 2 RL closure makes every class a
  # subclass of owl:Thing and may materialise owl:Thing as a domain;
  # without this filter every property would show up under every root.
  FILTER(?effective != owl:Thing)
  # If the domain is a blank node (i.e. an owl:unionOf expression), only
  # follow it when the property has no asserted IRI domain. Otherwise the
  # bnode is a closure-derived domain (OWL 2 RL rule scm-dom1) lifting
  # the asserted domain through subClassOf into a union, which would
  # spuriously associate the property with the union's other members.
  FILTER(!isBlank(?domain) || NOT EXISTS {
    ?prop rdfs:domain ?asserted .
    FILTER(isIRI(?asserted) && ?asserted != owl:Thing)
  })
  { <${rootIri}> rdfs:subClassOf* ?effective . }
  UNION
  { ?effective rdfs:subClassOf* <${rootIri}> . }
  OPTIONAL { ?prop rdfs:label ?label . FILTER(${lang}) }
  OPTIONAL { ?prop rdfs:range ?range . }
  OPTIONAL { ?prop a ?propType . FILTER(?propType IN (owl:DatatypeProperty, owl:ObjectProperty)) }
}`;
  const r = await select(q);
  // group by prop IRI
  const byProp = new Map<string, DiscoveredProperty>();
  for (const b of r.results.bindings) {
    const iri = asIri(b.prop);
    if (!iri) continue;
    const existing = byProp.get(iri) ?? {
      iri,
      label: asLiteral(b.label) ?? localName(iri),
      range: undefined,
      isObjectProperty: false,
      isDatatypeProperty: false,
    };
    if (asLiteral(b.label) && existing.label === localName(iri)) {
      existing.label = asLiteral(b.label)!;
    }
    const rng = asIri(b.range);
    if (rng && rng !== "http://www.w3.org/2002/07/owl#Thing" && !existing.range) existing.range = rng;
    const t = asIri(b.propType);
    if (t === OWL_OBJECT_PROP) existing.isObjectProperty = true;
    if (t === OWL_DATATYPE_PROP) existing.isDatatypeProperty = true;
    byProp.set(iri, existing);
  }
  return [...byProp.values()];
}

// D3a: is this range a controlled vocabulary?
export async function rangeIsVocabulary(rangeIri: string): Promise<boolean> {
  if (rangeIri === "http://www.w3.org/2002/07/owl#Thing") return false;
  const q = `
PREFIX owl: <http://www.w3.org/2002/07/owl#>
ASK { ?ni a owl:NamedIndividual, <${rangeIri}> }`;
  return ask(q);
}

// D3b: list values of an enumerated range
export async function discoverEnumValues(rangeIri: string): Promise<EnumValue[]> {
  const q = `
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?value ?label WHERE {
  ?value a <${rangeIri}> .
  OPTIONAL { ?value rdfs:label ?label . FILTER(${lang}) }
} ORDER BY ?label`;
  const r = await select(q);
  return r.results.bindings
    .map((b) => {
      const iri = asIri(b.value);
      if (!iri) return null;
      return { iri, label: asLiteral(b.label) ?? localName(iri) };
    })
    .filter((x): x is EnumValue => x !== null);
}

// Helper: fetch year min/max for an xsd:gYear property (used to seed range UI)
export async function fetchYearBounds(
  rootIri: string,
  propIri: string,
): Promise<{ lo?: number; hi?: number }> {
  const q = `
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
SELECT (MIN(?y) AS ?lo) (MAX(?y) AS ?hi) WHERE {
  ?w a <${rootIri}> .
  ?w <${propIri}> ?y .
}`;
  const r = await select(q);
  const b = r.results.bindings[0];
  const parse = (v?: string) => {
    if (!v) return undefined;
    const m = v.match(/-?\d+/);
    return m ? Number(m[0]) : undefined;
  };
  return { lo: parse(asLiteral(b?.lo)), hi: parse(asLiteral(b?.hi)) };
}

// D5: discover label-properties for the root
export async function discoverLabelProperties(rootIri: string): Promise<string[]> {
  const q = `
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
SELECT DISTINCT ?labelProp (COUNT(?mid) AS ?depth) WHERE {
  ?labelProp rdfs:subPropertyOf* ?mid .
  ?mid rdfs:subPropertyOf* rdfs:label .
  ?labelProp rdfs:domain ?domain .
  ?domain (owl:unionOf/rdf:rest*/rdf:first)? ?effective .
  FILTER(?effective != owl:Thing)
  FILTER(!isBlank(?domain) || NOT EXISTS {
    ?labelProp rdfs:domain ?asserted .
    FILTER(isIRI(?asserted) && ?asserted != owl:Thing)
  })
  { <${rootIri}> rdfs:subClassOf* ?effective . }
  UNION
  { ?effective rdfs:subClassOf* <${rootIri}> . }
}
GROUP BY ?labelProp
ORDER BY ?depth`;
  const r = await select(q);
  const props = r.results.bindings
    .map((b) => asIri(b.labelProp))
    .filter((x): x is string => Boolean(x));
  // append rdfs:label as universal fallback if not already present
  if (!props.includes(RDFS_LABEL)) props.push(RDFS_LABEL);
  return props;
}

// Combine discovery into a list of usable filter definitions
export async function buildFilters(
  rootIri: string,
  properties: DiscoveredProperty[],
): Promise<FilterDef[]> {
  const filters: FilterDef[] = [];
  for (const p of properties) {
    if (p.isObjectProperty && p.range) {
      const vocab = await rangeIsVocabulary(p.range);
      if (!vocab) continue;
      const values = await discoverEnumValues(p.range);
      if (values.length === 0) continue;
      filters.push({ property: p, kind: "enum", values });
      continue;
    }
    if (p.isDatatypeProperty && p.range) {
      switch (p.range) {
        case XSD_GYEAR: {
          const yearBounds = await fetchYearBounds(rootIri, p.iri);
          filters.push({ property: p, kind: "year", yearBounds });
          break;
        }
        case XSD_BOOLEAN:
          filters.push({ property: p, kind: "boolean" });
          break;
        case XSD_INTEGER:
        case XSD_DECIMAL:
        case XSD_DOUBLE:
          filters.push({ property: p, kind: "integer" });
          break;
        case XSD_STRING:
          filters.push({ property: p, kind: "text" });
          break;
        default:
          break; // skipped silently
      }
    }
  }
  // sort filters by label for stable display
  filters.sort((a, b) => a.property.label.localeCompare(b.property.label));
  return filters;
}