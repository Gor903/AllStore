import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { User, UserList } from "@/lib/api";

/**
 * The administrator's list of accounts.
 *
 * Everything here is one administrator's: the role is not granted but handed over, and there is
 * exactly one of it. So the handover is offered only against a moderator — offering it against a
 * buyer would be offering to make somebody an administrator, which is not a thing this platform
 * does — and nothing at all is offered against the administrator's own row.
 */

vi.mock("@/lib/dal", () => ({
  ADMIN_PAGE_SIZE: 20,
  requireRole: vi.fn(),
  getAdminUsers: vi.fn(),
}));

vi.mock("@/components/admin/AdminNav", () => ({
  AdminNav: ({ current }: { current: string }) => (
    <header data-testid="nav" data-current={current} />
  ),
}));

vi.mock("@/components/admin/AccountFilters", () => ({
  AccountFilters: () => <form data-testid="filters" />,
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
        <li key={item.id}>
          {item.email}
          {extra?.(item)}
        </li>
      ))}
    </ul>
  ),
}));

vi.mock("@/components/admin/RoleSelect", () => ({
  RoleSelect: ({ userId }: { userId: string }) => <div data-testid="role-select">{userId}</div>,
}));

vi.mock("@/components/admin/TransferAdmin", () => ({
  TransferAdmin: ({ userId }: { userId: string }) => <div data-testid="transfer">{userId}</div>,
}));

const { requireRole, getAdminUsers } = await import("@/lib/dal");
const { default: AdminUsersPage } = await import("@/app/(admin)/admin/page");

const ADMIN = "admin-1";

function account(id: string, role: User["role"]): User {
  return { id, email: `${id}@example.am`, role, status: "active" } as User;
}

function page(items: User[]): UserList {
  return { items, total: items.length, limit: 20, offset: 0 } as UserList;
}

const props = { params: Promise.resolve({}), searchParams: Promise.resolve({}) };

beforeEach(() => {
  vi.mocked(requireRole).mockReset().mockResolvedValue(account(ADMIN, "admin"));
  vi.mocked(getAdminUsers)
    .mockReset()
    .mockResolvedValue(page([account("u1", "buyer")]));
});

describe("the administrator's accounts list", () => {
  it("is the administrator's screen and nobody else's", async () => {
    render(await AdminUsersPage(props));

    expect(requireRole).toHaveBeenCalledWith("admin");
  });

  it("says who is reading and that the role is handed over rather than granted", async () => {
    render(await AdminUsersPage(props));

    expect(screen.getByText(/Вы вошли как admin-1@example.am/)).toBeInTheDocument();
    expect(screen.getByText(/роль не снимают, её передают/i)).toBeInTheDocument();
  });

  it("offers a role change and a card against another account", async () => {
    render(await AdminUsersPage(props));

    expect(screen.getByTestId("role-select")).toHaveTextContent("u1");
    expect(screen.getByRole("link", { name: "Карточка" })).toHaveAttribute(
      "href",
      "/admin/users/u1",
    );
  });

  it("offers the handover only against a moderator", async () => {
    vi.mocked(getAdminUsers).mockResolvedValue(page([account("m1", "moderator")]));

    render(await AdminUsersPage(props));

    expect(screen.getByTestId("transfer")).toHaveTextContent("m1");
  });

  it("offers it against nobody else", async () => {
    render(await AdminUsersPage(props));

    expect(screen.queryByTestId("transfer")).not.toBeInTheDocument();
  });

  it("offers nothing at all against the administrator's own row", async () => {
    vi.mocked(getAdminUsers).mockResolvedValue(page([account(ADMIN, "admin")]));

    render(await AdminUsersPage(props));

    expect(screen.queryByTestId("role-select")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Карточка" })).not.toBeInTheDocument();
  });

  it("says how many were found", async () => {
    render(await AdminUsersPage(props));

    expect(screen.getByText("Найдено: 1")).toBeInTheDocument();
  });

  it("says nobody was found rather than that the list broke", async () => {
    vi.mocked(getAdminUsers).mockResolvedValue(page([]));

    render(await AdminUsersPage(props));

    expect(screen.getByText("Никого не нашлось.")).toBeInTheDocument();
  });

  it("says the list could not be read when it could not", async () => {
    vi.mocked(getAdminUsers).mockResolvedValue(null);

    render(await AdminUsersPage(props));

    expect(screen.getByText(/список сейчас недоступен/i)).toBeInTheDocument();
  });

  it("tells the rows who is reading", async () => {
    render(await AdminUsersPage(props));

    expect(screen.getByTestId("rows")).toHaveAttribute("data-viewer", ADMIN);
  });
});
