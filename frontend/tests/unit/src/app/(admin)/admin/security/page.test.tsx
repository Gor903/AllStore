import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { User } from "@/lib/api";

/**
 * The administrator's own access.
 *
 * The password comes first, because that is what somebody opening a screen called «Доступ» has
 * come to change — and because a form asking for a password while quietly doing something else
 * is how this screen went wrong before.
 *
 * It also says the one thing nobody can work out from the interface: if the password is lost
 * entirely, the way back is on the server, not on this page.
 */

vi.mock("@/lib/dal", () => ({ requireRole: vi.fn() }));

vi.mock("@/components/admin/AdminNav", () => ({
  AdminNav: ({ current }: { current: string }) => (
    <header data-testid="nav" data-current={current} />
  ),
}));

vi.mock("@/components/auth/PasswordChangeForm", () => ({
  PasswordChangeForm: () => <form data-testid="password-form" />,
}));

vi.mock("@/components/admin/EmailChangeForm", () => ({
  EmailChangeForm: () => <form data-testid="email-form" />,
}));

const { requireRole } = await import("@/lib/dal");
const { default: AdminSecurityPage } = await import("@/app/(admin)/admin/security/page");

beforeEach(() => {
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue({ id: "1", email: "admin@allstore.am", role: "admin" } as User);
});

describe("the administrator's access screen", () => {
  it("is the administrator's screen and nobody else's", async () => {
    render(await AdminSecurityPage());

    expect(requireRole).toHaveBeenCalledWith("admin");
  });

  it("offers both changes", async () => {
    render(await AdminSecurityPage());

    expect(screen.getByTestId("password-form")).toBeInTheDocument();
    expect(screen.getByTestId("email-form")).toBeInTheDocument();
  });

  it("puts the password first, which is what people come here for", async () => {
    render(await AdminSecurityPage());

    const headings = screen.getAllByRole("heading", { level: 2 }).map((node) => node.textContent);
    expect(headings[0]).toBe("Пароль");
  });

  it("says every change ends every session and goes into the journal", async () => {
    render(await AdminSecurityPage());

    expect(screen.getByText(/завершает все сессии/i)).toBeInTheDocument();
    expect(screen.getByText(/записываются в журнал/i)).toBeInTheDocument();
  });

  it("says what to do when the password is lost entirely", async () => {
    render(await AdminSecurityPage());

    expect(screen.getByText(/bootstrap_admin --reset-password/)).toBeInTheDocument();
  });

  it("shows the login the account answers to now", async () => {
    render(await AdminSecurityPage());

    expect(screen.getByText(/Сейчас: admin@allstore.am/)).toBeInTheDocument();
  });

  it("points at the screens everybody shares rather than copying them", async () => {
    render(await AdminSecurityPage());

    expect(screen.getByRole("link", { name: "/password" })).toHaveAttribute("href", "/password");
    expect(screen.getByRole("link", { name: "/devices" })).toHaveAttribute("href", "/devices");
  });
});
