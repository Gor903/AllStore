import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PasswordChangeForm } from "@/components/auth/PasswordChangeForm";

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

async function fill(current: string, chosen: string, confirmation: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Текущий пароль"), current);
  await user.type(screen.getByLabelText("Новый пароль"), chosen);
  await user.type(screen.getByLabelText("Новый пароль ещё раз"), confirmation);
  await user.click(screen.getByRole("button", { name: "Задать пароль" }));
}

beforeEach(() => {
  push.mockClear();
  refresh.mockClear();
  apiPost.mockReset().mockResolvedValue({ ok: true, data: {} });
});

describe("смена пароля", () => {
  it("отправляет старый и новый пароль и отправляет входить заново", async () => {
    render(<PasswordChangeForm />);

    await fill("handed-to-me-1", "my-own-password-1", "my-own-password-1");

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/auth/password", {
        current_password: "handed-to-me-1",
        password: "my-own-password-1",
      }),
    );
    // the change ended every session, so there is nowhere to go but in again
    expect(push).toHaveBeenCalledWith("/login");
  });

  it("опечатку в подтверждении ловит на месте, не беспокоя сервер", async () => {
    render(<PasswordChangeForm />);

    await fill("handed-to-me-1", "my-own-password-1", "my-own-passward-1");

    expect(await screen.findByText("Пароли не совпадают")).toBeInTheDocument();
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("неверный текущий пароль показывает отказ сервера и никуда не уводит", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { message: "Текущий пароль неверен", fieldErrors: {} },
    });
    render(<PasswordChangeForm />);

    await fill("not-the-one-1", "my-own-password-1", "my-own-password-1");

    expect(await screen.findByRole("alert")).toHaveTextContent("Текущий пароль неверен");
    expect(push).not.toHaveBeenCalled();
  });
});
