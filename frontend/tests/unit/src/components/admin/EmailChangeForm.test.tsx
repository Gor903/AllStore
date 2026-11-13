import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EmailChangeForm } from "@/components/admin/EmailChangeForm";

/**
 * Asking to move, not moving.
 *
 * Nothing changes until somebody opens the letter at the new address, so this screen stays
 * where it is and the session is left alone. It used to send people to the login page, which
 * was right when the change took effect on submit and is a lie now.
 *
 * The new-address box is deliberately empty rather than prefilled: prefilled, it invites a
 * submission that changes nothing, and the answer to that submission says it worked.
 */

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

async function ask(email: string, password: string): Promise<void> {
  await userEvent.type(screen.getByLabelText("Новый email"), email);
  await userEvent.type(screen.getByLabelText("Текущий пароль"), password);
  await userEvent.click(screen.getByRole("button", { name: "Сменить логин" }));
}

beforeEach(() => {
  apiPost.mockReset().mockResolvedValue({ ok: true, data: undefined });
});

describe("EmailChangeForm", () => {
  it("starts with an empty box rather than the address somebody already has", () => {
    render(<EmailChangeForm />);

    expect(screen.getByLabelText("Новый email")).toHaveValue("");
  });

  it("asks for the password, because a login is what a password protects", async () => {
    render(<EmailChangeForm />);

    await ask("new@example.am", "a-long-enough-password");

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/auth/email", {
        email: "new@example.am",
        current_password: "a-long-enough-password",
      }),
    );
  });

  it("says the old address still works, because it does", async () => {
    render(<EmailChangeForm />);

    await ask("new@example.am", "a-long-enough-password");

    expect(await screen.findByRole("status")).toHaveTextContent(/вход по старому продолжает/i);
  });

  it("says the old address was told, and what to do if it was not them", async () => {
    render(<EmailChangeForm />);

    await ask("new@example.am", "a-long-enough-password");

    const answer = await screen.findByRole("status");
    expect(answer).toHaveTextContent(/на старый адрес ушло уведомление/i);
    expect(answer).toHaveTextContent(/смените пароль/i);
  });

  it("takes the form away once the letter is on its way", async () => {
    render(<EmailChangeForm />);

    await ask("new@example.am", "a-long-enough-password");

    await waitFor(() => expect(screen.queryByRole("button")).not.toBeInTheDocument());
  });

  it("puts a refusal about the password next to the password", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: {
        code: "invalid_credentials",
        message: "Проверьте форму",
        fieldErrors: { current_password: "Неверный пароль" },
      },
    });
    render(<EmailChangeForm />);

    await ask("new@example.am", "wrong-password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Неверный пароль");
    expect(screen.getByLabelText("Текущий пароль")).toBeInvalid();
  });

  it("puts a refusal about the address next to the address", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: {
        code: "conflict",
        message: "Проверьте форму",
        fieldErrors: { email: "Этот адрес уже занят" },
      },
    });
    render(<EmailChangeForm />);

    await ask("taken@example.am", "a-long-enough-password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Этот адрес уже занят");
    expect(screen.getByLabelText("Новый email")).toBeInvalid();
  });

  it("keeps the form standing after a refusal, so it can be corrected", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "too_many_requests", message: "Слишком много попыток", fieldErrors: {} },
    });
    render(<EmailChangeForm />);

    await ask("new@example.am", "a-long-enough-password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Слишком много попыток");
    expect(screen.getByRole("button", { name: "Сменить логин" })).toBeEnabled();
  });

  it("cannot be submitted twice while the first attempt is in flight", async () => {
    apiPost.mockReturnValue(new Promise(() => {}));
    render(<EmailChangeForm />);

    await ask("new@example.am", "a-long-enough-password");

    expect(screen.getByRole("button", { name: "Меняем…" })).toBeDisabled();
  });
});
