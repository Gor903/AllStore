import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ResubmitBusiness } from "@/components/dashboard/ResubmitBusiness";

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
  apiPost.mockReset().mockResolvedValue({ ok: true, data: {} });
});

describe("answering a refusal", () => {
  it("sends the application back into the queue", async () => {
    const user = userEvent.setup();
    render(<ResubmitBusiness />);

    await user.click(screen.getByRole("button", { name: "Отправить заявку снова" }));

    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(apiPost).toHaveBeenCalledWith("/users/me/business/resubmit", {});
    expect(refresh).toHaveBeenCalled();
  });

  it("repeats the backend's refusal rather than pretending it worked", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { message: "Повторно подать можно только отклонённую заявку", fieldErrors: {} },
    });
    const user = userEvent.setup();
    render(<ResubmitBusiness />);

    await user.click(screen.getByRole("button", { name: "Отправить заявку снова" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("только отклонённую заявку");
    expect(refresh).not.toHaveBeenCalled();
  });
});
