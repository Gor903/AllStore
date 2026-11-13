import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfirmEmail } from "@/components/auth/ConfirmEmail";

/**
 * The page the link in the letter opens, which spends the link on arrival.
 *
 * A button would be safer against a mail client that follows links to preview them — and worse
 * for everybody else, who would arrive at a page whose only content is a second thing to click.
 * The link is single-use either way; a preview that spends it costs one resend.
 *
 * The guard against a double attempt is the part a test is needed for. React mounts an effect
 * twice in development, and the second attempt would meet a link the first one just spent — so
 * a working confirmation would report itself as a failure, on every developer's machine only.
 */

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

const TOKEN = "a-token-from-the-letter";

beforeEach(() => {
  apiPost.mockReset().mockResolvedValue({ ok: true, data: { message: "Адрес подтверждён" } });
});

describe("ConfirmEmail", () => {
  it("spends the link without being asked", async () => {
    render(<ConfirmEmail token={TOKEN} />);

    expect(await screen.findByRole("status")).toBeInTheDocument();
    expect(apiPost).toHaveBeenCalledWith("/auth/email/confirm", { token: TOKEN });
  });

  it("says it is working while it works", () => {
    apiPost.mockReturnValue(new Promise(() => {}));

    render(<ConfirmEmail token={TOKEN} />);

    expect(screen.getByText("Подтверждаем…")).toBeInTheDocument();
  });

  it("spends it once however many times the effect runs", async () => {
    const { rerender } = render(<ConfirmEmail token={TOKEN} />);
    rerender(<ConfirmEmail token={TOKEN} />);

    expect(await screen.findByRole("status")).toBeInTheDocument();
    expect(apiPost).toHaveBeenCalledTimes(1);
  });

  it("announces success and offers the cabinet", async () => {
    render(<ConfirmEmail token={TOKEN} />);

    expect(await screen.findByRole("status")).toHaveTextContent("Адрес подтверждён");
    expect(screen.getByRole("link", { name: "В кабинет" })).toHaveAttribute("href", "/dashboard");
  });

  it("says what went wrong, in the backend's own words", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "not_found", message: "Ссылка больше не действует", fieldErrors: {} },
    });

    render(<ConfirmEmail token={TOKEN} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Ссылка больше не действует");
  });

  it("sends somebody whose link is spent to the sign-in screen, not the cabinet", async () => {
    /* They may not be signed in at all: a letter is opened on whatever device is to hand,
       and the cabinet would bounce them straight back to /login anyway. */
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "not_found", message: "Ссылка больше не действует", fieldErrors: {} },
    });

    render(<ConfirmEmail token={TOKEN} />);

    expect(await screen.findByRole("link", { name: "Ко входу" })).toHaveAttribute("href", "/login");
  });
});
