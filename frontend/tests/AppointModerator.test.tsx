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
const HANDED_OVER = "handed-over-password-1";

async function fill(email: string, password: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Временный пароль"), password);
  await user.click(screen.getByRole("button", { name: "Завести" }));
}

beforeEach(() => {
  refresh.mockClear();
  apiPost.mockReset().mockResolvedValue({
    ok: true,
    data: { id: "11111111-1111-1111-1111-111111111111", email: EMAIL, role: "moderator" },
  });
});

describe("заведение модератора", () => {
  it("отправляет адрес и временный пароль", async () => {
    render(<AppointModerator />);

    await fill(EMAIL, HANDED_OVER);

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/admin/moderators", {
        email: EMAIL,
        password: HANDED_OVER,
      }),
    );
  });

  it("говорит, что передать человеку", async () => {
    render(<AppointModerator />);

    await fill(EMAIL, HANDED_OVER);

    const done = await screen.findByRole("status");
    expect(done).toHaveTextContent(EMAIL);
    expect(done).toHaveTextContent(/Передайте ему адрес и пароль/);
  });

  it("занятый адрес показывает отказом сервера и список не обновляет", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { message: "Аккаунт с таким адресом уже есть", fieldErrors: {} },
    });
    render(<AppointModerator />);

    await fill(EMAIL, HANDED_OVER);

    expect(await screen.findByRole("alert")).toHaveTextContent("Аккаунт с таким адресом уже есть");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("предупреждает, что пароль одноразовый", () => {
    render(<AppointModerator />);

    expect(screen.getByText(/площадка для него закрыта/)).toBeInTheDocument();
  });
});
