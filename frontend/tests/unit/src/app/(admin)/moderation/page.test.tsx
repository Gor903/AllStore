import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { BusinessList, ModerationProductList } from "@/lib/api";

/**
 * The queue of products waiting to be judged.
 *
 * It holds two kinds of work that look alike in a list: a product waiting for its first look,
 * and an edit to one that is already on a shelf. Refusing the first keeps a shelf empty;
 * refusing the second takes away nothing the seller had, and the buyer goes on seeing the
 * approved version. The queue says which it is looking at, and shows what the buyer currently
 * sees beside what is proposed — a moderator judging an edit without that is judging blind.
 *
 * The counters in the navigation come from the other queues, and a queue that could not be read
 * counts as zero rather than taking the page down with it.
 */

vi.mock("@/lib/dal", () => ({
  ADMIN_PAGE_SIZE: 20,
  requireRole: vi.fn(),
  getModerationProducts: vi.fn(),
  getModerationBusinesses: vi.fn(),
}));

vi.mock("@/components/moderation/ModerationNav", () => ({
  ModerationNav: ({ products, businesses }: { products: number; businesses: number }) => (
    <header data-testid="nav" data-products={products} data-businesses={businesses} />
  ),
}));

vi.mock("@/components/moderation/VerdictButtons", () => ({
  VerdictButtons: ({ basePath }: { basePath: string }) => (
    <div data-testid="verdicts" data-base={basePath} />
  ),
}));

const { requireRole, getModerationProducts, getModerationBusinesses } = await import("@/lib/dal");
const { default: ModerationProductsPage } = await import("@/app/(admin)/moderation/page");

const PRODUCT = "11111111-1111-1111-1111-111111111111";

function queued(overrides: Record<string, unknown> = {}) {
  return {
    id: PRODUCT,
    name: "Чашка",
    description: "Фарфор",
    price: "1500.00",
    currency: "AMD",
    stock_quantity: 3,
    category_name: "Посуда",
    seller_name: "Ромашка",
    subdomain: "cups",
    proposed: null,
    is_change: false,
    images: [],
    ...overrides,
  };
}

function page(items: unknown[], total = items.length): ModerationProductList {
  return { items, total, limit: 20, offset: 0 } as unknown as ModerationProductList;
}

const props = { params: Promise.resolve({}), searchParams: Promise.resolve({}) };

beforeEach(() => {
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue({ id: "1", role: "moderator" } as never);
  vi.mocked(getModerationProducts)
    .mockReset()
    .mockResolvedValue(page([queued()]));
  vi.mocked(getModerationBusinesses)
    .mockReset()
    .mockResolvedValue({ items: [], total: 4, limit: 20, offset: 0 } as unknown as BusinessList);
});

describe("the product queue", () => {
  it("is open to a moderator and to the administrator", async () => {
    render(await ModerationProductsPage(props));

    expect(requireRole).toHaveBeenCalledWith("moderator", "admin");
  });

  it("shows what is waiting, and who it is from", async () => {
    render(await ModerationProductsPage(props));

    expect(screen.getByRole("heading", { name: "Чашка" })).toBeInTheDocument();
    expect(screen.getByText(/Ромашка/)).toBeInTheDocument();
    expect(screen.getByTestId("verdicts")).toHaveAttribute(
      "data-base",
      `/moderation/products/${PRODUCT}`,
    );
  });

  it("says the queue is empty rather than that it broke", async () => {
    vi.mocked(getModerationProducts).mockResolvedValue(page([]));

    render(await ModerationProductsPage(props));

    expect(screen.getByText(/очередь пуста/i)).toBeInTheDocument();
  });

  it("says the queue could not be read when it could not", async () => {
    vi.mocked(getModerationProducts).mockResolvedValue(null);

    render(await ModerationProductsPage(props));

    expect(screen.getByText(/очередь сейчас недоступна/i)).toBeInTheDocument();
  });

  it("counts the other queue in the navigation, and zero for one it cannot read", async () => {
    render(await ModerationProductsPage(props));
    expect(screen.getByTestId("nav")).toHaveAttribute("data-businesses", "4");

    vi.mocked(getModerationBusinesses).mockResolvedValue(null);
    render(await ModerationProductsPage(props));

    expect(screen.getAllByTestId("nav")[1]).toHaveAttribute("data-businesses", "0");
  });

  it("marks an edit to a live listing as a different decision", async () => {
    vi.mocked(getModerationProducts).mockResolvedValue(
      page([
        queued({
          is_change: true,
          proposed: { name: "Чашка с блюдцем", description: null, category_name: "Посуда" },
        }),
      ]),
    );

    render(await ModerationProductsPage(props));

    expect(screen.getByText(/правка уже опубликованного товара/i)).toBeInTheDocument();
    expect(screen.getByText(/товар с полки не уйдёт/i)).toBeInTheDocument();
  });

  it("shows what is proposed beside what the buyer sees now", async () => {
    vi.mocked(getModerationProducts).mockResolvedValue(
      page([
        queued({
          is_change: true,
          proposed: { name: "Чашка с блюдцем", description: null, category_name: "Посуда" },
        }),
      ]),
    );

    render(await ModerationProductsPage(props));

    expect(screen.getByRole("heading", { name: /Чашка с блюдцем/ })).toBeInTheDocument();
    expect(screen.getByText(/Покупатель сейчас видит/)).toBeInTheDocument();
  });

  it("says a product has no description rather than leaving a gap", async () => {
    vi.mocked(getModerationProducts).mockResolvedValue(page([queued({ description: null })]));

    render(await ModerationProductsPage(props));

    expect(screen.getByText("Описания нет.")).toBeInTheDocument();
  });

  it("says a seller has no storefront, which is a thing worth knowing here", async () => {
    vi.mocked(getModerationProducts).mockResolvedValue(page([queued({ subdomain: null })]));

    render(await ModerationProductsPage(props));

    expect(screen.getByText(/без витрины/)).toBeInTheDocument();
  });

  it("is a page without a photograph rather than a hole where one would be", async () => {
    render(await ModerationProductsPage(props));

    expect(screen.getByText("Без фото")).toBeInTheDocument();
  });
});
