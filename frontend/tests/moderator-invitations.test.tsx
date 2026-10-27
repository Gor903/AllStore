import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { InviteModerator } from "@/components/admin/InviteModerator";
import { ModeratorRegisterForm } from "@/components/auth/ModeratorRegisterForm";

const push = vi.fn();
const refresh = vi.fn();
let query = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
  useSearchParams: () => query,
}));

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

const TOKEN = "a-very-long-one-time-secret";
const EMAIL = "invited@example.com";

beforeEach(() => {
  push.mockClear();
  refresh.mockClear();
  query = new URLSearchParams();
  apiPost.mockReset().mockResolvedValue({
    ok: true,
    data: { invitation: { id: "1", email: EMAIL }, token: TOKEN },
  });
  vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn(async () => undefined) } });
});

describe("issuing an invitation", () => {
  it("shows the link once, built from the one-time secret", async () => {
    const user = userEvent.setup();
    render(<InviteModerator />);

    await user.type(screen.getByLabelText("Email"), EMAIL);
    await user.click(screen.getByRole("button", { name: "Создать приглашение" }));

    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(apiPost).toHaveBeenCalledWith("/admin/moderator-invitations", { email: EMAIL });
    const shown = await screen.findByText(/register\/moderator/);
    expect(shown).toHaveTextContent(encodeURIComponent(TOKEN));
    expect(shown).toHaveTextContent(encodeURIComponent(EMAIL));
  });

  it("says plainly that nobody posted the letter", async () => {
    const user = userEvent.setup();
    render(<InviteModerator />);

    await user.type(screen.getByLabelText("Email"), EMAIL);
    await user.click(screen.getByRole("button", { name: "Создать приглашение" }));

    expect(await screen.findByText(/Отправка писем ещё не настроена/)).toBeInTheDocument();
  });

  it("explains a refusal instead of swallowing it", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { message: "Для этого адреса уже есть действующее приглашение", fieldErrors: {} },
    });
    const user = userEvent.setup();
    render(<InviteModerator />);

    await user.type(screen.getByLabelText("Email"), EMAIL);
    await user.click(screen.getByRole("button", { name: "Создать приглашение" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("уже есть действующее приглашение");
    expect(screen.queryByText(/register\/moderator/)).toBeNull();
  });
});

describe("accepting an invitation", () => {
  it("registers with the address from the link, not one the visitor typed", async () => {
    query = new URLSearchParams({ token: TOKEN, email: EMAIL });
    const user = userEvent.setup();
    render(<ModeratorRegisterForm />);

    await user.type(screen.getByLabelText("Пароль"), "moderator-password-1");
    await user.click(screen.getByRole("button", { name: "Стать модератором" }));

    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(apiPost).toHaveBeenCalledWith("/auth/register/moderator", {
      token: TOKEN,
      email: EMAIL,
      password: "moderator-password-1",
    });
    expect(push).toHaveBeenCalledWith("/moderation");
  });

  it("offers no form at all when the link is incomplete", () => {
    query = new URLSearchParams({ token: TOKEN });

    render(<ModeratorRegisterForm />);

    expect(screen.queryByLabelText("Пароль")).toBeNull();
    expect(screen.getByRole("alert")).toHaveTextContent("Ссылка неполная");
  });

  it("repeats the backend's refusal without guessing at its reason", async () => {
    query = new URLSearchParams({ token: TOKEN, email: EMAIL });
    apiPost.mockResolvedValue({
      ok: false,
      error: { message: "Приглашение недействительно или устарело", fieldErrors: {} },
    });
    const user = userEvent.setup();
    render(<ModeratorRegisterForm />);

    await user.type(screen.getByLabelText("Пароль"), "moderator-password-1");
    await user.click(screen.getByRole("button", { name: "Стать модератором" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("недействительно или устарело");
    expect(push).not.toHaveBeenCalled();
  });
});
