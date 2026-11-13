import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { UserList } from "@/lib/api";

/**
 * The people the platform serves: buyers and sellers.
 *
 * Moderators are not here and neither is the administrator — they run the platform rather than
 * being served by it, and they live in the administrator's own panel. The screen says so,
 * because "I cannot find my colleague in the list of accounts" is otherwise a bug report.
 *
 * It also says what a block is: it needs a reason, it is lifted by a separate action, it stays
 * in the history, and a blocked seller's shop goes dark by itself.
 */

vi.mock("@/lib/dal", () => ({
  ADMIN_PAGE_SIZE: 20,
  requireRole: vi.fn(),
  getReachableAccounts: vi.fn(),
  getModerationProducts: vi.fn(),
  getModerationBusinesses: vi.fn(),
}));

vi.mock("@/components/moderation/ModerationNav", () => ({
  ModerationNav: () => <header data-testid="nav" />,
}));

vi.mock("@/components/moderation/AccountRows", () => ({
  AccountRows: ({ items, viewerId }: { items: unknown[]; viewerId: string }) => (
    <ul data-testid="rows" data-viewer={viewerId}>
      {items.length}
    </ul>
  ),
}));

const { requireRole, getReachableAccounts, getModerationProducts, getModerationBusinesses } =
  await import("@/lib/dal");
const { default: ModerationAccountsPage } = await import("@/app/(admin)/moderation/accounts/page");

function page(count: number): UserList {
  return {
    items: Array.from({ length: count }, (_, index) => ({ id: String(index) })),
    total: count,
    limit: 20,
    offset: 0,
  } as unknown as UserList;
}

const props = (q?: string) => ({
  params: Promise.resolve({}),
  searchParams: Promise.resolve(q === undefined ? {} : { q }),
});

beforeEach(() => {
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue({ id: "viewer-1", role: "moderator" } as never);
  vi.mocked(getReachableAccounts).mockReset().mockResolvedValue(page(2));
  vi.mocked(getModerationProducts)
    .mockReset()
    .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 } as never);
  vi.mocked(getModerationBusinesses)
    .mockReset()
    .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 } as never);
});

describe("the accounts screen", () => {
  it("is open to a moderator and to the administrator", async () => {
    render(await ModerationAccountsPage(props()));

    expect(requireRole).toHaveBeenCalledWith("moderator", "admin");
  });

  it("says who is not in this list and where they are instead", async () => {
    render(await ModerationAccountsPage(props()));

    expect(screen.getByText(/модераторов здесь нет/i)).toBeInTheDocument();
    expect(screen.getByText(/в разделе «Модераторы» админки/i)).toBeInTheDocument();
  });

  it("says what a block is and what it does to a shop", async () => {
    render(await ModerationAccountsPage(props()));

    expect(screen.getByText(/блокировка\s+требует причины/i)).toBeInTheDocument();
    expect(screen.getByText(/магазин\s+заблокированного продавца гаснет сам/i)).toBeInTheDocument();
  });

  it("tells the rows who is reading, so nobody is offered a verdict on themselves", async () => {
    render(await ModerationAccountsPage(props()));

    expect(screen.getByTestId("rows")).toHaveAttribute("data-viewer", "viewer-1");
  });

  it("searches for what was typed", async () => {
    render(await ModerationAccountsPage(props("ромашка")));

    expect(getReachableAccounts).toHaveBeenCalledWith("ромашка", 0);
  });

  it("asks for everybody when nothing was typed", async () => {
    render(await ModerationAccountsPage(props()));

    expect(getReachableAccounts).toHaveBeenCalledWith("", 0);
  });

  it("says nobody was found rather than that the list broke", async () => {
    vi.mocked(getReachableAccounts).mockResolvedValue(page(0));

    render(await ModerationAccountsPage(props("никто")));

    expect(screen.getByText("Никого не нашлось.")).toBeInTheDocument();
  });

  it("says the list could not be read when it could not", async () => {
    vi.mocked(getReachableAccounts).mockResolvedValue(null);

    render(await ModerationAccountsPage(props()));

    expect(screen.getByText(/список сейчас недоступен/i)).toBeInTheDocument();
  });

  it("names the search box without a visible label", async () => {
    render(await ModerationAccountsPage(props()));

    expect(screen.getByLabelText("Поиск по email")).toBeInTheDocument();
  });
});
