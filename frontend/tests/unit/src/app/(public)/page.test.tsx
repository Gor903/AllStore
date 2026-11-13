import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CatalogProduct, CatalogStore } from "@/lib/api";

/**
 * The front page.
 *
 * Both listings answer newest first and hold only what a visitor may see, so the two blocks are
 * simply the head of each — nothing is picked here and nothing has to be kept up to date by
 * hand. What the page has to survive is a catalogue that could not be read at all: the front
 * page of a marketplace must still be a page, with its way into the catalogue and its invitation
 * to open a shop, rather than an error.
 *
 * The product links are built against the host the visitor is on, because a storefront renders
 * this page too and a link to another shop has to leave the subdomain it is rendered on.
 */

vi.mock("@/lib/api", () => ({
  fetchCatalogProducts: vi.fn(),
  fetchCatalogStores: vi.fn(),
}));

vi.mock("@/lib/request-host", () => ({ currentSubdomain: vi.fn() }));

vi.mock("@/components/SiteHeader", () => ({
  SiteHeader: () => <header data-testid="site-header" />,
}));

vi.mock("@/components/catalog/ProductCard", () => ({
  ProductCard: ({ product, href }: { product: CatalogProduct; href: string }) => (
    <a data-testid="product" href={href}>
      {product.name}
    </a>
  ),
}));

vi.mock("@/components/catalog/StoreCard", () => ({
  StoreCard: ({ store }: { store: CatalogStore }) => (
    <div data-testid="store">{store.display_name}</div>
  ),
}));

const { fetchCatalogProducts, fetchCatalogStores } = await import("@/lib/api");
const { currentSubdomain } = await import("@/lib/request-host");
const { default: HomePage } = await import("@/app/(public)/page");

function product(id: string, name: string): CatalogProduct {
  return {
    id,
    name,
    description: null,
    price: "1500.00",
    currency: "AMD",
    availability_status: "in_stock",
    category: { slug: "dishes", name: "Посуда" },
    store: { subdomain: "cups", display_name: "Лавка кружек" },
    images: [],
    created_at: "2026-11-13T00:00:00Z",
  };
}

function store(subdomain: string, displayName: string): CatalogStore {
  return {
    subdomain,
    display_name: displayName,
    description: null,
    logo_url: null,
    banner_url: null,
    contacts: [],
  };
}

beforeEach(() => {
  vi.mocked(currentSubdomain).mockReset().mockResolvedValue(null);
  vi.mocked(fetchCatalogProducts)
    .mockReset()
    .mockResolvedValue({
      items: [product("11111111-1111-1111-1111-111111111111", "Чашка")],
      total: 1,
      limit: 8,
      offset: 0,
      by_meaning: [],
    });
  vi.mocked(fetchCatalogStores)
    .mockReset()
    .mockResolvedValue({ items: [store("cups", "Лавка кружек")], total: 1, limit: 6, offset: 0 });
});

describe("home page", () => {
  it("says what the platform is and offers both doors", async () => {
    render(await HomePage());

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Магазины Армении");
    expect(screen.getByRole("link", { name: "Смотреть каталог" })).toHaveAttribute(
      "href",
      "/catalog",
    );
    expect(screen.getByRole("link", { name: "Открыть магазин" })).toHaveAttribute(
      "href",
      "/register",
    );
  });

  it("shows the newest products and the newest shops", async () => {
    render(await HomePage());

    expect(screen.getByTestId("product")).toHaveTextContent("Чашка");
    expect(screen.getByTestId("store")).toHaveTextContent("Лавка кружек");
  });

  it("asks for a handful of each rather than a page of them", async () => {
    render(await HomePage());

    expect(fetchCatalogProducts).toHaveBeenCalledWith(
      { q: null, category: null, store: null, offset: 0 },
      8,
    );
    expect(fetchCatalogStores).toHaveBeenCalledWith(0, 6);
  });

  it("is still a page when the catalogue could not be read", async () => {
    vi.mocked(fetchCatalogProducts).mockResolvedValue(null);
    vi.mocked(fetchCatalogStores).mockResolvedValue(null);

    render(await HomePage());

    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Смотреть каталог" })).toBeInTheDocument();
    expect(screen.queryByTestId("product")).not.toBeInTheDocument();
  });

  it("shows no empty blocks when there is nothing new", async () => {
    vi.mocked(fetchCatalogProducts).mockResolvedValue({
      items: [],
      total: 0,
      limit: 8,
      offset: 0,
      by_meaning: [],
    });
    vi.mocked(fetchCatalogStores).mockResolvedValue({ items: [], total: 0, limit: 6, offset: 0 });

    render(await HomePage());

    expect(screen.queryByRole("heading", { name: "Новые товары" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Новые магазины" })).not.toBeInTheDocument();
  });

  it("keeps a product link relative while the visitor is in that shop", async () => {
    vi.mocked(currentSubdomain).mockResolvedValue("cups");

    render(await HomePage());

    expect(screen.getByTestId("product")).toHaveAttribute(
      "href",
      "/p/11111111-1111-1111-1111-111111111111",
    );
  });

  it("makes it absolute from anywhere else, because the shop is another host", async () => {
    render(await HomePage());

    expect(screen.getByTestId("product").getAttribute("href")).toContain("cups.");
  });
});
