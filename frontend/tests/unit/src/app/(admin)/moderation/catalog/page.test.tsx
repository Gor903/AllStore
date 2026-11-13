import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ModerationProductList } from "@/lib/api";

/**
 * Searching the whole catalogue, in any state.
 *
 * The queue holds only what is waiting to be judged; this is where a moderator finds a product
 * that was complained about after it was published. An empty query shows nothing at all rather
 * than everything — the backend refuses an empty search, and a page that showed the whole
 * catalogue by default would be a page nobody can act on.
 *
 * The verdict offered depends on where the product stands: one already hidden can be put back,
 * and one on the shelf can be taken off it. Offering both would let a moderator publish a
 * product that is already published and wonder why nothing happened.
 */

vi.mock("@/lib/dal", () => ({
  ADMIN_PAGE_SIZE: 20,
  requireRole: vi.fn(),
  searchModerationCatalog: vi.fn(),
  getModerationProducts: vi.fn(),
  getModerationBusinesses: vi.fn(),
}));

vi.mock("@/components/moderation/ModerationNav", () => ({
  ModerationNav: () => <header data-testid="nav" />,
}));

vi.mock("@/components/moderation/VerdictButtons", () => ({
  VerdictButtons: ({ basePath, verdicts }: { basePath: string; verdicts: { label: string }[] }) => (
    <div data-testid="verdicts" data-base={basePath}>
      {verdicts.map((verdict) => (
        <span key={verdict.label}>{verdict.label}</span>
      ))}
    </div>
  ),
}));

const { requireRole, searchModerationCatalog, getModerationProducts, getModerationBusinesses } =
  await import("@/lib/dal");
const { default: ModerationCatalogPage } = await import("@/app/(admin)/moderation/catalog/page");

const PRODUCT = "11111111-1111-1111-1111-111111111111";

function found(publication: string) {
  return {
    id: PRODUCT,
    name: "Чашка",
    seller_name: "Ромашка",
    category_name: "Посуда",
    subdomain: "cups",
    price: "1500.00",
    currency: "AMD",
    publication_status: publication,
    moderation_status: "approved",
    stock_quantity: 1,
    description: null,
    proposed: null,
    is_change: false,
    images: [],
  };
}

function page(items: unknown[]): ModerationProductList {
  return { items, total: items.length, limit: 20, offset: 0 } as unknown as ModerationProductList;
}

const props = (q?: string) => ({
  params: Promise.resolve({}),
  searchParams: Promise.resolve(q === undefined ? {} : { q }),
});

beforeEach(() => {
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue({ id: "1", role: "moderator" } as never);
  vi.mocked(searchModerationCatalog)
    .mockReset()
    .mockResolvedValue(page([found("published")]));
  vi.mocked(getModerationProducts)
    .mockReset()
    .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 } as never);
  vi.mocked(getModerationBusinesses)
    .mockReset()
    .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 } as never);
});

describe("the catalogue search", () => {
  it("is open to a moderator and to the administrator", async () => {
    render(await ModerationCatalogPage(props("чашка")));

    expect(requireRole).toHaveBeenCalledWith("moderator", "admin");
  });

  it("says what this screen is for that the queue is not", async () => {
    render(await ModerationCatalogPage(props("чашка")));

    expect(screen.getByText(/очередь держит только то, что ждёт проверки/i)).toBeInTheDocument();
  });

  it("searches for what was typed", async () => {
    render(await ModerationCatalogPage(props("чашка")));

    expect(searchModerationCatalog).toHaveBeenCalledWith("чашка", 0);
    expect(screen.getByDisplayValue("чашка")).toBeInTheDocument();
  });

  it("shows nothing at all until something is asked for", async () => {
    vi.mocked(searchModerationCatalog).mockResolvedValue(page([]));

    render(await ModerationCatalogPage(props()));

    expect(screen.queryByText("Ничего не нашлось.")).not.toBeInTheDocument();
    expect(screen.queryByTestId("verdicts")).not.toBeInTheDocument();
  });

  it("says nothing was found when a search found nothing", async () => {
    vi.mocked(searchModerationCatalog).mockResolvedValue(page([]));

    render(await ModerationCatalogPage(props("чашка")));

    expect(screen.getByText("Ничего не нашлось.")).toBeInTheDocument();
  });

  it("says the search could not be run when it could not", async () => {
    vi.mocked(searchModerationCatalog).mockResolvedValue(null);

    render(await ModerationCatalogPage(props("чашка")));

    expect(screen.getByText(/поиск сейчас недоступен/i)).toBeInTheDocument();
  });

  it("offers to take a published product off the shelf", async () => {
    render(await ModerationCatalogPage(props("чашка")));

    const verdicts = screen.getByTestId("verdicts");
    expect(verdicts).toHaveAttribute("data-base", `/moderation/products/${PRODUCT}`);
    expect(verdicts.textContent).toMatch(/снять|скрыть/i);
  });

  it("offers to bring a hidden one back instead", async () => {
    vi.mocked(searchModerationCatalog).mockResolvedValue(page([found("hidden")]));

    render(await ModerationCatalogPage(props("чашка")));

    expect(screen.getByTestId("verdicts").textContent).toMatch(/верн|опублик/i);
  });

  it("offers nothing to decide about a product nobody has approved yet", async () => {
    vi.mocked(searchModerationCatalog).mockResolvedValue(page([found("draft")]));

    render(await ModerationCatalogPage(props("чашка")));

    expect(screen.queryByTestId("verdicts")).not.toBeInTheDocument();
  });

  it("names the search box without a visible label", async () => {
    render(await ModerationCatalogPage(props("чашка")));

    expect(screen.getByLabelText("Поиск по каталогу")).toBeInTheDocument();
  });
});
