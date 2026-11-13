import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BlockHistory } from "@/components/moderation/BlockHistory";
import type { AccountBlockList } from "@/lib/api";

/**
 * Every ban an account has ever had, loaded when somebody asks for it.
 *
 * On demand rather than with the page: a list of twenty accounts would otherwise make twenty
 * requests for a history most of them do not have. Shown at all because a ban that has been
 * lifted still happened, and whoever is about to decide again needs to know it did — which is
 * why a lifted ban stays in the list instead of disappearing from it.
 */

const apiGet = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiGet: (path: string) => apiGet(path),
}));

const USER = "11111111-1111-1111-1111-111111111111";
const EMAIL = "person@example.am";

function history(items: AccountBlockList["items"]): AccountBlockList {
  return { items, total: items.length, limit: 100, offset: 0 };
}

function entry(overrides: Partial<AccountBlockList["items"][number]> = {}) {
  return {
    id: "22222222-2222-2222-2222-222222222222",
    reason: "Спам в переписке",
    created_at: "2026-11-13T10:00:00Z",
    actor_email: "moderator@allstore.am",
    revoked_at: null,
    revoked_by_email: null,
    revoke_reason: null,
    in_force: true,
    ...overrides,
  };
}

async function open(): Promise<void> {
  await userEvent.click(screen.getByRole("button", { name: "История блокировок" }));
}

beforeEach(() => {
  apiGet.mockReset().mockResolvedValue({ ok: true, data: history([entry()]) });
});

describe("BlockHistory", () => {
  it("asks for nothing until somebody asks for it", () => {
    render(<BlockHistory userId={USER} email={EMAIL} />);

    expect(apiGet).not.toHaveBeenCalled();
  });

  it("loads the history on the first press", async () => {
    render(<BlockHistory userId={USER} email={EMAIL} />);

    await open();

    await waitFor(() => expect(apiGet).toHaveBeenCalledWith(`/accounts/${USER}/blocks`));
  });

  it("says whether it is open, so a screen reader can tell", async () => {
    render(<BlockHistory userId={USER} email={EMAIL} />);
    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "false");

    await open();

    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "true");
  });

  it("does not ask again when it is closed and opened", async () => {
    render(<BlockHistory userId={USER} email={EMAIL} />);

    await open();
    await screen.findByRole("list");
    await userEvent.click(screen.getByRole("button", { name: "Скрыть историю блокировок" }));
    await userEvent.click(screen.getByRole("button", { name: "История блокировок" }));

    expect(apiGet).toHaveBeenCalledTimes(1);
  });

  it("says the account has a clean record rather than showing an empty box", async () => {
    apiGet.mockResolvedValue({ ok: true, data: history([]) });
    render(<BlockHistory userId={USER} email={EMAIL} />);

    await open();

    expect(await screen.findByText(`${EMAIL} ещё не блокировали.`)).toBeInTheDocument();
  });

  it("says a ban is in force, with what it was for and who decided", async () => {
    render(<BlockHistory userId={USER} email={EMAIL} />);

    await open();

    const line = await screen.findByRole("listitem");
    expect(line).toHaveTextContent("Действует");
    expect(line).toHaveTextContent("Спам в переписке");
    expect(line).toHaveTextContent("moderator@allstore.am");
  });

  it("keeps a lifted ban in the list, because it still happened", async () => {
    apiGet.mockResolvedValue({
      ok: true,
      data: history([
        entry({
          in_force: false,
          revoked_at: "2026-11-14T10:00:00Z",
          revoked_by_email: "admin@allstore.am",
          revoke_reason: "Разобрались",
        }),
      ]),
    });
    render(<BlockHistory userId={USER} email={EMAIL} />);

    await open();

    const line = await screen.findByRole("listitem");
    expect(line).toHaveTextContent("Снята");
    expect(line).toHaveTextContent("admin@allstore.am");
    expect(line).toHaveTextContent("при снятии: Разобрались");
  });

  it("names a decision whose author is gone rather than leaving a gap", async () => {
    apiGet.mockResolvedValue({ ok: true, data: history([entry({ actor_email: null })]) });
    render(<BlockHistory userId={USER} email={EMAIL} />);

    await open();

    expect(await screen.findByText(/аккаунт удалён/)).toBeInTheDocument();
  });

  it("says it is loading while it loads", async () => {
    apiGet.mockReturnValue(new Promise(() => {}));
    render(<BlockHistory userId={USER} email={EMAIL} />);

    await open();

    expect(screen.getByText("Загружаем…")).toBeInTheDocument();
  });

  it("says the history could not be read, rather than that there is none", async () => {
    apiGet.mockResolvedValue({
      ok: false,
      error: { code: "offline", message: "Сервер недоступен", fieldErrors: {} },
    });
    render(<BlockHistory userId={USER} email={EMAIL} />);

    await open();

    expect(await screen.findByRole("alert")).toHaveTextContent("Сервер недоступен");
    expect(screen.queryByText(/ещё не блокировали/)).not.toBeInTheDocument();
  });
});
