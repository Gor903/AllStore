import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

/**
 * Where the confirmation link lands.
 *
 * Needs no session of its own: the token is the proof, and whoever opens the letter may well be
 * on a device that was never signed in. A page that demanded a session here would turn one
 * click into a sign-in on a telephone that has never seen this site.
 */

vi.mock("@/components/auth/ConfirmEmail", () => ({
  ConfirmEmail: ({ token }: { token: string }) => <div data-testid="confirm" data-token={token} />,
}));

const { default: ConfirmEmailPage } = await import("@/app/(public)/email/confirm/page");

const props = (token?: string | string[]) => ({
  params: Promise.resolve({}),
  searchParams: Promise.resolve(token === undefined ? {} : { token }),
});

describe("email confirmation page", () => {
  it("hands the token from the address bar on to be spent", async () => {
    render(await ConfirmEmailPage(props("a-token-from-the-letter")));

    expect(screen.getByTestId("confirm")).toHaveAttribute("data-token", "a-token-from-the-letter");
  });

  it("asks for nothing when the link carried no token", async () => {
    render(await ConfirmEmailPage(props()));

    expect(screen.queryByTestId("confirm")).not.toBeInTheDocument();
    expect(screen.getByText(/в ссылке нет токена/i)).toBeInTheDocument();
  });

  it("says where a new letter can be asked for", async () => {
    render(await ConfirmEmailPage(props()));

    expect(screen.getByRole("link", { name: "кабинете" })).toHaveAttribute("href", "/dashboard");
  });

  it("treats a repeated token in the address as no token", async () => {
    render(await ConfirmEmailPage(props(["a", "b"])));

    expect(screen.queryByTestId("confirm")).not.toBeInTheDocument();
  });
});
