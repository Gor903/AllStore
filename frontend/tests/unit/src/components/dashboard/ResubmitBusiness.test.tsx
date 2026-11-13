import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ResubmitBusiness } from "@/components/dashboard/ResubmitBusiness";

/**
 * Answering a refusal.
 *
 * This button exists at all because `rejected` is deliberately not `blocked`: a refusal says
 * what is wrong and expects an answer, so the seller needs a way to give one without writing to
 * support. A refusal of the answer itself therefore has to be shown — a button that silently
 * does nothing is how somebody ends up writing to support anyway.
 */

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

beforeEach(() => {
  refresh.mockClear();
  apiPost.mockReset().mockResolvedValue({ ok: true, data: undefined });
});

describe("ResubmitBusiness", () => {
  it("puts the application back in the queue", async () => {
    render(<ResubmitBusiness />);

    await userEvent.click(screen.getByRole("button", { name: "Отправить заявку снова" }));

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith("/users/me/business/resubmit", {}));
  });

  it("reloads the page, which now says the application is waiting", async () => {
    render(<ResubmitBusiness />);

    await userEvent.click(screen.getByRole("button", { name: "Отправить заявку снова" }));

    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("cannot be pressed twice into the same queue", async () => {
    apiPost.mockReturnValue(new Promise(() => {}));
    render(<ResubmitBusiness />);

    await userEvent.click(screen.getByRole("button", { name: "Отправить заявку снова" }));

    expect(screen.getByRole("button", { name: "Отправляем…" })).toBeDisabled();
  });

  it("shows why the application was not taken", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "conflict", message: "Заявка уже на рассмотрении", fieldErrors: {} },
    });
    render(<ResubmitBusiness />);

    await userEvent.click(screen.getByRole("button", { name: "Отправить заявку снова" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Заявка уже на рассмотрении");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("can be tried again after a refusal", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "offline", message: "Сервер недоступен", fieldErrors: {} },
    });
    render(<ResubmitBusiness />);

    await userEvent.click(screen.getByRole("button", { name: "Отправить заявку снова" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Отправить заявку снова" })).toBeEnabled();
  });
});
