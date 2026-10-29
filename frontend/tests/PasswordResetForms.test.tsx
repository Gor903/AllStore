import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";
import { ResetPasswordForm } from "@/components/auth/ResetPasswordForm";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

const apiPost = vi.fn();
vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

beforeEach(() => {
  push.mockReset();
  refresh.mockReset();
  apiPost.mockReset().mockResolvedValue({ ok: true, data: {} });
});

describe("ForgotPasswordForm", () => {
  it("asks for the link and says the same thing whatever the answer", async () => {
    const user = userEvent.setup();
    render(<ForgotPasswordForm />);

    await user.type(screen.getByLabelText("Email"), "buyer@example.com");
    await user.click(screen.getByRole("button", { name: "Прислать ссылку" }));

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith("/auth/password-reset/request", {
        email: "buyer@example.com",
      });
    });
    // the wording must not depend on whether the account exists — it is the whole point
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Если аккаунт с таким адресом есть",
    );
  });

  it("shows why nothing happened when the server refuses outright", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { message: "Слишком много попыток, попробуйте позже", fieldErrors: {} },
    });
    const user = userEvent.setup();
    render(<ForgotPasswordForm />);

    await user.type(screen.getByLabelText("Email"), "buyer@example.com");
    await user.click(screen.getByRole("button", { name: "Прислать ссылку" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Слишком много попыток");
  });
});

describe("ResetPasswordForm", () => {
  async function fill(password: string, confirmation: string) {
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Новый пароль"), password);
    await user.type(screen.getByLabelText("Новый пароль ещё раз"), confirmation);
    await user.click(screen.getByRole("button", { name: "Задать пароль" }));
  }

  it("sends the token from the link, never from a field", async () => {
    render(<ResetPasswordForm token="token-from-the-letter" />);

    await fill("a-password-of-my-own-1", "a-password-of-my-own-1");

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith("/auth/password-reset/confirm", {
        token: "token-from-the-letter",
        password: "a-password-of-my-own-1",
      });
    });
  });

  it("catches a typo in the confirmation without troubling the server", async () => {
    render(<ResetPasswordForm token="t" />);

    await fill("a-password-of-my-own-1", "a-password-of-my-own-2");

    expect(await screen.findByText("Пароли не совпадают")).toBeInTheDocument();
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("sends them to sign in again, because the reset ended every session", async () => {
    render(<ResetPasswordForm token="t" />);

    await fill("a-password-of-my-own-1", "a-password-of-my-own-1");

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/login");
    });
  });

  it("says when the link itself is the problem", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { message: "Ссылка недействительна или устарела", fieldErrors: {} },
    });
    render(<ResetPasswordForm token="stale" />);

    await fill("a-password-of-my-own-1", "a-password-of-my-own-1");

    expect(await screen.findByRole("alert")).toHaveTextContent("Ссылка недействительна");
    expect(push).not.toHaveBeenCalled();
  });
});
