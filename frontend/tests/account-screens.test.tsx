import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TransferAdmin } from "@/components/admin/TransferAdmin";
import { AccountRows } from "@/components/moderation/AccountRows";
import { BlockHistory } from "@/components/moderation/BlockHistory";
import type { AccountBlockList, User } from "@/lib/api";

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const apiGet = vi.fn();
const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

const VIEWER = "00000000-0000-0000-0000-000000000000";
const BUYER_ID = "11111111-1111-1111-1111-111111111111";

function account(overrides: Partial<User> = {}): User {
  return {
    id: BUYER_ID,
    email: "buyer@example.com",
    phone: null,
    role: "buyer",
    status: "active",
    email_verified_at: null,
    created_at: "2026-10-01T10:00:00Z",
    must_change_password: false,
    ...overrides,
  };
}

const HISTORY: AccountBlockList = {
  items: [
    {
      id: "22222222-2222-2222-2222-222222222222",
      reason: "Оскорбления в переписке",
      created_at: "2026-10-02T10:00:00Z",
      actor_email: "moderator@example.com",
      revoked_at: "2026-10-03T10:00:00Z",
      revoked_by_email: "admin@example.com",
      revoke_reason: "Разобрались",
      in_force: false,
    },
  ],
  total: 1,
  limit: 20,
  offset: 0,
};

beforeEach(() => {
  push.mockClear();
  refresh.mockClear();
  apiGet.mockReset().mockResolvedValue({ ok: true, data: HISTORY });
  apiPost.mockReset().mockResolvedValue({ ok: true, data: {} });
});

describe("account rows", () => {
  it("posts a ban to the shared route, with its reason", async () => {
    const user = userEvent.setup();
    render(<AccountRows items={[account()]} viewerId={VIEWER} />);

    await user.click(screen.getByRole("button", { name: "Заблокировать" }));
    await user.type(screen.getByRole("textbox"), "Оскорбления в переписке");
    await user.click(screen.getAllByRole("button", { name: "Заблокировать" })[1]!);

    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(apiPost).toHaveBeenCalledWith(`/accounts/${BUYER_ID}/block`, {
      reason: "Оскорбления в переписке",
    });
  });

  it("offers to lift the ban on an account that has one", () => {
    render(<AccountRows items={[account({ status: "blocked" })]} viewerId={VIEWER} />);

    expect(screen.getByRole("button", { name: "Разблокировать" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Заблокировать" })).toBeNull();
  });

  it("offers nobody a button against their own account", () => {
    render(<AccountRows items={[account({ id: VIEWER })]} viewerId={VIEWER} />);

    expect(screen.queryByRole("button", { name: "Заблокировать" })).toBeNull();
    expect(screen.getByText(/это вы/)).toBeInTheDocument();
  });
});

describe("block history", () => {
  it("asks for nothing until somebody wants to see it", () => {
    render(<BlockHistory userId={BUYER_ID} email="buyer@example.com" />);

    expect(apiGet).not.toHaveBeenCalled();
  });

  it("shows a lifted ban as something that still happened", async () => {
    const user = userEvent.setup();
    render(<BlockHistory userId={BUYER_ID} email="buyer@example.com" />);

    await user.click(screen.getByRole("button", { name: "История блокировок" }));

    await waitFor(() => expect(apiGet).toHaveBeenCalledWith(`/accounts/${BUYER_ID}/blocks`));
    expect(await screen.findByText(/Оскорбления в переписке/)).toBeInTheDocument();
    expect(screen.getByText(/Снята/)).toBeInTheDocument();
    expect(screen.getByText(/admin@example.com/)).toBeInTheDocument();
  });

  it("fetches once and then just folds away", async () => {
    const user = userEvent.setup();
    render(<BlockHistory userId={BUYER_ID} email="buyer@example.com" />);

    await user.click(screen.getByRole("button", { name: "История блокировок" }));
    await screen.findByText(/Оскорбления в переписке/);
    await user.click(screen.getByRole("button", { name: "Скрыть историю блокировок" }));
    await user.click(screen.getByRole("button", { name: "История блокировок" }));

    expect(apiGet).toHaveBeenCalledTimes(1);
  });

  it("says plainly when there is nothing to show", async () => {
    apiGet.mockResolvedValue({ ok: true, data: { items: [], total: 0, limit: 20, offset: 0 } });
    const user = userEvent.setup();
    render(<BlockHistory userId={BUYER_ID} email="buyer@example.com" />);

    await user.click(screen.getByRole("button", { name: "История блокировок" }));

    expect(await screen.findByText(/ещё не блокировали/)).toBeInTheDocument();
  });
});

describe("handing the platform over", () => {
  it("asks before taking the role away from the person pressing it", async () => {
    const user = userEvent.setup();
    render(<TransferAdmin userId={BUYER_ID} email="moderator@example.com" />);

    await user.click(screen.getByRole("button", { name: "Передать админку" }));

    expect(apiPost).not.toHaveBeenCalled();
    expect(screen.getByText(/Вы станете модератором/)).toBeInTheDocument();
  });

  it("hands it over once confirmed and leaves the administrator's screens", async () => {
    const user = userEvent.setup();
    render(<TransferAdmin userId={BUYER_ID} email="moderator@example.com" />);

    await user.click(screen.getByRole("button", { name: "Передать админку" }));
    await user.click(screen.getByRole("button", { name: "Передать" }));

    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(apiPost).toHaveBeenCalledWith(`/admin/users/${BUYER_ID}/transfer-admin`, {});
    expect(push).toHaveBeenCalledWith("/moderation");
  });

  it("explains a refusal and stays put", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { message: "У этого аккаунта есть магазин", fieldErrors: {} },
    });
    const user = userEvent.setup();
    render(<TransferAdmin userId={BUYER_ID} email="seller@example.com" />);

    await user.click(screen.getByRole("button", { name: "Передать админку" }));
    await user.click(screen.getByRole("button", { name: "Передать" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("есть магазин");
    expect(push).not.toHaveBeenCalled();
  });
});
