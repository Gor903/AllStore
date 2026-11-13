import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";

/**
 * Asking for a reset link.
 *
 * The answer is the same whether the address is known or not, and this screen has to be too.
 * It would be friendlier to say "no such account" and save somebody the wait for a letter that
 * is not coming — and it would turn this form into a way of asking whether a particular person
 * has an account here, which is not ours to answer.
 *
 * So the test asserts the wording stays conditional, and that the form does not betray the
 * answer some other way: by what it shows, or by how long it takes to show it.
 */

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

async function ask(email: string): Promise<void> {
  await userEvent.type(screen.getByLabelText("Email"), email);
  await userEvent.click(screen.getByRole("button", { name: "Прислать ссылку" }));
}

beforeEach(() => {
  apiPost.mockReset().mockResolvedValue({ ok: true, data: undefined });
});

describe("ForgotPasswordForm", () => {
  it("asks the backend for a letter", async () => {
    render(<ForgotPasswordForm />);

    await ask("person@example.am");

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/auth/password-reset/request", {
        email: "person@example.am",
      }),
    );
  });

  it("says that there may be an account, never that there is one", async () => {
    render(<ForgotPasswordForm />);

    await ask("person@example.am");

    expect(await screen.findByRole("status")).toHaveTextContent(
      /если аккаунт с таким адресом есть/i,
    );
  });

  it("says the same thing for an address nobody registered", async () => {
    render(<ForgotPasswordForm />);

    await ask("nobody@example.am");

    expect(await screen.findByRole("status")).toHaveTextContent(
      /если аккаунт с таким адресом есть/i,
    );
  });

  it("says how long the link lasts and that it works once", async () => {
    render(<ForgotPasswordForm />);

    await ask("person@example.am");

    const answer = await screen.findByRole("status");
    expect(answer).toHaveTextContent(/два часа/);
    expect(answer).toHaveTextContent(/один раз/);
  });

  it("takes the form away once it has been answered", async () => {
    /* A form still standing after a successful send invites a second and a third, and every
       one of them is another letter into somebody's inbox. */
    render(<ForgotPasswordForm />);

    await ask("person@example.am");

    await waitFor(() => expect(screen.queryByRole("button")).not.toBeInTheDocument());
  });

  it("cannot be asked twice while the first letter is on its way", async () => {
    apiPost.mockReturnValue(new Promise(() => {}));
    render(<ForgotPasswordForm />);

    await ask("person@example.am");

    expect(screen.getByRole("button", { name: "Отправляем…" })).toBeDisabled();
  });

  it("puts a refusal about the address next to the address", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: {
        code: "validation_failed",
        message: "Проверьте форму",
        fieldErrors: { email: "Введите адрес электронной почты" },
      },
    });
    render(<ForgotPasswordForm />);

    await ask("not-an-address");

    expect(await screen.findByRole("alert")).toHaveTextContent("Введите адрес электронной почты");
  });

  it("shows a refusal that belongs to no field, and keeps the form", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "too_many_requests", message: "Слишком много попыток", fieldErrors: {} },
    });
    render(<ForgotPasswordForm />);

    await ask("person@example.am");

    expect(await screen.findByRole("alert")).toHaveTextContent("Слишком много попыток");
    expect(screen.getByRole("button", { name: "Прислать ссылку" })).toBeEnabled();
  });

  it("leaves the refusing to the backend rather than to the browser's own bubble", () => {
    const { container } = render(<ForgotPasswordForm />);

    expect(container.querySelector("form")).toHaveAttribute("novalidate");
  });
});
