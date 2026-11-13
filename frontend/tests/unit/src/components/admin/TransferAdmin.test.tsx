import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TransferAdmin } from "@/components/admin/TransferAdmin";

/**
 * Handing the one administrator role to somebody else.
 *
 * There is no "make another administrator" because there is never another: the role moves as a
 * whole, in one transaction, and the person pressing this is a moderator when it returns. It is
 * the only button on the screen that takes something away from whoever presses it, which is why
 * it asks first, says what will be lost, and then sends them somewhere they still have access.
 */

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

vi.mock("@/components/auth/useStepUp", () => ({
  useStepUp: () => ({
    attempt: (run: () => Promise<unknown>) => run(),
    prompt: null,
  }),
}));

const USER = "11111111-1111-1111-1111-111111111111";
const EMAIL = "moderator@allstore.am";

beforeEach(() => {
  push.mockClear();
  refresh.mockClear();
  apiPost.mockReset().mockResolvedValue({ ok: true, data: undefined });
});

describe("TransferAdmin", () => {
  it("does nothing on the first press but ask", async () => {
    render(<TransferAdmin userId={USER} email={EMAIL} />);

    await userEvent.click(screen.getByRole("button", { name: "Передать админку" }));

    expect(apiPost).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Передать" })).toBeInTheDocument();
  });

  it("names who it is about to hand the platform to", async () => {
    render(<TransferAdmin userId={USER} email={EMAIL} />);

    await userEvent.click(screen.getByRole("button", { name: "Передать админку" }));

    expect(screen.getByText(EMAIL)).toBeInTheDocument();
  });

  it("says what the administrator is about to lose", async () => {
    render(<TransferAdmin userId={USER} email={EMAIL} />);

    await userEvent.click(screen.getByRole("button", { name: "Передать админку" }));

    expect(screen.getByText(/станете\s+модератором/i)).toBeInTheDocument();
    expect(screen.getByText(/потеряете доступ/i)).toBeInTheDocument();
  });

  it("hands it over once the question is answered", async () => {
    render(<TransferAdmin userId={USER} email={EMAIL} />);

    await userEvent.click(screen.getByRole("button", { name: "Передать админку" }));
    await userEvent.click(screen.getByRole("button", { name: "Передать" }));

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith(`/admin/users/${USER}/transfer-admin`, {}),
    );
  });

  it("sends them to the queues, because the admin screens are not theirs now", async () => {
    render(<TransferAdmin userId={USER} email={EMAIL} />);

    await userEvent.click(screen.getByRole("button", { name: "Передать админку" }));
    await userEvent.click(screen.getByRole("button", { name: "Передать" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/moderation"));
    expect(refresh).toHaveBeenCalled();
  });

  it("takes the question back when it is dismissed, and changes nothing", async () => {
    render(<TransferAdmin userId={USER} email={EMAIL} />);

    await userEvent.click(screen.getByRole("button", { name: "Передать админку" }));
    await userEvent.click(screen.getByRole("button", { name: "Отмена" }));

    expect(screen.queryByRole("button", { name: "Передать" })).not.toBeInTheDocument();
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("says why the platform refused, and keeps the administrator where they are", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "conflict", message: "У аккаунта есть магазин", fieldErrors: {} },
    });
    render(<TransferAdmin userId={USER} email={EMAIL} />);

    await userEvent.click(screen.getByRole("button", { name: "Передать админку" }));
    await userEvent.click(screen.getByRole("button", { name: "Передать" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("У аккаунта есть магазин");
    expect(push).not.toHaveBeenCalled();
  });

  it("leaves the question open after a refusal, so it can be read and retried", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "conflict", message: "У аккаунта есть магазин", fieldErrors: {} },
    });
    render(<TransferAdmin userId={USER} email={EMAIL} />);

    await userEvent.click(screen.getByRole("button", { name: "Передать админку" }));
    await userEvent.click(screen.getByRole("button", { name: "Передать" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Передать" })).toBeEnabled();
  });

  it("cannot be asked a second time while the first is in flight", async () => {
    apiPost.mockReturnValue(new Promise(() => {}));
    render(<TransferAdmin userId={USER} email={EMAIL} />);

    await userEvent.click(screen.getByRole("button", { name: "Передать админку" }));
    await userEvent.click(screen.getByRole("button", { name: "Передать" }));

    expect(screen.getByRole("button", { name: "Передать" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Отмена" })).toBeDisabled();
  });
});
