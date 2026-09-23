import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  CatalogProduct,
  CatalogProductDetail,
  CatalogStore,
  Contact,
  Storefront,
} from "@/lib/api";

const host = { value: "cups.allstore.am" };

vi.mock("next/headers", () => ({
  headers: () => Promise.resolve(new Headers({ host: host.value })),
}));

vi.mock("@/lib/api", () => ({
  PAGE_SIZE: 24,
  fetchCatalogProduct: vi.fn(),
  fetchCatalogProducts: vi.fn(),
  fetchCatalogStores: vi.fn(),
  fetchStorefront: vi.fn(),
}));

const { fetchCatalogProduct, fetchCatalogProducts, fetchCatalogStores, fetchStorefront } =
  await import("@/lib/api");
const { default: HomePage } = await import("@/app/(public)/page");
const { default: ProductPage } = await import("@/app/(public)/p/[productId]/page");
const { default: StorefrontPage } = await import("@/app/(public)/s/[subdomain]/page");

const PRODUCT: CatalogProduct = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "Кружка керамическая",
  description: "Ручная работа",
  price: "4500.00",
  currency: "AMD",
  availability_status: "in_stock",
  category: { slug: "tableware", name: "Посуда" },
  store: { subdomain: "cups", display_name: "Лавка кружек" },
  images: [],
  created_at: "2026-09-21T00:00:00Z",
};

const PHONE: Contact = {
  platform: "phone",
  value: "+37410123456",
  href: "tel:+37410123456",
};

// what the card endpoint adds on top of the listing: the ways to reach the seller
const PRODUCT_DETAIL: CatalogProductDetail = {
  ...PRODUCT,
  store: { ...PRODUCT.store, contacts: [PHONE] },
};

const STORE: Storefront = {
  subdomain: "cups",
  display_name: "Лавка кружек",
  description: "Керамика ручной работы",
  logo_url: null,
  banner_url: null,
  primary_color: null,
  secondary_color: null,
  theme_id: "default",
  contacts: [],
};

const SHOP: CatalogStore = {
  subdomain: "cups",
  display_name: "Лавка кружек",
  description: "Керамика ручной работы",
  logo_url: null,
  banner_url: null,
  contacts: [],
};

const DRESSED: Storefront = {
  ...STORE,
  logo_url: "https://cdn.example/logo.jpg",
  banner_url: "https://cdn.example/banner.jpg",
  primary_color: "#c4805c",
  secondary_color: "#eed6ba",
  contacts: [PHONE],
};

const productProps = (productId: string) => ({
  params: Promise.resolve({ productId }),
  searchParams: Promise.resolve({}),
});

const storeProps = (subdomain: string) => ({
  params: Promise.resolve({ subdomain }),
  searchParams: Promise.resolve({}),
});

beforeEach(() => {
  host.value = "cups.allstore.am";
  vi.mocked(fetchCatalogProduct).mockReset();
  vi.mocked(fetchCatalogProducts).mockReset();
  vi.mocked(fetchCatalogStores).mockReset();
  vi.mocked(fetchStorefront).mockReset();
});

