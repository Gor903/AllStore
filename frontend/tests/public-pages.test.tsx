import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CatalogProduct, Storefront } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  PAGE_SIZE: 24,
  fetchCatalogProduct: vi.fn(),
  fetchCatalogProducts: vi.fn(),
  fetchStorefront: vi.fn(),
}));

const { fetchCatalogProduct, fetchCatalogProducts, fetchStorefront } = await import("@/lib/api");
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

const STORE: Storefront = {
  subdomain: "cups",
  display_name: "Лавка кружек",
  description: "Керамика ручной работы",
  logo_url: null,
  banner_url: null,
  primary_color: null,
  secondary_color: null,
  theme_id: "default",
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
  vi.mocked(fetchCatalogProduct).mockReset();
  vi.mocked(fetchCatalogProducts).mockReset();
  vi.mocked(fetchStorefront).mockReset();
});

describe("product page", () => {
  it("renders the product on the server", async () => {
    vi.mocked(fetchCatalogProduct).mockResolvedValue(PRODUCT);

    render(await ProductPage(productProps(PRODUCT.id)));

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Кружка керамическая");
    expect(screen.getByRole("link", { name: "Лавка кружек" })).toHaveAttribute("href", "/s/cups");
  });

  it("is not found when the backend does not hand the product over", async () => {
    // pending, rejected, hidden, archived and plain missing all arrive here as null
    vi.mocked(fetchCatalogProduct).mockResolvedValue(null);

    await expect(ProductPage(productProps(PRODUCT.id))).rejects.toThrow();
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
    expect(screen.getByText("Кружка керамическая")).toBeInTheDocument();
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

  it("is not found when the shop is not on the air", async () => {
    // a draft, a suspended and a blocked shop all arrive here as null
    vi.mocked(fetchStorefront).mockResolvedValue(null);

    await expect(StorefrontPage(storeProps("cups"))).rejects.toThrow();
  });
});
