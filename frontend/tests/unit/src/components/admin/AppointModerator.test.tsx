import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppointModerator } from "@/components/admin/AppointModerator";

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

const EMAIL = "new-moderator@example.com";
const GENERATED = "kf7p-2mxq-9vrt-ha3d";

async function appoint(email: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email"), email);
  await user.click(screen.getByRole("button", { name: "Завести" }));
}

beforeEach(() => {
  refresh.mockClear();
  apiPost.mockReset().mockResolvedValue({
    ok: true,
    data: {
      user: { id: "11111111-1111-1111-1111-111111111111", email: EMAIL, role: "moderator" },
      password: GENERATED,
    },
  });
});

describe("заведение модератора", () => {
  it("отправляет один адрес и ничего больше", async () => {
    render(<AppointModerator />);

    await appoint(EMAIL);

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/admin/moderators", { email: EMAIL }),
    );
  });

  it("пароля в форме нет: его придумывает площадка", () => {
    render(<AppointModerator />);

    expect(screen.queryByLabelText(/пароль/i)).not.toBeInTheDocument();
  });

  it("показывает выданный пароль, чтобы его можно было передать", async () => {
    render(<AppointModerator />);

    await appoint(EMAIL);

    const done = await screen.findByRole("status");
    expect(done).toHaveTextContent(EMAIL);
    expect(done).toHaveTextContent(GENERATED);
    expect(done).toHaveTextContent(/показан он один раз/);
  });

  it("копирует пароль, а не адрес", async () => {
    const user = userEvent.setup();
    render(<AppointModerator />);
    await appoint(EMAIL);
    await screen.findByRole("status");

    await user.click(screen.getByRole("button", { name: "Скопировать" }));

    await waitFor(async () => expect(await navigator.clipboard.readText()).toBe(GENERATED));
  });

  it("занятый адрес показывает отказом сервера и список не обновляет", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { message: "Аккаунт с таким адресом уже есть", fieldErrors: {}, code: "exists" },
    });
    render(<AppointModerator />);

    await appoint(EMAIL);

    expect(await screen.findByRole("alert")).toHaveTextContent("Аккаунт с таким адресом уже есть");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("предупреждает, что пароль одноразовый", async () => {
    render(<AppointModerator />);

    await appoint(EMAIL);

    expect(await screen.findByText(/площадка для него закрыта/)).toBeInTheDocument();
  });
});
