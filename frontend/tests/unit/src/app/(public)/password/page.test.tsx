import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { User } from "@/lib/api";

/**
 * The one screen an account owing a password change may reach.
 *
 * It sits outside the guarded groups on purpose and reads the account through `getCurrentUser`
 * rather than `requireUser`: `requireUser` is what sends people here, so asking it would make
 * the redirect a loop — a page that redirects to itself forever.
 *
 * The two wordings are not decoration. Somebody whose password was handed to them needs to be
 * told that whoever issued it knows it; somebody changing their own needs to be told that every
 * session, including the one they are using, is about to end.
 */

const redirect = vi.fn((to: string) => {
  throw new Error(`redirect:${to}`);
});

vi.mock("next/navigation", () => ({ redirect: (to: string) => redirect(to) }));

vi.mock("@/lib/dal", () => ({ getCurrentUser: vi.fn() }));

vi.mock("@/components/auth/PasswordChangeForm", () => ({
  PasswordChangeForm: () => <form data-testid="password-form" />,
}));

const { getCurrentUser } = await import("@/lib/dal");
const { default: PasswordPage } = await import("@/app/(public)/password/page");

function account(mustChange: boolean): User {
  return {
    id: "1",
    email: "person@example.am",
    role: "moderator",
    must_change_password: mustChange,
  } as User;
}

beforeEach(() => {
  redirect.mockClear();
  vi.mocked(getCurrentUser).mockReset();
});

describe("password page", () => {
  it("sends somebody who is not signed in to sign in", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue(null);

    await expect(PasswordPage()).rejects.toThrow("redirect:/login");
  });

  it("lets through an account that owes a change, rather than bouncing it", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue(account(true));

    render(await PasswordPage());

    expect(screen.getByTestId("password-form")).toBeInTheDocument();
    expect(redirect).not.toHaveBeenCalled();
  });

  it("tells an account that owes one why, and what is shut until it is done", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue(account(true));

    render(await PasswordPage());

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Задайте свой пароль");
    expect(screen.getByText(/известен тем, кто его выдавал/i)).toBeInTheDocument();
    expect(screen.getByText(/остальная площадка закрыта/i)).toBeInTheDocument();
  });

  it("warns everybody else that this very session will end", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue(account(false));

    render(await PasswordPage());

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Смена пароля");
    expect(screen.getByText(/включая эту/i)).toBeInTheDocument();
  });
});
