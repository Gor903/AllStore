import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { User } from "@/lib/api";

/**
 * One account, read by the administrator.
 *
 * The verdict row is the same one every other screen gets: barring somebody is one action in the
 * access matrix, and it must not look or behave differently because this page happens to be about
 * one person. The handover is still offered only against a moderator, and nothing at all against
 * the administrator's own card.
 *
 * Dates that are not there are said out loud — "никогда" rather than an empty cell, which reads
 * as a page that failed to load half of itself.
 */

const notFound = vi.fn(() => {
  throw new Error("not-found");
});

vi.mock("next/navigation", () => ({ notFound: () => notFound() }));

vi.mock("@/lib/dal", () => ({ requireRole: vi.fn(), getAdminUser: vi.fn() }));

vi.mock("@/components/admin/AdminNav", () => ({
  AdminNav: () => <header data-testid="nav" />,
}));

vi.mock("@/components/moderation/AccountRows", () => ({
  AccountRows: ({
    items,
    viewerId,
    extra,
  }: {
    items: User[];
    viewerId: string;
    extra?: (item: User) => React.ReactNode;
  }) => (
    <ul data-testid="rows" data-viewer={viewerId}>
      {items.map((item) => (
        <li key={item.id}>{extra?.(item)}</li>
      ))}
    </ul>
  ),
}));

vi.mock("@/components/admin/RoleSelect", () => ({
  RoleSelect: () => <div data-testid="role-select" />,
}));

vi.mock("@/components/admin/TransferAdmin", () => ({
  TransferAdmin: () => <div data-testid="transfer" />,
}));

const { requireRole, getAdminUser } = await import("@/lib/dal");
const { default: AdminUserPage } = await import("@/app/(admin)/admin/users/[userId]/page");

const ADMIN = "admin-1";

function account(overrides: Partial<User> = {}): User {
  return {
    id: "u1",
    email: "person@example.am",
    phone: null,
    role: "buyer",
    status: "active",
    created_at: "2026-11-01T10:00:00Z",
    last_login_at: null,
    email_verified_at: null,
    ...overrides,
  } as User;
}

const props = {
  params: Promise.resolve({ userId: "u1" }),
  searchParams: Promise.resolve({}),
};

beforeEach(() => {
  notFound.mockClear();
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue(account({ id: ADMIN, role: "admin" }));
  vi.mocked(getAdminUser).mockReset().mockResolvedValue(account());
});

describe("one account's card", () => {
  it("is the administrator's screen and nobody else's", async () => {
    render(await AdminUserPage(props));

    expect(requireRole).toHaveBeenCalledWith("admin");
  });

  it("answers 404 for an account that does not exist", async () => {
    vi.mocked(getAdminUser).mockResolvedValue(null);

    await expect(AdminUserPage(props)).rejects.toThrow("not-found");
  });

  it("says what the account is, in words rather than in codes", async () => {
    vi.mocked(getAdminUser).mockResolvedValue(account({ role: "seller" }));

    render(await AdminUserPage(props));

    expect(screen.getByRole("heading", { name: "person@example.am" })).toBeInTheDocument();
    expect(screen.getByText("продавец")).toBeInTheDocument();
  });

  it("says a date that is not there rather than leaving the cell blank", async () => {
    render(await AdminUserPage(props));

    expect(screen.getAllByText("никогда")).toHaveLength(2);
  });

  it("says a telephone nobody gave rather than leaving a gap", async () => {
    render(await AdminUserPage(props));

    expect(screen.getByText("не указан")).toBeInTheDocument();
  });

  it("gives this one account the same verdict row as every list", async () => {
    render(await AdminUserPage(props));

    expect(screen.getByTestId("rows")).toHaveAttribute("data-viewer", ADMIN);
    expect(screen.getByTestId("role-select")).toBeInTheDocument();
  });

  it("offers the handover only against a moderator", async () => {
    vi.mocked(getAdminUser).mockResolvedValue(account({ role: "moderator" }));

    render(await AdminUserPage(props));

    expect(screen.getByTestId("transfer")).toBeInTheDocument();
  });

  it("offers nothing at all on the administrator's own card", async () => {
    vi.mocked(getAdminUser).mockResolvedValue(account({ id: ADMIN, role: "admin" }));

    render(await AdminUserPage(props));

    expect(screen.queryByTestId("role-select")).not.toBeInTheDocument();
  });

  it("offers the way back to the list", async () => {
    render(await AdminUserPage(props));

    expect(screen.getByRole("link", { name: "Пользователи" })).toHaveAttribute("href", "/admin");
  });
});
