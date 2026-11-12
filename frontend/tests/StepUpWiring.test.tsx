import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppointModerator } from "@/components/admin/AppointModerator";
import { ResetModeratorPassword } from "@/components/admin/ResetModeratorPassword";
import { RoleSelect } from "@/components/admin/RoleSelect";
import { TransferAdmin } from "@/components/admin/TransferAdmin";

const refresh = vi.fn();
const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push }),
}));

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

const USER_ID = "11111111-1111-1111-1111-111111111111";
const REFUSAL = {
  ok: false,
  error: {
    message: "Подтвердите пароль, чтобы продолжить",
    fieldErrors: {},
    code: "verification_required",
  },
};
const DONE = { ok: true, data: { id: USER_ID, email: "someone@example.com", role: "moderator" } };

/**
 * The four actions the server guards with `require_fresh_verification`. Each is reached a
 * different way — a form, a select, a confirmation — so each is driven the way a person
 * would, rather than by calling the handler.
 */
const ACTIONS = [
  {
    name: "заведение модератора",
    path: "/admin/moderators",
    render: () => render(<AppointModerator />),
    act: async (user: ReturnType<typeof userEvent.setup>) => {
      await user.type(screen.getByLabelText("Email"), "new@example.com");
      await user.type(screen.getByLabelText("Временный пароль"), "handed-over-password-1");
      await user.click(screen.getByRole("button", { name: "Завести" }));
    },
  },
  {
    name: "выдача нового пароля модератору",
    path: `/admin/moderators/${USER_ID}/password`,
    render: () => render(<ResetModeratorPassword userId={USER_ID} email="mod@example.com" />),
    act: async (user: ReturnType<typeof userEvent.setup>) => {
      await user.click(screen.getByRole("button", { name: "Выдать новый пароль" }));
      await user.type(screen.getByPlaceholderText("Новый временный пароль"), "replacement-1");
      await user.click(screen.getByRole("button", { name: "Выдать" }));
    },
  },
  {
    name: "смена роли",
    path: `/admin/users/${USER_ID}/role`,
    render: () => render(<RoleSelect userId={USER_ID} role="buyer" />),
    act: async (user: ReturnType<typeof userEvent.setup>) => {
      await user.selectOptions(screen.getByLabelText("Роль"), "moderator");
    },
  },
  {
    name: "передача админки",
    path: `/admin/users/${USER_ID}/transfer-admin`,
    render: () => render(<TransferAdmin userId={USER_ID} email="heir@example.com" />),
    act: async (user: ReturnType<typeof userEvent.setup>) => {
      await user.click(screen.getByRole("button", { name: "Передать админку" }));
      await user.click(screen.getByRole("button", { name: "Передать" }));
    },
  },
];

beforeEach(() => {
  refresh.mockClear();
  push.mockClear();
  apiPost.mockReset();
});

describe.each(ACTIONS)(
  "$name просит пароль, когда вход был давно",
  ({ path, render: mount, act }) => {
    it("показывает экран подтверждения вместо отказа", async () => {
      apiPost.mockResolvedValue(REFUSAL);
      mount();

      await act(userEvent.setup());

      expect(await screen.findByLabelText("Пароль")).toBeInTheDocument();
      expect(screen.getByText("Подтвердите пароль, чтобы продолжить")).toBeInTheDocument();
    });

    it("повторяет само действие после подтверждения, не спрашивая форму заново", async () => {
      const user = userEvent.setup();
      apiPost.mockResolvedValue(REFUSAL);
      mount();
      await act(user);
      await screen.findByLabelText("Пароль");

      // the confirmation itself, then the action again — now allowed
      apiPost.mockReset().mockResolvedValue(DONE);
      await user.type(screen.getByLabelText("Пароль"), "my-own-password-1");
      await user.click(screen.getByRole("button", { name: "Подтвердить" }));

      await waitFor(() => expect(apiPost).toHaveBeenCalledWith("/auth/verify", expect.anything()));
      await waitFor(() => expect(apiPost).toHaveBeenCalledWith(path, expect.anything()));
    });

    it("отмена возвращает тот отказ, который пришёл от сервера", async () => {
      const user = userEvent.setup();
      apiPost.mockResolvedValue(REFUSAL);
      mount();
      await act(user);
      await screen.findByLabelText("Пароль");

      // two screens here can carry a cancel button, so take the one next to the password
      const confirmation = screen.getByLabelText("Пароль").closest("form");
      await user.click(within(confirmation as HTMLElement).getByRole("button", { name: "Отмена" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("Подтвердите пароль");
      expect(screen.queryByLabelText("Пароль")).not.toBeInTheDocument();
    });
  },
);
