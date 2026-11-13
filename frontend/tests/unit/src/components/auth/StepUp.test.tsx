import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StepUp } from "@/components/auth/StepUp";

/**
 * Asking for the password again, for the actions an unattended screen must not be enough for.
 *
 * The server has demanded this since stage 4 — appointing a moderator, handing over the
 * administrator role, attaching another way in — and for a while there was no screen that could
 * answer it: signing in granted the claim for ten minutes, so the actions worked if you were
 * quick and refused with no way forward if you were not.
 *
 * So the test is about the way forward. The reason comes from the server and is shown as given;
 * a wrong password is a refusal to read rather than a dead end; and `onDone` fires only when
 * the password was actually accepted, because it is what replays the action behind it.
 */

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

const onDone = vi.fn();
const onCancel = vi.fn();

async function confirm(password: string): Promise<void> {
  await userEvent.type(screen.getByLabelText("Пароль"), password);
  await userEvent.click(screen.getByRole("button", { name: "Подтвердить" }));
}

beforeEach(() => {
  onDone.mockClear();
  onCancel.mockClear();
  apiPost.mockReset().mockResolvedValue({ ok: true, data: undefined });
});

describe("StepUp", () => {
  it("says what it is asking for, in the server's own words", () => {
    render(<StepUp reason="Подтвердите пароль, чтобы передать админку" onDone={onDone} />);

    expect(screen.getByText("Подтвердите пароль, чтобы передать админку")).toBeInTheDocument();
  });

  it("asks the server to check the password", async () => {
    render(<StepUp reason="Подтвердите пароль" onDone={onDone} />);

    await confirm("a-long-enough-password");

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/auth/verify", {
        password: "a-long-enough-password",
      }),
    );
  });

  it("lets the action behind it run once the password was accepted", async () => {
    render(<StepUp reason="Подтвердите пароль" onDone={onDone} />);

    await confirm("a-long-enough-password");

    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("does not let it run when the password was wrong", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: {
        code: "invalid_credentials",
        message: "Проверьте форму",
        fieldErrors: { password: "Неверный пароль" },
      },
    });
    render(<StepUp reason="Подтвердите пароль" onDone={onDone} />);

    await confirm("wrong-password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Неверный пароль");
    expect(onDone).not.toHaveBeenCalled();
  });

  it("can be answered again after a wrong one", async () => {
    apiPost.mockResolvedValueOnce({
      ok: false,
      error: { code: "invalid_credentials", message: "Неверный пароль", fieldErrors: {} },
    });
    render(<StepUp reason="Подтвердите пароль" onDone={onDone} />);

    await confirm("wrong-password");
    await screen.findByRole("alert");
    await confirm("a-long-enough-password");

    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("shows a refusal that belongs to no field", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "too_many_requests", message: "Слишком много попыток", fieldErrors: {} },
    });
    render(<StepUp reason="Подтвердите пароль" onDone={onDone} />);

    await confirm("a-long-enough-password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Слишком много попыток");
  });

  it("cannot be answered twice while the first answer is being checked", async () => {
    apiPost.mockReturnValue(new Promise(() => {}));
    render(<StepUp reason="Подтвердите пароль" onDone={onDone} />);

    await confirm("a-long-enough-password");

    expect(screen.getByRole("button", { name: "Проверяем…" })).toBeDisabled();
  });

  it("offers a way out when the caller has somewhere to go back to", async () => {
    render(<StepUp reason="Подтвердите пароль" onDone={onDone} onCancel={onCancel} />);

    await userEvent.click(screen.getByRole("button", { name: "Отмена" }));

    expect(onCancel).toHaveBeenCalled();
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("offers none where the screen itself is the only thing to answer", () => {
    /* /password and /devices render this as the page: cancelling there would leave somebody
       looking at a screen with nothing on it. */
    render(<StepUp reason="Подтвердите пароль" onDone={onDone} />);

    expect(screen.queryByRole("button", { name: "Отмена" })).not.toBeInTheDocument();
  });

  it("asks the browser for the password it already has", () => {
    render(<StepUp reason="Подтвердите пароль" onDone={onDone} />);

    expect(screen.getByLabelText("Пароль")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByLabelText("Пароль")).toHaveAttribute("type", "password");
  });
});