describe("home page", () => {
  const products = (items: CatalogProduct[]) => ({
    items,
    total: items.length,
    limit: 8,
    offset: 0,
  });
  const stores = (items: CatalogStore[]) => ({ items, total: items.length, limit: 6, offset: 0 });

  beforeEach(() => {
    host.value = "allstore.am";
  });

  it("shows the newest products and the newest shops", async () => {
    vi.mocked(fetchCatalogProducts).mockResolvedValue(products([PRODUCT]));
    vi.mocked(fetchCatalogStores).mockResolvedValue(stores([SHOP]));

    render(await HomePage());

    expect(screen.getByRole("heading", { name: "Новые товары" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Новые магазины" })).toBeInTheDocument();
    // both blocks leave the marketplace for the shop's own subdomain
    expect(screen.getByRole("link", { name: /Кружка керамическая/u })).toHaveAttribute(
      "href",
      `https://cups.allstore.am/p/${PRODUCT.id}`,
    );
    // the shop card is the one naming the address the visitor will land on
    expect(screen.getByRole("link", { name: /cups\.allstore\.am/u })).toHaveAttribute(
      "href",
      "https://cups.allstore.am/",
    );
  });

  it("asks for a block, not for a page of the catalogue", async () => {
    // the blocks are the head of each public listing: nothing on the page picks or caches
    // what to show, so a product taken off the shelf leaves the block with the next render
    vi.mocked(fetchCatalogProducts).mockResolvedValue(products([]));
    vi.mocked(fetchCatalogStores).mockResolvedValue(stores([]));

    render(await HomePage());

    expect(fetchCatalogProducts).toHaveBeenCalledWith(
      { q: null, category: null, store: null, offset: 0 },
      8,
    );
    expect(fetchCatalogStores).toHaveBeenCalledWith(0, 6);
  });

  it("drops a block it has nothing to fill with", async () => {
    // nothing published yet, everything hidden, every shop suspended — the listings answer
    // empty and the page must not show an empty shelf
    vi.mocked(fetchCatalogProducts).mockResolvedValue(products([]));
    vi.mocked(fetchCatalogStores).mockResolvedValue(stores([]));

    render(await HomePage());

    expect(screen.queryByRole("heading", { name: "Новые товары" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Новые магазины" })).not.toBeInTheDocument();
  });

  it("stands even when the catalogue cannot be read", async () => {
    vi.mocked(fetchCatalogProducts).mockResolvedValue(null);
    vi.mocked(fetchCatalogStores).mockResolvedValue(null);

    render(await HomePage());

    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });
});

describe("product page", () => {
  it("renders on the subdomain of the shop that sells it", async () => {
    vi.mocked(fetchCatalogProduct).mockResolvedValue(PRODUCT_DETAIL);

    render(await ProductPage(productProps(PRODUCT.id)));

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Кружка керамическая");
    // the shop is where the visitor already is, so the link home stays relative
    expect(screen.getAllByRole("link", { name: "Лавка кружек" })[0]).toHaveAttribute("href", "/");
  });

  it("moves the visitor into the shop when opened on the marketplace", async () => {
    host.value = "allstore.am";
    vi.mocked(fetchCatalogProduct).mockResolvedValue(PRODUCT_DETAIL);

    await expect(ProductPage(productProps(PRODUCT.id))).rejects.toThrow();
  });

  it("is not found when the backend does not hand the product over", async () => {
    // pending, rejected, hidden, archived and plain missing all arrive here as null
    vi.mocked(fetchCatalogProduct).mockResolvedValue(null);

    await expect(ProductPage(productProps(PRODUCT.id))).rejects.toThrow();
  });

  it("gives the buyer a way to reach the seller", async () => {
    // there is no cart in the MVP, so this link is the whole of the transaction
    vi.mocked(fetchCatalogProduct).mockResolvedValue(PRODUCT_DETAIL);
    vi.mocked(fetchStorefront).mockResolvedValue(STORE);

    render(await ProductPage(productProps(PRODUCT.id)));

    expect(screen.getByRole("link", { name: /Телефон/u })).toHaveAttribute(
      "href",
      "tel:+37410123456",
    );
  });

  it("wears the shop it is sold in", async () => {
    vi.mocked(fetchCatalogProduct).mockResolvedValue(PRODUCT_DETAIL);
    vi.mocked(fetchStorefront).mockResolvedValue(DRESSED);

    const { container } = render(await ProductPage(productProps(PRODUCT.id)));

    expect(container.querySelector('img[src="https://cdn.example/logo.jpg"]')).toBeInTheDocument();
    expect(container.querySelector("[style*='--color-brand']")).toBeInTheDocument();
  });

  it("still renders when the storefront cannot be read", async () => {
    // the product is the page; its shop's colours are decoration and may be missing
    vi.mocked(fetchCatalogProduct).mockResolvedValue(PRODUCT_DETAIL);
    vi.mocked(fetchStorefront).mockResolvedValue(null);

    render(await ProductPage(productProps(PRODUCT.id)));

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Кружка керамическая");
  });
});

describe("storefront page", () => {
  it("renders the shop and its products", async () => {
    vi.mocked(fetchStorefront).mockResolvedValue(STORE);
    vi.mocked(fetchCatalogProducts).mockResolvedValue({
      items: [PRODUCT],
      total: 1,
      limit: 24,
      offset: 0,
    });

    render(await StorefrontPage(storeProps("cups")));

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Лавка кружек");
    // inside its own shop a product card does not leave the host
    expect(screen.getByRole("link", { name: /Кружка керамическая/u })).toHaveAttribute(
      "href",
      `/p/${PRODUCT.id}`,
    );
  });

  it("says so when the shop has nothing on the shelf yet", async () => {
    vi.mocked(fetchStorefront).mockResolvedValue(STORE);
    vi.mocked(fetchCatalogProducts).mockResolvedValue({
      items: [],
      total: 0,
      limit: 24,
      offset: 0,
    });

    render(await StorefrontPage(storeProps("cups")));

    expect(screen.getByText("В этом магазине пока нет товаров.")).toBeInTheDocument();
  });

  it("moves the visitor onto the subdomain when opened by path", async () => {
    host.value = "allstore.am";
    vi.mocked(fetchStorefront).mockResolvedValue(STORE);

    await expect(StorefrontPage(storeProps("cups"))).rejects.toThrow();
  });

  it("is not found when the shop is not on the air", async () => {
    // a draft, a suspended and a blocked shop all arrive here as null
    vi.mocked(fetchStorefront).mockResolvedValue(null);

    await expect(StorefrontPage(storeProps("cups"))).rejects.toThrow();
  });

  it("shows what the seller dressed it in", async () => {
    vi.mocked(fetchStorefront).mockResolvedValue(DRESSED);
    vi.mocked(fetchCatalogProducts).mockResolvedValue({
      items: [],
      total: 0,
      limit: 24,
      offset: 0,
    });

    const { container } = render(await StorefrontPage(storeProps("cups")));

    expect(container.querySelector('img[src="https://cdn.example/logo.jpg"]')).toBeInTheDocument();
    expect(
      container.querySelector('img[src="https://cdn.example/banner.jpg"]'),
    ).toBeInTheDocument();
    expect(screen.getByText("Керамика ручной работы")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Телефон/u })).toHaveAttribute(
      "href",
      "tel:+37410123456",
    );
  });

  it("paints its own colours over the shared skeleton", async () => {
    vi.mocked(fetchStorefront).mockResolvedValue(DRESSED);
    vi.mocked(fetchCatalogProducts).mockResolvedValue({
      items: [],
      total: 0,
      limit: 24,
      offset: 0,
    });

    const { container } = render(await StorefrontPage(storeProps("cups")));

    const painted = container.querySelector("[style*='--color-brand']");
    expect(painted).toHaveStyle({ "--color-brand": "#c4805c" });
    expect(painted).toHaveStyle({ "--color-brand-dark": "#eed6ba" });
  });

  it("inherits the platform look when the seller chose nothing", async () => {
    vi.mocked(fetchStorefront).mockResolvedValue(STORE);
    vi.mocked(fetchCatalogProducts).mockResolvedValue({
      items: [],
      total: 0,
      limit: 24,
      offset: 0,
    });

    const { container } = render(await StorefrontPage(storeProps("cups")));

    expect(container.querySelector("[style*='--color-brand']")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });
});
