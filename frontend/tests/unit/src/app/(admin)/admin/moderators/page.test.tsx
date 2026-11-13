import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { User, UserList } from "@/lib/api";

/**
 * The moderators themselves.
 *
 * A separate screen from the accounts list on purpose: that one is about the people the platform
 * serves, this one about the people who run it. A moderator judges other people's shops and
 * closes other people's accounts, so the role is not taken on the site — the administrator
 * creates the account, and the platform generates the password (ADR 28).
 */

vi.mock("@/lib/dal", () => ({
  ADMIN_PAGE_SIZE: 20,
  requireRole: vi.fn(),
  getModerators: vi.fn(),
}));

vi.mock("@/components/admin/AdminNav", () => ({
  AdminNav: () => <header data-testid="nav" />,
}));

vi.mock("@/components/admin/AppointModerator", () => ({
  AppointModerator: () => <form data-testid="appoint" />,
}));

vi.mock("@/components/admin/ResetModeratorPassword", () => ({
  ResetModeratorPassword: ({ userId }: { userId: string }) => (
    <div data-testid="reset-password">{userId}</div>
  ),
}));

vi.mock("@/components/admin/ModeratorStatus", () => ({
  ModeratorStatus: ({ user }: { user: User }) => <span data-testid="status">{user.email}</span>,
}));

vi.mock("@/components/moderation/AccountRows", () => ({
  AccountRows: ({ items, extra }: { items: User[]; extra?: (item: User) => React.ReactNode }) => (
    <ul data-testid="rows">
      {items.map((item) => (
        <li key={item.id}>
          {item.email}
          {extra?.(item)}
        </li>
      ))}
    </ul>
  ),
}));

const { requireRole, getModerators } = await import("@/lib/dal");
const { default: ModeratorsPage } = await import("@/app/(admin)/admin/moderators/page");

function moderator(id: string): User {
  return { id, email: `${id}@allstore.am`, role: "moderator", status: "active" } as User;
}

function page(items: User[]): UserList {
  return { items, total: items.length, limit: 20, offset: 0 } as UserList;
}

const props = { params: Promise.resolve({}), searchParams: Promise.resolve({}) };

beforeEach(() => {
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue({ id: "admin-1", role: "admin" } as never);
  vi.mocked(getModerators)
    .mockReset()
    .mockResolvedValue(page([moderator("m1")]));
});

describe("the moderators screen", () => {
  it("is the administrator's screen and nobody else's", async () => {
    render(await ModeratorsPage(props));

    expect(requireRole).toHaveBeenCalledWith("admin");
  });

  it("says why the role is not taken but given", async () => {
    render(await ModeratorsPage(props));

    expect(screen.getByText(/роль не берут на сайте/i)).toBeInTheDocument();
  });

  it("offers to create one", async () => {
    render(await ModeratorsPage(props));

    expect(screen.getByTestId("appoint")).toBeInTheDocument();
  });

  it("offers a record of what each one decided, and a new password", async () => {
    render(await ModeratorsPage(props));

    expect(screen.getByRole("link", { name: "Что решил" })).toHaveAttribute(
      "href",
      "/admin/moderators/m1",
    );
    expect(screen.getByTestId("reset-password")).toHaveTextContent("m1");
  });

  it("says where each one stands with their own access", async () => {
    render(await ModeratorsPage(props));

    expect(screen.getByTestId("status")).toHaveTextContent("m1@allstore.am");
  });

  it("invites the first moderator rather than showing an empty list", async () => {
    vi.mocked(getModerators).mockResolvedValue(page([]));

    render(await ModeratorsPage(props));

    expect(screen.getByText(/заведите первого/i)).toBeInTheDocument();
  });

  it("says the list could not be read when it could not", async () => {
    vi.mocked(getModerators).mockResolvedValue(null);

    render(await ModeratorsPage(props));

    expect(screen.getByText(/список сейчас недоступен/i)).toBeInTheDocument();
    expect(screen.getByTestId("appoint")).toBeInTheDocument();
  });
});
