import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ReportQueue } from "@/lib/api";

/**
 * The complaints queue.
 *
 * One line is one subject, even when ten people complained about it, and one verdict closes all
 * of them — twenty complaints about one product are one piece of work, and treating them as
 * twenty would mean a moderator deciding the same thing twenty times.
 *
 * A complaint about a shop and one about a product are routed differently and offer different
 * verdicts: a shop is suspended, a product comes off the shelf. Getting the two the wrong way
 * round would address a resolution to an identifier that is not there.
 */

vi.mock("@/lib/dal", () => ({
  ADMIN_PAGE_SIZE: 20,
  requireRole: vi.fn(),
  getReportQueue: vi.fn(),
  getModerationProducts: vi.fn(),
  getModerationBusinesses: vi.fn(),
}));

vi.mock("@/components/moderation/ModerationNav", () => ({
  ModerationNav: ({ reports }: { reports: number }) => (
    <header data-testid="nav" data-reports={reports} />
  ),
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

const { requireRole, getReportQueue, getModerationProducts, getModerationBusinesses } =
  await import("@/lib/dal");
const { default: ReportsPage } = await import("@/app/(admin)/moderation/reports/page");

const PRODUCT = "11111111-1111-1111-1111-111111111111";
const BUSINESS = "22222222-2222-2222-2222-222222222222";

function aboutProduct() {
  return {
    product: {
      id: PRODUCT,
      name: "Чашка",
      seller_name: "Ромашка",
      category_name: "Посуда",
      price: "1500.00",
      currency: "AMD",
      images: [],
    },
    shop: null,
    business_id: null,
    total: 3,
    last_at: "2026-11-13T00:00:00Z",
    reasons: ["Фото чужое", "Цена не та"],
  };
}

function aboutShop() {
  return {
    product: null,
    shop: { display_name: "Ромашка", subdomain: "cups" },
    business_id: BUSINESS,
    total: 1,
    last_at: "2026-11-13T00:00:00Z",
    reasons: ["Берут деньги мимо площадки"],
  };
}

function page(items: unknown[]): ReportQueue {
  return { items, total: items.length, limit: 20, offset: 0 } as unknown as ReportQueue;
}

const props = { params: Promise.resolve({}), searchParams: Promise.resolve({}) };

beforeEach(() => {
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue({ id: "1", role: "moderator" } as never);
  vi.mocked(getReportQueue)
    .mockReset()
    .mockResolvedValue(page([aboutProduct()]));
  vi.mocked(getModerationProducts)
    .mockReset()
    .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 } as never);
  vi.mocked(getModerationBusinesses)
    .mockReset()
    .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 } as never);
});

describe("the complaints queue", () => {
  it("is open to a moderator and to the administrator", async () => {
    render(await ReportsPage(props));

    expect(requireRole).toHaveBeenCalledWith("moderator", "admin");
  });

  it("says one line is one subject and one verdict closes all of them", async () => {
    render(await ReportsPage(props));

    expect(screen.getByText(/одна строка — один предмет/i)).toBeInTheDocument();
  });

  it("shows how many complained and what each of them said", async () => {
    render(await ReportsPage(props));

    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("«Фото чужое»")).toBeInTheDocument();
    expect(screen.getByText("«Цена не та»")).toBeInTheDocument();
  });

  it("offers to take a product off the shelf, addressed to the product", async () => {
    render(await ReportsPage(props));

    const verdicts = screen.getByTestId("verdicts");
    expect(verdicts).toHaveAttribute("data-base", `/moderation/reports/product/${PRODUCT}`);
    expect(verdicts).toHaveTextContent("Снять товар с полки");
  });

  it("offers to suspend a shop, addressed to the business", async () => {
    vi.mocked(getReportQueue).mockResolvedValue(page([aboutShop()]));

    render(await ReportsPage(props));

    const verdicts = screen.getByTestId("verdicts");
    expect(verdicts).toHaveAttribute("data-base", `/moderation/reports/business/${BUSINESS}`);
    expect(verdicts).toHaveTextContent("Приостановить магазин");
  });

  it("always offers to dismiss the complaint as well", async () => {
    render(await ReportsPage(props));

    expect(screen.getByTestId("verdicts")).toHaveTextContent("Отклонить жалобу");
  });

  it("names the shop a complaint is about", async () => {
    vi.mocked(getReportQueue).mockResolvedValue(page([aboutShop()]));

    render(await ReportsPage(props));

    expect(screen.getByText("Магазин: Ромашка")).toBeInTheDocument();
    expect(screen.getByText("cups")).toBeInTheDocument();
  });

  it("says there are no complaints rather than that the queue broke", async () => {
    vi.mocked(getReportQueue).mockResolvedValue(page([]));

    render(await ReportsPage(props));

    expect(screen.getByText("Жалоб нет.")).toBeInTheDocument();
  });

  it("says the queue could not be read when it could not", async () => {
    vi.mocked(getReportQueue).mockResolvedValue(null);

    render(await ReportsPage(props));

    expect(screen.getByText(/очередь сейчас недоступна/i)).toBeInTheDocument();
  });

  it("counts itself in the navigation, so the other queues show the badge too", async () => {
    render(await ReportsPage(props));

    expect(screen.getByTestId("nav")).toHaveAttribute("data-reports", "1");
  });
});
