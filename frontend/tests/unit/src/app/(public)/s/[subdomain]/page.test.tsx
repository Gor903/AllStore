import { render, screen } from "@testing-library/react";
import type React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CatalogProduct, Storefront } from "@/lib/api";

/**
 * A shop's own storefront.
 *
 * Three answers that look alike and are not. A shop that does not exist is a 404. A shop that has
 * barred this buyer is told so in words — the shop decided it, not the platform, and the visitor
 * knows the shop exists, so a riddle would be worse than a sentence. And a shop opened on the
 * marketplace path is moved to its own address, permanently, because that is the one address it
 * has.
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
  PAGE_SIZE: 24,
  STORE_BLOCKED: "store-blocked",
  fetchStorefront: vi.fn(),
  fetchCatalogProducts: vi.fn(),
}));

vi.mock("@/lib/request-host", () => ({ currentSubdomain: vi.fn() }));

vi.mock("@/components/StoreContacts", () => ({
  StoreContacts: () => <div data-testid="contacts" />,
}));

vi.mock("@/components/ReportButton", () => ({
  ReportButton: () => <button type="button">Пожаловаться</button>,
}));

vi.mock("@/components/StorefrontGuard", () => ({
  // the guard asks the marketplace host who is reading; here it is a pass-through
  StorefrontGuard: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="guard">{children}</div>
  ),
}));

const { fetchStorefront, fetchCatalogProducts } = await import("@/lib/api");
const { currentSubdomain } = await import("@/lib/request-host");
const { default: StorefrontPage, generateMetadata } =
  await import("@/app/(public)/s/[subdomain]/page");

function storefront(overrides: Partial<Storefront> = {}): Storefront {
  return {
    subdomain: "cups",
    display_name: "Лавка кружек",
    description: null,
    logo_url: null,
    banner_url: null,
    primary_color: null,
    secondary_color: null,
    theme_id: "default",
    contacts: [],
    ...overrides,
  } as Storefront;
}

function product(): CatalogProduct {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    name: "Чашка",
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

const props = {
  params: Promise.resolve({ subdomain: "cups" }),
  searchParams: Promise.resolve({}),
};

beforeEach(() => {
  notFound.mockClear();
  permanentRedirect.mockClear();
  vi.mocked(currentSubdomain).mockReset().mockResolvedValue("cups");
  vi.mocked(fetchStorefront).mockReset().mockResolvedValue(storefront());
  vi.mocked(fetchCatalogProducts)
    .mockReset()
    .mockResolvedValue({ items: [product()], total: 1, limit: 24, offset: 0, by_meaning: [] });
});

describe("storefront page", () => {
  it("shows the shop on its own host", async () => {
    render(await StorefrontPage(props));

    expect(screen.getByText("Чашка")).toBeInTheDocument();
    expect(screen.getByTestId("contacts")).toBeInTheDocument();
  });

  it("answers 404 for a shop that does not exist", async () => {
    vi.mocked(fetchStorefront).mockResolvedValue(null);

    await expect(StorefrontPage(props)).rejects.toThrow("not-found");
  });

  it("tells a barred buyer in words, and says the rest of the site still works", async () => {
    vi.mocked(fetchStorefront).mockResolvedValue("store-blocked");

    render(await StorefrontPage(props));

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("ограничил вам доступ");
    expect(screen.getByText(/остальная площадка работает как обычно/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /вернуться в каталог/i })).toHaveAttribute(
      "href",
      "/catalog",
    );
  });

  it("asks for no products at all for a barred buyer", async () => {
    vi.mocked(fetchStorefront).mockResolvedValue("store-blocked");

    render(await StorefrontPage(props));

    expect(fetchCatalogProducts).not.toHaveBeenCalled();
  });

  it("moves a visitor on the marketplace path to the shop's own address", async () => {
    vi.mocked(currentSubdomain).mockResolvedValue(null);

    await expect(StorefrontPage(props)).rejects.toThrow(/redirect/);
    expect(permanentRedirect.mock.calls[0]?.[0]).toContain("cups.");
  });

  it("narrows the catalogue to this one shop", async () => {
    render(await StorefrontPage(props));

    expect(fetchCatalogProducts).toHaveBeenCalledWith(
      expect.objectContaining({ store: "cups", offset: 0 }),
    );
  });

  it("says the products could not be read, which is not the same as none", async () => {
    vi.mocked(fetchCatalogProducts).mockResolvedValue(null);

    render(await StorefrontPage(props));

    expect(screen.getByText(/товары сейчас недоступны/i)).toBeInTheDocument();
  });

  it("says the shop is empty rather than showing nothing", async () => {
    vi.mocked(fetchCatalogProducts).mockResolvedValue({
      items: [],
      total: 0,
      limit: 24,
      offset: 0,
      by_meaning: [],
    });

    render(await StorefrontPage(props));

    expect(screen.getByText("В этом магазине пока нет товаров.")).toBeInTheDocument();
  });
});

describe("what a search engine is told about a shop", () => {
  it("points at the shop's own address", async () => {
    const meta = await generateMetadata(props);

    expect(meta.title).toBe("Лавка кружек");
    expect(meta.alternates?.canonical).toContain("cups.");
  });

  it("describes a shop that said nothing about itself", async () => {
    const meta = await generateMetadata(props);

    expect(meta.description).toBe("Магазин Лавка кружек на AllStore.am");
  });

  it("asks not to be indexed for a shop that does not exist", async () => {
    vi.mocked(fetchStorefront).mockResolvedValue(null);

    const meta = await generateMetadata(props);

    expect(meta.robots).toEqual({ index: false });
  });

  it("asks not to be indexed when the viewer is the one being refused", async () => {
    /* The shop is fine; this visitor is not welcome in it. Letting a crawler index that answer
       would put "access restricted" in search results for a shop that is open. */
    vi.mocked(fetchStorefront).mockResolvedValue("store-blocked");

    const meta = await generateMetadata(props);

    expect(meta.robots).toEqual({ index: false });
  });
});
