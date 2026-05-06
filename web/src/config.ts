const env = (import.meta as ImportMeta).env;

export const SPARQL_ENDPOINT: string = env.VITE_SPARQL_ENDPOINT ?? "/sparql";

export const ROOTS: string[] = (env.VITE_ROOTS ?? "")
  .split(",")
  .map((s: string) => s.trim())
  .filter(Boolean);

if (ROOTS.length === 0) {
  ROOTS.push("http://localhost:3030/culturalworks/ontology#CreativeWork");
}

export const APP_TITLE: string = env.VITE_APP_TITLE ?? "Cultural Works Browser";

export const PAGE_SIZE = 50;
export const RESULT_CAP = 1000;
export const MAX_PAGE = 20;
export const ENUM_COMBOBOX_THRESHOLD = 10;
