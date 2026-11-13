import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { VerifyEmailNotice } from "@/components/auth/VerifyEmailNotice";

/**
 * The notice shown to an account whose address has not answered yet.
 *
 * Worded as a thing to finish rather than a thing being withheld. Only one door is actually
 * closed — opening a shop — and saying so plainly is better than a banner implying the whole
 * site is hostage: the second kind gets dismissed, and then nobody confirms anything. That is
 * why a buyer and a seller are told different things, and it is the part worth asserting.
 */

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

const EMAIL = "person@example.am";

beforeEach(() => {
  apiPost.mockReset().mockResolvedValue({ ok: true, data: undefined });
});

describe("VerifyEmailNotice", () => {
  it("names the address that has not answered", () => {
    render(<VerifyEmailNotice email={EMAIL} seller={false} />);

    expect(screen.getByText(EMAIL)).toBeInTheDocument();
  });

  it("tells a seller which door is closed", () => {
    render(<VerifyEmailNotice email={EMAIL} seller={true} />);

    expect(screen.getByText(/магазин открыть нельзя/i)).toBeInTheDocument();
  });

  it("does not tell a buyer anything is closed, because nothing is", () => {
    render(<VerifyEmailNotice email={EMAIL} seller={false} />);

    expect(screen.queryByText(/нельзя/i)).not.toBeInTheDocument();
    expect(screen.getByText(/чтобы мы могли с вами связаться/i)).toBeInTheDocument();
  });

  it("asks for another letter when the first one did not arrive", async () => {
    render(<VerifyEmailNotice email={EMAIL} seller={false} />);

    await userEvent.click(screen.getByRole("button", { name: /ещё раз/i }));

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith("/auth/email/verify", {}));
  });

  it("says the letter went, and stops offering to send it again", async () => {
    render(<VerifyEmailNotice email={EMAIL} seller={false} />);

    await userEvent.click(screen.getByRole("button", { name: /ещё раз/i }));

    expect(await screen.findByRole("status")).toHaveTextContent(/письмо отправлено/i);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("cannot be pressed twice while a letter is on its way", async () => {
    apiPost.mockReturnValue(new Promise(() => {}));
    render(<VerifyEmailNotice email={EMAIL} seller={false} />);

    await userEvent.click(screen.getByRole("button", { name: /ещё раз/i }));

    expect(screen.getByRole("button", { name: /отправляем/i })).toBeDisabled();
  });

  it("shows why the letter did not go, rather than pretending it did", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "too_many_requests", message: "Слишком много попыток", fieldErrors: {} },
    });
    render(<VerifyEmailNotice email={EMAIL} seller={false} />);

    await userEvent.click(screen.getByRole("button", { name: /ещё раз/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Слишком много попыток");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("leaves the button there after a refusal, because trying again is the answer", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "offline", message: "Сервер недоступен", fieldErrors: {} },
    });
    render(<VerifyEmailNotice email={EMAIL} seller={false} />);

    await userEvent.click(screen.getByRole("button", { name: /ещё раз/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ещё раз/i })).toBeEnabled();
  });
});
