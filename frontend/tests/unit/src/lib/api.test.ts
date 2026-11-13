import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CatalogQuery } from "@/lib/catalog-query";

/**
 * What the server reads on the visitor's behalf while rendering a page.
 *
 * Two promises are kept here and both have teeth. The viewer's cookies travel with public
 * reads, because a shop that has barred this buyer drops out of their listings and the backend
 * can only decide that if it knows who is asking — rendering anonymously would show them a
 * shop the API would then refuse. And "could not be read" is a different answer from "there is
 * nothing": the two used to be the same value, which hid a backend that was down behind a form
 * with nothing to choose from.
 */

const jar = vi.hoisted(() => ({ value: "" }));

vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({ toString: () => jar.value }),
}));

type Call = { url: string; init: RequestInit };

function answering(response: unknown): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return Promise.resolve(response);
  });
  return calls;
}

function json(status: number, payload: unknown): unknown {
  return { ok: status < 400, status, json: () => Promise.resolve(payload) };
}

function query(overrides: Partial<CatalogQuery> = {}): CatalogQuery {
  return { q: null, category: null, store: null, offset: 0, ...overrides };
}

function cookieOf(init: RequestInit): string | undefined {
  return (init.headers as Record<string, string> | undefined)?.["cookie"];
}

beforeEach(() => {
  jar.value = "";
});

describe("reading on the visitor's behalf", () => {
  it("sends their cookies, so the backend can hide a shop that barred them", async () => {
    jar.value = "allstore_session=a-token";
    const calls = answering(json(200, { items: [], total: 0 }));
    const { fetchCatalogStores } = await import("@/lib/api");

    await fetchCatalogStores(0);

    expect(cookieOf(calls[0]!.init)).toBe("allstore_session=a-token");
  });

  it("sends no cookie header at all when the visitor has no cookies", async () => {
    const calls = answering(json(200, { items: [], total: 0 }));
    const { fetchCatalogStores } = await import("@/lib/api");

    await fetchCatalogStores(0);

    expect(cookieOf(calls[0]!.init)).toBeUndefined();
  });

  it("never serves a page from a cache, because who is asking changes the answer", async () => {
    const calls = answering(json(200, { items: [], total: 0 }));
    const { fetchCatalogStores } = await import("@/lib/api");

    await fetchCatalogStores(0);

    expect(calls[0]!.init.cache).toBe("no-store");
  });
});

describe("a storefront that refused the visitor", () => {
  it("says so, because a 404 would be a riddle to somebody who shopped there last week", async () => {
    answering(json(403, {}));
    const { fetchStorefront, STORE_BLOCKED } = await import("@/lib/api");

    expect(await fetchStorefront("shop")).toBe(STORE_BLOCKED);
  });

  it("is null when the shop genuinely is not there", async () => {
    answering(json(404, {}));
    const { fetchStorefront } = await import("@/lib/api");

    expect(await fetchStorefront("shop")).toBeNull();
  });

  it("is addressed by subdomain, with the subdomain escaped", async () => {
    const calls = answering(json(200, { subdomain: "shop" }));
    const { fetchStorefront } = await import("@/lib/api");

    await fetchStorefront("не шоп/../admin");

    expect(calls[0]!.url).toContain("/storefront/%D0%BD%D0%B5%20%D1%88%D0%BE%D0%BF%2F..%2Fadmin");
  });
});

describe("could not be read is not the same as there is nothing", () => {
  it("answers null when the catalogue cannot be read", async () => {
    answering(json(503, {}));
    const { fetchCatalogProducts } = await import("@/lib/api");

    expect(await fetchCatalogProducts(query())).toBeNull();
  });

  it("answers an empty list when the catalogue is simply empty", async () => {
    answering(json(200, { items: [], total: 0 }));
    const { fetchCatalogProducts } = await import("@/lib/api");

    expect(await fetchCatalogProducts(query())).toEqual({ items: [], total: 0 });
  });

  it("answers null for the categories when the reference cannot be read", async () => {
    answering(json(500, {}));
    const { fetchCategories } = await import("@/lib/api");

    expect(await fetchCategories()).toBeNull();
  });

  it("answers an empty tree when there are no categories yet", async () => {
    answering(json(200, []));
    const { fetchCategories } = await import("@/lib/api");

    expect(await fetchCategories()).toEqual([]);
  });

  it("answers null for the health check rather than throwing at the admin page", async () => {
    answering(json(502, {}));
    const { fetchBackendHealth } = await import("@/lib/api");

    expect(await fetchBackendHealth()).toBeNull();
  });
});

describe("the query a listing asks for", () => {
  it("carries the page size the listing renders", async () => {
    const calls = answering(json(200, { items: [], total: 0 }));
    const { fetchCatalogProducts, PAGE_SIZE } = await import("@/lib/api");

    await fetchCatalogProducts(query());

    expect(calls[0]!.url).toContain(`limit=${PAGE_SIZE}`);
  });

  it("carries what the visitor filtered by", async () => {
    const calls = answering(json(200, { items: [], total: 0 }));
    const { fetchCatalogProducts } = await import("@/lib/api");

    await fetchCatalogProducts(query({ q: "ваза", offset: 24 }));

    expect(calls[0]!.url).toContain("q=%D0%B2%D0%B0%D0%B7%D0%B0");
    expect(calls[0]!.url).toContain("offset=24");
  });

  it("asks for as many stores as it was told to", async () => {
    const calls = answering(json(200, { items: [], total: 0 }));
    const { fetchCatalogStores } = await import("@/lib/api");

    await fetchCatalogStores(48, 12);

    expect(calls[0]!.url).toContain("limit=12");
    expect(calls[0]!.url).toContain("offset=48");
  });
});
