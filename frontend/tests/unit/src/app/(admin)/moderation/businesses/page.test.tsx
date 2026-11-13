import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { BusinessList, ModerationProductList } from "@/lib/api";
import { env } from "@/lib/env";

/**
 * The queue of sellers waiting to be let in.
 *
 * The screen says what is at stake, because the three verdicts mean very different things: until
 * a seller is admitted their shop is invisible and their products stay unpublished even when
 * approved one by one; a refusal is not a ban, and they will read the reason and apply again; a
 * block closes the road.
 *
 * An applicant who has already been looked at is a different case from one nobody has seen, so
 * the history travels with the row — out of the way, but not out of sight.
 */

vi.mock("@/lib/dal", () => ({
  ADMIN_PAGE_SIZE: 20,
  requireRole: vi.fn(),
  getModerationBusinesses: vi.fn(),
  getModerationProducts: vi.fn(),
}));

vi.mock("@/components/moderation/ModerationNav", () => ({
  ModerationNav: ({ products }: { products: number }) => (
    <header data-testid="nav" data-products={products} />
  ),
}));

vi.mock("@/components/moderation/VerdictButtons", () => ({
  VerdictButtons: ({ basePath }: { basePath: string }) => (
    <div data-testid="verdicts" data-base={basePath} />
  ),
}));

const { requireRole, getModerationBusinesses, getModerationProducts } = await import("@/lib/dal");
const { default: ModerationBusinessesPage } =
  await import("@/app/(admin)/moderation/businesses/page");

const BUSINESS = "11111111-1111-1111-1111-111111111111";

function applicant(overrides: Record<string, unknown> = {}) {
  return {
    id: BUSINESS,
    legal_name: "ООО Ромашка",
    display_name: "Ромашка",
    description: null,
    status: "pending",
    subdomain: "cups",
    store_status: "pending",
    created_at: "2026-11-13T00:00:00Z",
    history: [],
    ...overrides,
  };
}

function page(items: unknown[]): BusinessList {
  return { items, total: items.length, limit: 20, offset: 0 } as unknown as BusinessList;
}

const props = { params: Promise.resolve({}), searchParams: Promise.resolve({}) };

beforeEach(() => {
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue({ id: "1", role: "moderator" } as never);
  vi.mocked(getModerationBusinesses)
    .mockReset()
    .mockResolvedValue(page([applicant()]));
  vi.mocked(getModerationProducts)
    .mockReset()
    .mockResolvedValue({
      items: [],
      total: 7,
      limit: 20,
      offset: 0,
    } as unknown as ModerationProductList);
});

describe("the sellers queue", () => {
  it("is open to a moderator and to the administrator", async () => {
    render(await ModerationBusinessesPage(props));

    expect(requireRole).toHaveBeenCalledWith("moderator", "admin");
  });

  it("says what the three verdicts actually do", async () => {
    render(await ModerationBusinessesPage(props));

    expect(screen.getByText(/магазин никому не виден/i)).toBeInTheDocument();
    expect(screen.getByText(/отклонение — не бан/i)).toBeInTheDocument();
    expect(screen.getByText(/блокировка закрывает дорогу совсем/i)).toBeInTheDocument();
  });

  it("shows who is applying, under both their names", async () => {
    render(await ModerationBusinessesPage(props));

    expect(screen.getByRole("heading", { name: "Ромашка" })).toBeInTheDocument();
    expect(screen.getByText("ООО Ромашка")).toBeInTheDocument();
    expect(screen.getByTestId("verdicts")).toHaveAttribute(
      "data-base",
      `/moderation/businesses/${BUSINESS}`,
    );
  });

  it("shows the address their shop would answer at", async () => {
    render(await ModerationBusinessesPage(props));

    expect(screen.getByText(`Адрес: cups.${env.baseDomain}`)).toBeInTheDocument();
  });

  it("says when there is no storefront yet, which is not a reason to refuse", async () => {
    vi.mocked(getModerationBusinesses).mockResolvedValue(page([applicant({ subdomain: null })]));

    render(await ModerationBusinessesPage(props));

    expect(screen.getByText("Витрину ещё не создал")).toBeInTheDocument();
  });

  it("carries the history of an applicant who has been looked at before", async () => {
    vi.mocked(getModerationBusinesses).mockResolvedValue(
      page([
        applicant({
          history: [
            { decision: "rejected", reason: "Нет документов", created_at: "2026-11-01T00:00:00Z" },
          ],
        }),
      ]),
    );

    render(await ModerationBusinessesPage(props));

    expect(screen.getByText(/эту заявку уже смотрели \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Нет документов/)).toBeInTheDocument();
  });

  it("says nothing about a history nobody has yet", async () => {
    render(await ModerationBusinessesPage(props));

    expect(screen.queryByText(/уже смотрели/i)).not.toBeInTheDocument();
  });

  it("says the queue is empty rather than that it broke", async () => {
    vi.mocked(getModerationBusinesses).mockResolvedValue(page([]));

    render(await ModerationBusinessesPage(props));

    expect(screen.getByText(/заявок нет/i)).toBeInTheDocument();
  });

  it("says the queue could not be read when it could not", async () => {
    vi.mocked(getModerationBusinesses).mockResolvedValue(null);

    render(await ModerationBusinessesPage(props));

    expect(screen.getByText(/очередь сейчас недоступна/i)).toBeInTheDocument();
  });

  it("counts the other queue in the navigation", async () => {
    render(await ModerationBusinessesPage(props));

    expect(screen.getByTestId("nav")).toHaveAttribute("data-products", "7");
  });
});
