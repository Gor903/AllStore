import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfirmEmail } from "@/components/auth/ConfirmEmail";
import { VerifyEmailNotice } from "@/components/auth/VerifyEmailNotice";

const apiPost = vi.fn();
vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

beforeEach(() => {
  apiPost.mockReset().mockResolvedValue({ ok: true, data: { message: "Адрес подтверждён" } });
});

describe("ConfirmEmail", () => {
  it("spends the link on arrival rather than asking for another click", async () => {
    render(<ConfirmEmail token="from-the-letter" />);

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith("/auth/email/confirm", { token: "from-the-letter" });
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Адрес подтверждён");
  });

  it("says what went wrong when the link is spent or stale", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { message: "Ссылка недействительна или устарела", fieldErrors: {} },
    });

    render(<ConfirmEmail token="stale" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Ссылка недействительна");
  });

  it("tries once, not twice, so a double mount does not meet its own spent link", async () => {
    const { rerender } = render(<ConfirmEmail token="t" />);
    rerender(<ConfirmEmail token="t" />);

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledTimes(1);
    });
  });
});

describe("VerifyEmailNotice", () => {
  it("tells a seller which door is actually closed", () => {
    render(<VerifyEmailNotice email="seller@example.com" seller />);

    expect(screen.getByText(/магазин открыть нельзя/)).toBeInTheDocument();
  });

  it("does not imply a buyer is being held hostage", () => {
    render(<VerifyEmailNotice email="buyer@example.com" seller={false} />);

    expect(screen.queryByText(/магазин открыть нельзя/)).not.toBeInTheDocument();
    expect(screen.getByText(/чтобы мы могли с вами связаться/)).toBeInTheDocument();
  });

  it("asks for the letter again", async () => {
    const user = userEvent.setup();
    render(<VerifyEmailNotice email="buyer@example.com" seller={false} />);

    await user.click(screen.getByRole("button", { name: "Прислать письмо ещё раз" }));

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith("/auth/email/verify", {});
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Письмо отправлено");
  });

  it("shows why nothing happened when the server refuses", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { message: "Слишком много попыток, попробуйте позже", fieldErrors: {} },
    });
    const user = userEvent.setup();
    render(<VerifyEmailNotice email="buyer@example.com" seller={false} />);

    await user.click(screen.getByRole("button", { name: "Прислать письмо ещё раз" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Слишком много попыток");
  });
});
