import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CatalogProduct } from "@/lib/api";

vi.mock("next/headers", () => ({
  headers: () => Promise.resolve(new Headers({ host: "allstore.am" })),
}));

vi.mock("@/lib/api", () => ({
  PAGE_SIZE: 24,
  fetchCatalogProducts: vi.fn(),
  fetchCategories: vi.fn(),
}));

const { fetchCatalogProducts, fetchCategories } = await import("@/lib/api");
const { default: CatalogPage } = await import("@/app/(public)/catalog/page");

function product(id: string, name: string): CatalogProduct {
  return {
    id,
    name,
    description: null,
    price: "4500.00",
    currency: "AMD",
    availability_status: "in_stock",
    category: { slug: "tableware", name: "Посуда" },
    store: { subdomain: "cups", display_name: "Лавка кружек" },
    images: [],
    created_at: "2026-09-21T00:00:00Z",
  };
}

const VASE = product("11111111-1111-1111-1111-111111111111", "Ваза «Гюмри»");
const PLAID = product("22222222-2222-2222-2222-222222222222", "Плед шерстяной");

const props = (q: string) => ({
  params: Promise.resolve({}),
  searchParams: Promise.resolve({ q }),
});

beforeEach(() => {
  vi.mocked(fetchCatalogProducts).mockReset();
  vi.mocked(fetchCategories).mockResolvedValue([]);
});

describe("catalog page", () => {
  it("marks the products the words of the query are not in", async () => {
    vi.mocked(fetchCatalogProducts).mockResolvedValue({
      items: [VASE, PLAID],
      total: 2,
      limit: 24,
      offset: 0,
      by_meaning: [PLAID.id],
    });

    render(await CatalogPage(props("ваза")));

    // one badge, on the card that did not match by words
    const badges = screen.getAllByText("по смыслу");
    expect(badges).toHaveLength(1);
    expect(badges[0]?.closest("a")).toHaveAccessibleName(/Плед шерстяной/u);
  });

  it("says nothing extra when every product matched by words", async () => {
    vi.mocked(fetchCatalogProducts).mockResolvedValue({
      items: [VASE],
      total: 1,
      limit: 24,
      offset: 0,
      by_meaning: [],
    });

    render(await CatalogPage(props("ваза")));

    expect(screen.queryByText("по смыслу")).not.toBeInTheDocument();
  });

  it("invites a description of the thing when nothing was found", async () => {
    vi.mocked(fetchCatalogProducts).mockResolvedValue({
      items: [],
      total: 0,
      limit: 24,
      offset: 0,
      by_meaning: [],
    });

    render(await CatalogPage(props("абракадабра")));

    expect(screen.getByText(/опишите словами|описать словами/iu)).toBeInTheDocument();
  });
});
