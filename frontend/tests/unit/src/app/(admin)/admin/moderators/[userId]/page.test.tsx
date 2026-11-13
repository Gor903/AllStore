import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AuditLogList, ModeratorRecord, User } from "@/lib/api";

/**
 * What one moderator has decided with their role.
 *
 * The figures are counted from the decisions themselves rather than from a counter kept beside
 * them: a separate counter can drift, and here it would be read as proof. The page says so,
 * because a number on a page about somebody's conduct has to be one they could defend.
 *
 * The counts say how much and the feed says what exactly, which is why both are here and why a
 * journal that could not be read says so rather than showing an empty list.
 */

const notFound = vi.fn(() => {
  throw new Error("not-found");
});

vi.mock("next/navigation", () => ({ notFound: () => notFound() }));

vi.mock("@/lib/dal", () => ({
  requireRole: vi.fn(),
  getModeratorRecord: vi.fn(),
  getAuditLogs: vi.fn(),
}));

vi.mock("@/components/admin/AdminNav", () => ({
  AdminNav: () => <header data-testid="nav" />,
}));

vi.mock("@/components/moderation/AccountRows", () => ({
  AccountRows: ({ items }: { items: User[] }) => <ul data-testid="rows">{items.length}</ul>,
}));

const { requireRole, getModeratorRecord, getAuditLogs } = await import("@/lib/dal");
const { default: ModeratorPage } = await import("@/app/(admin)/admin/moderators/[userId]/page");

const MODERATOR = "m1";

function record(): ModeratorRecord {
  return {
    moderator: { id: MODERATOR, email: "moderator@allstore.am", role: "moderator" },
    products_approved: 12,
    products_rejected: 3,
    businesses_approved: 4,
    businesses_refused: 1,
    accounts_blocked: 2,
  } as unknown as ModeratorRecord;
}

function journal(count: number, total = count): AuditLogList {
  return {
    items: Array.from({ length: count }, (_, index) => ({
      id: `e${index}`,
      action: "product.approved",
      entity_type: "product",
      entity_id: null,
      details: {},
      created_at: "2026-11-13T10:00:00Z",
      actor_email: "moderator@allstore.am",
    })),
    total,
    limit: 20,
    offset: 0,
  } as unknown as AuditLogList;
}

const props = {
  params: Promise.resolve({ userId: MODERATOR }),
  searchParams: Promise.resolve({}),
};

beforeEach(() => {
  notFound.mockClear();
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue({ id: "admin-1", role: "admin" } as never);
  vi.mocked(getModeratorRecord).mockReset().mockResolvedValue(record());
  vi.mocked(getAuditLogs).mockReset().mockResolvedValue(journal(1, 57));
});

describe("a moderator's record", () => {
  it("is the administrator's screen and nobody else's", async () => {
    render(await ModeratorPage(props));

    expect(requireRole).toHaveBeenCalledWith("admin");
  });

  it("answers 404 for somebody who is not a moderator", async () => {
    vi.mocked(getModeratorRecord).mockResolvedValue(null);

    await expect(ModeratorPage(props)).rejects.toThrow("not-found");
  });

  it("counts every kind of decision", async () => {
    render(await ModeratorPage(props));

    expect(screen.getByText("Товаров одобрено")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("Аккаунтов заблокировано")).toBeInTheDocument();
  });

  it("says the figures come from the decisions rather than from a counter", async () => {
    render(await ModeratorPage(props));

    expect(screen.getByText(/по самим решениям/i)).toBeInTheDocument();
  });

  it("asks the journal for this moderator's own entries", async () => {
    render(await ModeratorPage(props));

    expect(getAuditLogs).toHaveBeenCalledWith(0, { actorId: MODERATOR });
  });

  it("offers the whole journal filtered to them, with how many there are", async () => {
    render(await ModeratorPage(props));

    const link = screen.getByRole("link", { name: /все записи этого модератора/i });
    expect(link).toHaveAttribute("href", `/admin/audit?actor_id=${MODERATOR}`);
    expect(link).toHaveTextContent("57");
  });

  it("says they have done nothing yet rather than that the journal broke", async () => {
    vi.mocked(getAuditLogs).mockResolvedValue(journal(0, 0));

    render(await ModeratorPage(props));

    expect(screen.getByText("Пока ничего не делал.")).toBeInTheDocument();
  });

  it("says the journal could not be read when it could not, keeping the counts", async () => {
    vi.mocked(getAuditLogs).mockResolvedValue(null);

    render(await ModeratorPage(props));

    expect(screen.getByText("Журнал сейчас недоступен.")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("offers the way back to the list of moderators", async () => {
    render(await ModeratorPage(props));

    expect(screen.getByRole("link", { name: "Модераторы" })).toHaveAttribute(
      "href",
      "/admin/moderators",
    );
  });
});
