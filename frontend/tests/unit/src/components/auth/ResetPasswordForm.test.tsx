import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ResetPasswordForm } from "@/components/auth/ResetPasswordForm";

/**
 * Setting a new password from the link in the letter.
 *
 * The token comes from the address bar and never goes through a field: a hidden input would be
 * a live credential sitting in the DOM for any extension to read, and a visible one would be a
 * credential a browser offers to remember.
 *
 * The two boxes are checked here rather than by the server, because a mistyped confirmation is
 * a typo and not a refusal — sending it would spend the single-use token on a mistake.
 *
 * And a finished reset ends every session there was, so there is nowhere to go but in again.
 */

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

const TOKEN = "a-token-from-the-letter";

async function fill(password: string, confirmation: string): Promise<void> {
  await userEvent.type(screen.getByLabelText("Новый пароль"), password);
  await userEvent.type(screen.getByLabelText("Новый пароль ещё раз"), confirmation);
  await userEvent.click(screen.getByRole("button", { name: "Задать пароль" }));
}

beforeEach(() => {
  push.mockClear();
  refresh.mockClear();
  apiPost.mockReset().mockResolvedValue({ ok: true, data: undefined });
});

describe("ResetPasswordForm", () => {
  it("sends the token from the address bar together with the new password", async () => {
    render(<ResetPasswordForm token={TOKEN} />);

    await fill("a-long-enough-password", "a-long-enough-password");

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/auth/password-reset/confirm", {
        token: TOKEN,
        password: "a-long-enough-password",
      }),
    );
  });

  it("keeps the token out of the form entirely", async () => {
    const { container } = render(<ResetPasswordForm token={TOKEN} />);

    expect(container.querySelector(`input[value="${TOKEN}"]`)).toBeNull();
    expect(container.querySelector('input[name="token"]')).toBeNull();
  });

  it("catches a mistyped confirmation without spending the link", async () => {
    render(<ResetPasswordForm token={TOKEN} />);

    await fill("a-long-enough-password", "a-long-enough-passwore");

    expect(await screen.findByRole("alert")).toHaveTextContent("Пароли не совпадают");
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("puts that complaint on the box that was mistyped", async () => {
    render(<ResetPasswordForm token={TOKEN} />);

    await fill("a-long-enough-password", "something-else");

    expect(screen.getByLabelText("Новый пароль ещё раз")).toBeInvalid();
    expect(screen.getByLabelText("Новый пароль")).not.toBeInvalid();
  });

  it("stops complaining once the two agree", async () => {
    render(<ResetPasswordForm token={TOKEN} />);
    await fill("a-long-enough-password", "something-else");

    await userEvent.clear(screen.getByLabelText("Новый пароль ещё раз"));
    await userEvent.type(screen.getByLabelText("Новый пароль ещё раз"), "a-long-enough-password");
    await userEvent.click(screen.getByRole("button", { name: "Задать пароль" }));

    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(screen.queryByText("Пароли не совпадают")).not.toBeInTheDocument();
  });

  it("sends the person to sign in, because the reset ended every session", async () => {
    render(<ResetPasswordForm token={TOKEN} />);

    await fill("a-long-enough-password", "a-long-enough-password");

    await waitFor(() => expect(push).toHaveBeenCalledWith("/login"));
    expect(refresh).toHaveBeenCalled();
  });

  it("puts a refusal about the password next to the password", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: {
        code: "password_breached",
        message: "Проверьте форму",
        fieldErrors: { password: "Этот пароль уже встречался в утечках" },
      },
    });
    render(<ResetPasswordForm token={TOKEN} />);

    await fill("password123", "password123");

    expect(await screen.findByRole("alert")).toHaveTextContent("уже встречался в утечках");
    expect(push).not.toHaveBeenCalled();
  });

  it("shows a refusal about the link itself, which belongs to no field", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "not_found", message: "Ссылка больше не действует", fieldErrors: {} },
    });
    render(<ResetPasswordForm token={TOKEN} />);

    await fill("a-long-enough-password", "a-long-enough-password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Ссылка больше не действует");
  });

  it("asks the browser for a new password rather than offering the old one", async () => {
    render(<ResetPasswordForm token={TOKEN} />);

    for (const label of ["Новый пароль", "Новый пароль ещё раз"]) {
      expect(screen.getByLabelText(label)).toHaveAttribute("autocomplete", "new-password");
      expect(screen.getByLabelText(label)).toHaveAttribute("type", "password");
    }
  });

  it("cannot be submitted twice while the first attempt is in flight", async () => {
    apiPost.mockReturnValue(new Promise(() => {}));
    render(<ResetPasswordForm token={TOKEN} />);

    await fill("a-long-enough-password", "a-long-enough-password");

    expect(screen.getByRole("button", { name: "Меняем…" })).toBeDisabled();
  });
});
