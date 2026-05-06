import { SPARQL_ENDPOINT } from "../config";

export type SparqlBindingValue =
  | { type: "uri"; value: string }
  | { type: "literal"; value: string; "xml:lang"?: string; datatype?: string }
  | { type: "bnode"; value: string };

export type SparqlBinding = Record<string, SparqlBindingValue | undefined>;

export interface SparqlSelectResult {
  head: { vars: string[] };
  results: { bindings: SparqlBinding[] };
}

export interface SparqlAskResult {
  head: Record<string, never>;
  boolean: boolean;
}

export class SparqlError extends Error {
  constructor(message: string, public readonly query: string) {
    super(message);
    this.name = "SparqlError";
  }
}

async function run(query: string): Promise<unknown> {
  const base =
    typeof window !== "undefined" ? window.location.origin : "http://localhost";
  const url = new URL(SPARQL_ENDPOINT, base);
  url.searchParams.set("query", query);
  let resp: Response;
  try {
    resp = await fetch(url.toString(), {
      method: "GET",
      headers: { Accept: "application/sparql-results+json" },
    });
  } catch (e) {
    throw new SparqlError(`Network error: ${(e as Error).message}`, query);
  }
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new SparqlError(`HTTP ${resp.status}: ${body || resp.statusText}`, query);
  }
  return resp.json();
}

export async function select(query: string): Promise<SparqlSelectResult> {
  return (await run(query)) as SparqlSelectResult;
}

export async function ask(query: string): Promise<boolean> {
  const json = (await run(query)) as SparqlAskResult;
  return Boolean(json.boolean);
}

export function localName(iri: string): string {
  const hash = iri.lastIndexOf("#");
  if (hash !== -1) return iri.slice(hash + 1);
  const slash = iri.lastIndexOf("/");
  if (slash !== -1) return iri.slice(slash + 1);
  return iri;
}

export function asIri(v: SparqlBindingValue | undefined): string | undefined {
  return v && v.type === "uri" ? v.value : undefined;
}

export function asLiteral(v: SparqlBindingValue | undefined): string | undefined {
  return v && v.type === "literal" ? v.value : undefined;
}
