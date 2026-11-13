import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CatalogProductDetail } from "@/lib/api";

/**
 * A product's own page, which lives on its shop's subdomain.
 *
 * One address per product: opened anywhere else it moves the visitor into the shop with a
 * permanent redirect, so a link shared from the marketplace host still lands where the product
 * belongs and search engines learn the one canonical address rather than two.
 *
 * A product that is not public answers exactly as one that does not exist. Anything else tells a
 * stranger which identifiers are real, and for a product awaiting moderation it would also show
 * the shop's unapproved work to whoever guessed the link.
 *
 * The storefront is asked for by host, and a refusal of it only ever costs the page its colours:
 * a barred buyer never gets this far, because the product itself answers 404 for them.
 */

const notFound = vi.fn(() => {
  throw new Error("not-found");
});
const permanentRedirect = vi.fn((to: string) => {
  throw new Error(`redirect:${to}`);
});

vi.mock("next/navigation", () => ({
  notFound: () => notFound(),
  permanentRedirect: (to: string) => permanentRedirect(to),
}));

vi.mock("@/lib/api", () => ({
  fetchCatalogProduct: vi.fn(),
  fetchStorefront: vi.fn(),
  STORE_BLOCKED: "store-blocked",
}));

vi.mock("@/lib/request-host", () => ({ currentSubdomain: vi.fn() }));

vi.mock("@/components/StoreContacts", () => ({
  StoreContacts: () => <div data-testid="contacts" />,
}));

vi.mock("@/components/ReportButton", () => ({
  ReportButton: () => <button type="button">Пожаловаться</button>,
}));

const { fetchCatalogProduct, fetchStorefront } = await import("@/lib/api");
const { currentSubdomain } = await import("@/lib/request-host");
const { default: ProductPage, generateMetadata } =
  await import("@/app/(public)/p/[productId]/page");

const PRODUCT = "11111111-1111-1111-1111-111111111111";

function detail(overrides: Partial<CatalogProductDetail> = {}): CatalogProductDetail {
  return {
    id: PRODUCT,
    name: "Чашка",
    description: null,
    price: "1500.00",
    currency: "AMD",
    availability_status: "in_stock",
    category: { slug: "dishes", name: "Посуда" },
    store: { subdomain: "cups", display_name: "Лавка кружек", contacts: [] },
    images: [],
    created_at: "2026-11-13T00:00:00Z",
    ...overrides,
  } as CatalogProductDetail;
}

const props = {
  params: Promise.resolve({ productId: PRODUCT }),
  searchParams: Promise.resolve({}),
};

beforeEach(() => {
  notFound.mockClear();
  permanentRedirect.mockClear();
  vi.mocked(currentSubdomain).mockReset().mockResolvedValue("cups");
  vi.mocked(fetchCatalogProduct).mockReset().mockResolvedValue(detail());
  vi.mocked(fetchStorefront).mockReset().mockResolvedValue(null);
});

describe("product page", () => {
  it("shows the product on its own shop's host", async () => {
    render(await ProductPage(props));

    expect(screen.getByRole("heading", { name: "Чашка", level: 1 })).toBeInTheDocument();
    expect(screen.getByTestId("contacts")).toBeInTheDocument();
  });

  it("answers as if the product did not exist when it is not public", async () => {
    vi.mocked(fetchCatalogProduct).mockResolvedValue(null);

    await expect(ProductPage(props)).rejects.toThrow("not-found");
    expect(notFound).toHaveBeenCalled();
  });

  it("moves a visitor who opened it elsewhere into the shop, permanently", async () => {
    vi.mocked(currentSubdomain).mockResolvedValue(null);

    await expect(ProductPage(props)).rejects.toThrow(/redirect/);
    expect(permanentRedirect.mock.calls[0]?.[0]).toContain(`cups.`);
  });

  it("moves them out of a shop that is not the product's", async () => {
    vi.mocked(currentSubdomain).mockResolvedValue("wool");

    await expect(ProductPage(props)).rejects.toThrow(/redirect/);
  });

  it("says where to come back to in the whole catalogue", async () => {
    render(await ProductPage(props));

    const crumb = screen.getByRole("link", { name: /Каталог AllStore/ });
    expect(crumb.getAttribute("href")).toContain("/catalog");
    expect(screen.getByRole("link", { name: "Посуда" }).getAttribute("href")).toContain(
      "category=dishes",
    );
  });

  it("is a page without a photograph, rather than a hole where one would be", async () => {
    render(await ProductPage(props));

    expect(screen.getByText("Без фото")).toBeInTheDocument();
  });

  it("describes the photograph by what it was called, or by the product", async () => {
    vi.mocked(fetchCatalogProduct).mockResolvedValue(
      detail({ images: [{ image_url: "https://cdn.allstore.am/a.png", alt_text: null }] }),
    );

    render(await ProductPage(props));

    expect(screen.getByRole("img", { name: "Чашка" })).toBeInTheDocument();
  });

  it("renders even when the storefront refused the viewer, losing only its colours", async () => {
    vi.mocked(fetchStorefront).mockResolvedValue("store-blocked");

    render(await ProductPage(props));

    expect(screen.getByRole("heading", { name: "Чашка", level: 1 })).toBeInTheDocument();
  });

  it("offers a way to complain about it", async () => {
    render(await ProductPage(props));

    expect(screen.getByRole("button", { name: "Пожаловаться" })).toBeInTheDocument();
  });
});

describe("what a search engine is told", () => {
  it("points at the one address the product lives on", async () => {
    const meta = await generateMetadata(props);

    expect(meta.alternates?.canonical).toContain("cups.");
    expect(meta.title).toBe("Чашка — Лавка кружек");
  });

  it("describes a product with no description by where it is sold", async () => {
    const meta = await generateMetadata(props);

    expect(meta.description).toBe("Чашка в магазине Лавка кружек");
  });

  it("asks not to be indexed when there is no such product", async () => {
    vi.mocked(fetchCatalogProduct).mockResolvedValue(null);

    const meta = await generateMetadata(props);

    expect(meta.robots).toEqual({ index: false });
    expect(meta.title).toBe("Товар не найден");
  });
});
