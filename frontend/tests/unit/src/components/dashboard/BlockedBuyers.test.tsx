import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BlockedBuyers } from "@/components/dashboard/BlockedBuyers";
import type { CustomerBlock } from "@/lib/api";

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

const BLOCK_ID = "33333333-3333-3333-3333-333333333333";

function block(overrides: Partial<CustomerBlock> = {}): CustomerBlock {
  return {
    id: BLOCK_ID,
    buyer_email: "buyer@example.com",
    reason: "Хамство в переписке",
    created_at: "2026-10-02T10:00:00Z",
    revoked_at: null,
    revoked_by_email: null,
    in_force: true,
    store_name: null,
    ...overrides,
  };
}

beforeEach(() => {
  refresh.mockClear();
  apiPost.mockReset().mockResolvedValue({ ok: true, data: {} });
});

describe("the shop's own door", () => {
  it("closes it to one buyer, by address and with a reason", async () => {
    const user = userEvent.setup();
    render(<BlockedBuyers items={[]} />);

    await user.type(screen.getByLabelText("Email покупателя"), "buyer@example.com");
    await user.type(screen.getByLabelText("Причина"), "Хамство в переписке");
    await user.click(screen.getByRole("button", { name: "Закрыть доступ" }));

    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(apiPost).toHaveBeenCalledWith("/stores/me/blocked-buyers", {
      email: "buyer@example.com",
      reason: "Хамство в переписке",
    });
    expect(refresh).toHaveBeenCalled();
  });

  it("says in so many words that this is not a platform-wide ban", () => {
    render(<BlockedBuyers items={[]} />);

    expect(screen.getByText(/только в вашем магазине/)).toBeInTheDocument();
    expect(screen.getByText(/может пожаловаться на вас модератору/)).toBeInTheDocument();
  });

  it("offers no way to bar somebody from the platform", () => {
    render(<BlockedBuyers items={[block()]} />);

    expect(screen.queryByRole("button", { name: /Заблокировать/ })).toBeNull();
  });

  it("opens the door again and keeps the record", async () => {
    const user = userEvent.setup();
    render(<BlockedBuyers items={[block()]} />);

    await user.click(screen.getByRole("button", { name: "Открыть доступ" }));

    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(apiPost).toHaveBeenCalledWith(`/stores/me/blocked-buyers/${BLOCK_ID}/revoke`, {});
  });

  it("keeps lifted restrictions out of the way but not out of sight", () => {
    render(
      <BlockedBuyers items={[block({ in_force: false, revoked_at: "2026-10-03T10:00:00Z" })]} />,
    );

    expect(screen.getByText(/Сейчас магазин никому не закрыт/)).toBeInTheDocument();
    expect(screen.getByText(/Снятые ограничения \(1\)/)).toBeInTheDocument();
  });

  it("repeats the backend's refusal rather than guessing", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { message: "Покупатель с таким адресом не найден", fieldErrors: {} },
    });
    const user = userEvent.setup();
    render(<BlockedBuyers items={[]} />);

    await user.type(screen.getByLabelText("Email покупателя"), "nobody@example.com");
    await user.type(screen.getByLabelText("Причина"), "Причина");
    await user.click(screen.getByRole("button", { name: "Закрыть доступ" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("не найден");
    expect(refresh).not.toHaveBeenCalled();
  });
});
