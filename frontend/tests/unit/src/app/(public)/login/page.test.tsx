import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { User } from "@/lib/api";

/**
 * The sign-in screen.
 *
 * Somebody already signed in has no business here: the page sends them to wherever their role
 * belongs, rather than offering a second sign-in that would read as the first one having failed.
 *
 * `?next=` comes from the address bar, so it is bounded to paths on this host. An absolute URL
 * taken from there would make the sign-in screen a redirector anybody can aim anywhere — which
 * is phishing with our own domain in the address bar.
 */

const redirect = vi.fn((to: string) => {
  throw new Error(`redirect:${to}`);
});

vi.mock("next/navigation", () => ({ redirect: (to: string) => redirect(to) }));

vi.mock("@/lib/dal", () => ({ getCurrentUser: vi.fn() }));

vi.mock("@/components/auth/LoginForm", () => ({
  LoginForm: ({ next }: { next: string | null }) => (
    <form data-testid="login-form" data-next={next ?? ""} />
  ),
}));

const { getCurrentUser } = await import("@/lib/dal");
const { default: LoginPage } = await import("@/app/(public)/login/page");

const props = (next?: string) => ({
  params: Promise.resolve({}),
  searchParams: Promise.resolve(next === undefined ? {} : { next }),
});

function account(role: User["role"]): User {
  return { id: "1", email: "person@example.am", role } as User;
}

beforeEach(() => {
  redirect.mockClear();
  vi.mocked(getCurrentUser).mockReset().mockResolvedValue(null);
});

describe("login page", () => {
  it("offers the form to somebody who is not signed in", async () => {
    render(await LoginPage(props()));

    expect(screen.getByTestId("login-form")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Вход", level: 1 })).toBeInTheDocument();
  });

  it("offers the way to a forgotten password and to registering", async () => {
    render(await LoginPage(props()));

    expect(screen.getByRole("link", { name: /забыли пароль/i })).toHaveAttribute(
      "href",
      "/password/forgot",
    );
    expect(screen.getByRole("link", { name: /зарегистрироваться/i })).toHaveAttribute(
      "href",
      "/register",
    );
  });

  it.each([
    ["buyer", "/dashboard"],
    ["seller", "/dashboard"],
    ["moderator", "/moderation"],
    ["admin", "/admin"],
  ] as const)("sends a signed-in %s where they belong", async (role, home) => {
    vi.mocked(getCurrentUser).mockResolvedValue(account(role));

    await expect(LoginPage(props())).rejects.toThrow(/redirect/);
    expect(redirect).toHaveBeenCalledWith(home);
  });

  it("carries a destination on this host through to the form", async () => {
    render(await LoginPage(props("/dashboard/store")));

    expect(screen.getByTestId("login-form")).toHaveAttribute("data-next", "/dashboard/store");
  });

  it.each([
    "https://evil.example/steal",
    "//evil.example", // two slashes are a host, not a path
    "/\\evil.example", // which a browser normalises to the same thing
    "evil.example",
  ])("refuses %s as a destination", async (next) => {
    render(await LoginPage(props(next)));

    expect(screen.getByTestId("login-form")).toHaveAttribute("data-next", "");
  });

  it("lands people by role when nowhere in particular was asked for", async () => {
    render(await LoginPage(props()));

    expect(screen.getByTestId("login-form")).toHaveAttribute("data-next", "");
  });
});
