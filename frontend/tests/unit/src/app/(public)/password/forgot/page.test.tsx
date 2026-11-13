import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

/**
 * Asking for a reset link.
 *
 * The screen itself is a frame around the form: what matters here is that it needs no session
 * — somebody who cannot sign in is exactly the person who comes here — and that it says what
 * will happen, so nobody sits waiting for a letter without knowing one was promised.
 */

vi.mock("@/components/auth/ForgotPasswordForm", () => ({
  ForgotPasswordForm: () => <form data-testid="forgot-form" />,
}));

const { default: ForgotPasswordPage } = await import("@/app/(public)/password/forgot/page");

describe("forgot password page", () => {
  it("offers the form with no session of any kind", () => {
    render(ForgotPasswordPage());

    expect(screen.getByTestId("forgot-form")).toBeInTheDocument();
  });

  it("says what will be sent and what it is for", () => {
    render(ForgotPasswordPage());

    expect(screen.getByText(/пришлём ссылку/i)).toBeInTheDocument();
    expect(screen.getByText(/задать новый пароль/i)).toBeInTheDocument();
  });

  it("offers the way back for somebody who has just remembered", () => {
    render(ForgotPasswordPage());

    expect(screen.getByRole("link", { name: "Войти" })).toHaveAttribute("href", "/login");
  });
});
