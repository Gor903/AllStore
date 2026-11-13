import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

/**
 * Where the link in the letter lands.
 *
 * Whether the token is any good is the server's question, asked when the form is submitted.
 * Checking it on arrival would turn this page into a way of finding out which tokens are live,
 * and would spend a one-time token on somebody merely opening the page — a mail client that
 * previews links would burn every reset link before its owner ever saw the form.
 *
 * A link with no token at all is an ordinary accident, so the page says what happened and where
 * to get another rather than showing a form that cannot work.
 */

vi.mock("@/components/auth/ResetPasswordForm", () => ({
  ResetPasswordForm: ({ token }: { token: string }) => (
    <form data-testid="reset-form" data-token={token} />
  ),
}));

const { default: ResetPasswordPage } = await import("@/app/(public)/password/reset/page");

const props = (token?: string | string[]) => ({
  params: Promise.resolve({}),
  searchParams: Promise.resolve(token === undefined ? {} : { token }),
});

describe("password reset page", () => {
  it("hands the token from the address bar to the form, unchecked", async () => {
    render(await ResetPasswordPage(props("a-token-from-the-letter")));

    expect(screen.getByTestId("reset-form")).toHaveAttribute(
      "data-token",
      "a-token-from-the-letter",
    );
  });

  it("warns that every session will end", async () => {
    render(await ResetPasswordPage(props("a-token-from-the-letter")));

    expect(screen.getByText(/все сессии завершатся/i)).toBeInTheDocument();
  });

  it("offers a new link in case this one is stale", async () => {
    render(await ResetPasswordPage(props("a-token-from-the-letter")));

    expect(screen.getByRole("link", { name: /запросить новую/i })).toHaveAttribute(
      "href",
      "/password/forgot",
    );
  });

  it("shows no form at all when the link carried no token", async () => {
    render(await ResetPasswordPage(props()));

    expect(screen.queryByTestId("reset-form")).not.toBeInTheDocument();
    expect(screen.getByText(/в ссылке нет токена/i)).toBeInTheDocument();
  });

  it("says where to get another one instead", async () => {
    render(await ResetPasswordPage(props()));

    expect(screen.getByRole("link", { name: /запросите новую ссылку/i })).toHaveAttribute(
      "href",
      "/password/forgot",
    );
  });

  it("treats a repeated token in the address as no token", async () => {
    /* `?token=a&token=b` arrives as an array, and guessing which of the two was meant would be
       guessing with somebody's account. */
    render(await ResetPasswordPage(props(["a", "b"])));

    expect(screen.queryByTestId("reset-form")).not.toBeInTheDocument();
  });
});
