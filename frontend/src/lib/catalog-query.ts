export type CatalogQuery = {
  q: string | null;
  category: string | null;
  store: string | null;
  offset: number;
};

/** Next hands search params over as a record; a repeated key keeps its first value. */
export function toSearchParams(
  input: Record<string, string | string[] | undefined>,
): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(input)) {
    const single = typeof value === "string" ? value : value?.[0];
    if (single !== undefined) {
      params.set(key, single);
    }
  }
  return params;
}

/** What the address bar carries, with anything it cannot make sense of dropped. */
export function parseCatalogQuery(params: URLSearchParams): CatalogQuery {
  const offset = Number(params.get("offset"));
  return {
    q: params.get("q")?.trim() || null,
    category: params.get("category")?.trim() || null,
    store: params.get("store")?.trim() || null,
    offset: Number.isSafeInteger(offset) && offset > 0 ? offset : 0,
  };
}

/** The reverse, so a link back to the catalogue keeps the filters the visitor chose. */
export function catalogSearchParams(query: CatalogQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.q !== null) {
    params.set("q", query.q);
  }
  if (query.category !== null) {
    params.set("category", query.category);
  }
  if (query.store !== null) {
    params.set("store", query.store);
  }
  if (query.offset > 0) {
    params.set("offset", String(query.offset));
  }
  return params;
}
