import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { VerdictButtons, type Verdict } from "@/components/moderation/VerdictButtons";

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

const VERDICTS: Verdict[] = [
  { label: "Одобрить", action: "approve" },
  { label: "Отклонить", action: "reject", reasonPrompt: "Что исправить?", danger: true },
];

const BASE = "/moderation/products/11111111-1111-1111-1111-111111111111";

beforeEach(() => {
  refresh.mockClear();
  apiPost.mockReset().mockResolvedValue({ ok: true, data: {} });
});

describe("VerdictButtons", () => {
  it("passes a verdict that needs no reason at once", async () => {
    const user = userEvent.setup();
    render(<VerdictButtons basePath={BASE} verdicts={VERDICTS} />);

    await user.click(screen.getByRole("button", { name: "Одобрить" }));

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(`${BASE}/approve`, {}));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("asks for a reason before refusing, and does not fire until there is one", async () => {
    const user = userEvent.setup();
    render(<VerdictButtons basePath={BASE} verdicts={VERDICTS} />);

    await user.click(screen.getByRole("button", { name: "Отклонить" }));

    expect(screen.getByText("Что исправить?")).toBeInTheDocument();
    expect(apiPost).not.toHaveBeenCalled();
    // an empty box is not a reason, so the button stays shut
    const confirm = screen.getAllByRole("button", { name: "Отклонить" })[1];
    expect(confirm).toBeDisabled();
  });

  it("sends the reason along with the refusal", async () => {
    const user = userEvent.setup();
    render(<VerdictButtons basePath={BASE} verdicts={VERDICTS} />);
    await user.click(screen.getByRole("button", { name: "Отклонить" }));

    await user.type(screen.getByRole("textbox"), "Фото не то");
    await user.click(screen.getAllByRole("button", { name: "Отклонить" })[1]!);

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith(`${BASE}/reject`, { reason: "Фото не то" }),
    );
  });

  it("lets the moderator back out of a refusal", async () => {
    const user = userEvent.setup();
    render(<VerdictButtons basePath={BASE} verdicts={VERDICTS} />);
    await user.click(screen.getByRole("button", { name: "Отклонить" }));

    await user.click(screen.getByRole("button", { name: "Отмена" }));

    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("shows what the backend refused and keeps the queue as it was", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { message: "Одобрить можно только товар на проверке", fieldErrors: {} },
    });
    const user = userEvent.setup();
    render(<VerdictButtons basePath={BASE} verdicts={VERDICTS} />);

    await user.click(screen.getByRole("button", { name: "Одобрить" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("только товар на проверке");
    expect(refresh).not.toHaveBeenCalled();
  });
});
