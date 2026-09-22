import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CatalogProduct, CatalogStore } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  PAGE_SIZE: 24,
  fetchCatalogProducts: vi.fn(),
  fetchCatalogStores: vi.fn(),
}));

const { fetchCatalogProducts, fetchCatalogStores } = await import("@/lib/api");
const { default: sitemap } = await import("@/app/sitemap");

const STATIC_PAGES = [
  "https://allstore.am/",
  "https://allstore.am/catalog",
  "https://allstore.am/stores",
];

function product(index: number): CatalogProduct {
  return {
    id: `product-${index}`,
    name: `Товар ${index}`,
    description: null,
    price: "100.00",
    currency: "AMD",
    availability_status: "in_stock",
    category: { slug: "tableware", name: "Посуда" },
    store: { subdomain: "cups", display_name: "Лавка кружек" },
    images: [],
    created_at: "2026-09-21T00:00:00Z",
  };
}

function store(index: number): CatalogStore {
  return {
    subdomain: `shop-${index}`,
    display_name: `Магазин ${index}`,
    description: null,
    logo_url: null,
    banner_url: null,
    contacts: [],
  };
}

/** Answers a page at a time out of a list, the way the backend does. */
function pagedFrom<T>(items: T[]) {
  return (offsetOrQuery: unknown, _limit?: number, offsetFromQuery?: number) => {
    const offset =
      typeof offsetOrQuery === "number"
        ? offsetOrQuery
        : ((offsetOrQuery as { offset: number }).offset ?? offsetFromQuery ?? 0);
    return Promise.resolve({
      items: items.slice(offset, offset + 100),
      total: items.length,
      limit: 100,
      offset,
    });
  };
}

beforeEach(() => {
  vi.mocked(fetchCatalogProducts).mockReset();
  vi.mocked(fetchCatalogStores).mockReset();
  vi.mocked(fetchCatalogProducts).mockImplementation(pagedFrom([]));
  vi.mocked(fetchCatalogStores).mockImplementation(pagedFrom([]));
});

describe("sitemap", () => {
  it("always carries the pages that are always there", async () => {
    const entries = await sitemap();

    expect(entries.map((entry) => entry.url)).toEqual(STATIC_PAGES);
  });

  it("sends a crawler to the subdomain of a shop and to the marketplace for a product", async () => {
    vi.mocked(fetchCatalogStores).mockImplementation(pagedFrom([store(1)]));
    vi.mocked(fetchCatalogProducts).mockImplementation(pagedFrom([product(1)]));

    const urls = (await sitemap()).map((entry) => entry.url);

    expect(urls).toContain("https://shop-1.allstore.am/");
    expect(urls).toContain("https://cups.allstore.am/p/product-1");
  });

  it("walks through every page of the catalogue", async () => {
    const many = Array.from({ length: 250 }, (_, index) => product(index));
    vi.mocked(fetchCatalogProducts).mockImplementation(pagedFrom(many));

    const entries = await sitemap();

    expect(entries).toHaveLength(STATIC_PAGES.length + many.length);
    expect(vi.mocked(fetchCatalogProducts)).toHaveBeenCalledTimes(3);
  });

  it("stops short rather than breaks when the backend cannot answer", async () => {
    vi.mocked(fetchCatalogProducts).mockResolvedValue(null);

    const entries = await sitemap();

    expect(entries.map((entry) => entry.url)).toEqual(STATIC_PAGES);
  });

  it("does not grow past the cap of one file", async () => {
    const tooMany = Array.from({ length: 6000 }, (_, index) => product(index));
    vi.mocked(fetchCatalogProducts).mockImplementation(pagedFrom(tooMany));

    const entries = await sitemap();

    expect(entries).toHaveLength(STATIC_PAGES.length + 5000);
  });

  it("dates a product entry by when it appeared", async () => {
    vi.mocked(fetchCatalogProducts).mockImplementation(pagedFrom([product(1)]));

    const entry = (await sitemap()).find((item) => item.url.includes("/p/"));

    expect(entry?.lastModified).toBe("2026-09-21T00:00:00Z");
  });
});
