import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CategoryTree, Product, Store } from "@/lib/api";

/**
 * One product, as its own seller edits it.
 *
 * A product belonging to another seller reads exactly as one that does not exist — anything else
 * would let somebody walk the identifiers and learn what other shops are preparing.
 *
 * The reference book of categories can be unreachable, and when it is, the page says so and goes
 * on working: the photographs and the shelf actions do not need it, and taking the whole screen
 * away would mean a seller cannot remove a wrong photograph because a lookup table is down.
 */

const notFound = vi.fn(() => {
  throw new Error("not-found");
});

vi.mock("next/navigation", () => ({ notFound: () => notFound() }));

vi.mock("@/lib/api", () => ({ fetchCategories: vi.fn() }));

vi.mock("@/lib/dal", () => ({
  requireRole: vi.fn(),
  getMyProduct: vi.fn(),
  getMyStore: vi.fn(),
}));

vi.mock("@/components/dashboard/ProductActions", () => ({
  ProductActions: () => <div data-testid="actions" />,
}));

vi.mock("@/components/dashboard/ImageManager", () => ({
  ImageManager: ({ max }: { max: number }) => <div data-testid="images">{max}</div>,
}));

vi.mock("@/components/dashboard/ProductForm", () => ({
  ProductForm: () => <form data-testid="product-form" />,
}));

const { fetchCategories } = await import("@/lib/api");
const { requireRole, getMyProduct, getMyStore } = await import("@/lib/dal");
const { default: EditProductPage } =
  await import("@/app/(dashboard)/dashboard/products/[productId]/page");

const PRODUCT = "11111111-1111-1111-1111-111111111111";

function product(overrides: Partial<Product> = {}): Product {
  return {
    id: PRODUCT,
    name: "Чашка",
    description: null,
    price: "1500.00",
    currency: "AMD",
    stock_quantity: 1,
    availability_status: "in_stock",
    moderation_status: "approved",
    publication_status: "published",
    rejection_reason: null,
    pending_change: null,
    change_rejection_reason: null,
    images: [],
    created_at: "2026-11-13T00:00:00Z",
    updated_at: "2026-11-13T00:00:00Z",
    ...overrides,
  } as Product;
}

function store(): Store {
  return { id: "s", subdomain: "cups", status: "active" } as Store;
}

const props = {
  params: Promise.resolve({ productId: PRODUCT }),
  searchParams: Promise.resolve({}),
};

beforeEach(() => {
  notFound.mockClear();
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue({ id: "1" } as never);
  vi.mocked(getMyProduct).mockReset().mockResolvedValue(product());
  vi.mocked(getMyStore).mockReset().mockResolvedValue(store());
  vi.mocked(fetchCategories)
    .mockReset()
    .mockResolvedValue([
      { id: "c", slug: "dishes", name: "Посуда", children: [] },
    ] as CategoryTree[]);
});

describe("product edit page", () => {
  it("is a seller's screen and nobody else's", async () => {
    render(await EditProductPage(props));

    expect(requireRole).toHaveBeenCalledWith("seller");
  });

  it("shows the product, where it stands and what to do about it", async () => {
    vi.mocked(getMyProduct).mockResolvedValue(product({ moderation_status: "pending" }));

    render(await EditProductPage(props));

    expect(screen.getByRole("heading", { name: "Чашка", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("На проверке")).toBeInTheDocument();
    expect(screen.getByText(/модератор скоро посмотрит/i)).toBeInTheDocument();
  });

  it("answers as if it did not exist when it is somebody else's", async () => {
    vi.mocked(getMyProduct).mockResolvedValue(null);

    await expect(EditProductPage(props)).rejects.toThrow("not-found");
  });

  it("offers a look at the live listing once there is one", async () => {
    render(await EditProductPage(props));

    const link = screen.getByRole("link", { name: /открыть в магазине/i });
    expect(link.getAttribute("href")).toContain("cups.");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });

  it("offers no such link while the product is not on a shelf", async () => {
    vi.mocked(getMyProduct).mockResolvedValue(product({ publication_status: "draft" }));

    render(await EditProductPage(props));

    expect(screen.queryByRole("link", { name: /открыть в магазине/i })).not.toBeInTheDocument();
  });

  it("offers none either when the shop itself could not be read", async () => {
    vi.mocked(getMyStore).mockResolvedValue(null);

    render(await EditProductPage(props));

    expect(screen.queryByRole("link", { name: /открыть в магазине/i })).not.toBeInTheDocument();
  });

  it("carries the ceiling the backend enforces into the gallery", async () => {
    render(await EditProductPage(props));

    expect(screen.getByTestId("images")).toHaveTextContent("10");
  });

  it("says a change goes to the queue and the listing stays as it was", async () => {
    render(await EditProductPage(props));

    expect(screen.getByText(/уходит на проверку/i)).toBeInTheDocument();
    expect(screen.getByText(/цена и остаток меняются\s+сразу/i)).toBeInTheDocument();
  });

  it("keeps the photographs and the shelf working without the reference book", async () => {
    vi.mocked(fetchCategories).mockResolvedValue(null);

    render(await EditProductPage(props));

    expect(screen.getByText(/справочник категорий сейчас недоступен/i)).toBeInTheDocument();
    expect(screen.queryByTestId("product-form")).not.toBeInTheDocument();
    expect(screen.getByTestId("images")).toBeInTheDocument();
    expect(screen.getByTestId("actions")).toBeInTheDocument();
  });

  it("offers the way back to the cabinet", async () => {
    render(await EditProductPage(props));

    expect(screen.getByRole("link", { name: "Кабинет" })).toHaveAttribute("href", "/dashboard");
  });
});
