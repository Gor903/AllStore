import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { User } from "@/lib/api";

/**
 * The registration screen.
 *
 * Somebody already signed in is sent to wherever their role belongs: offering registration to
 * an account that exists invites a second one made by somebody who merely forgot they were
 * signed in, and then two accounts own one person's orders.
 *
 * The page says plainly that a seller's shop is checked before it is published — somebody
 * registering as a seller and finding nothing in the catalogue should know why before they
 * start, not after they have filled in a product.
 */

const redirect = vi.fn((to: string) => {
  throw new Error(`redirect:${to}`);
});

vi.mock("next/navigation", () => ({ redirect: (to: string) => redirect(to) }));

vi.mock("@/lib/dal", () => ({ getCurrentUser: vi.fn() }));

vi.mock("@/components/auth/RegisterForm", () => ({
  RegisterForm: () => <form data-testid="register-form" />,
}));

const { getCurrentUser } = await import("@/lib/dal");
const { default: RegisterPage } = await import("@/app/(public)/register/page");

function account(role: User["role"]): User {
  return { id: "1", email: "person@example.am", role } as User;
}

beforeEach(() => {
  redirect.mockClear();
  vi.mocked(getCurrentUser).mockReset().mockResolvedValue(null);
});

describe("register page", () => {
  it("offers the form to somebody with no account", async () => {
    render(await RegisterPage());

    expect(screen.getByTestId("register-form")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Регистрация", level: 1 })).toBeInTheDocument();
  });

  it("says a seller's shop is checked before it is published", async () => {
    render(await RegisterPage());

    expect(screen.getByText(/проходит проверку модератором/i)).toBeInTheDocument();
  });

  it("offers the way in to somebody who already has an account", async () => {
    render(await RegisterPage());

    expect(screen.getByRole("link", { name: "Войти" })).toHaveAttribute("href", "/login");
  });

  it.each([
    ["buyer", "/dashboard"],
    ["moderator", "/moderation"],
    ["admin", "/admin"],
  ] as const)("sends a signed-in %s where they belong instead", async (role, home) => {
    vi.mocked(getCurrentUser).mockResolvedValue(account(role));

    await expect(RegisterPage()).rejects.toThrow(/redirect/);
    expect(redirect).toHaveBeenCalledWith(home);
  });
});
