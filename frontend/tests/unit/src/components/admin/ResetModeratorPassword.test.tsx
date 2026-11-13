import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ResetModeratorPassword } from "@/components/admin/ResetModeratorPassword";

/**
 * Handing a moderator a new temporary password.
 *
 * There is no recovery link to send and nothing to wait for: the administrator already decides
 * who moderates, so letting them restore access is no new authority. The replacement is
 * generated like the first one and shown once (ADR 28) — which is why the password has to
 * appear on this screen and why losing it means issuing another rather than looking it up.
 *
 * The step-up prompt wrapping the call is its own screen with its own tests; here it is a
 * pass-through, so that what is asserted is this button rather than that one.
 */

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
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
const PASSWORD = "kf7p-2mxq-9vrt-ha3d";

beforeEach(() => {
  refresh.mockClear();
  apiPost.mockReset().mockResolvedValue({
    ok: true,
    data: { user: { id: USER, email: EMAIL, role: "moderator" }, password: PASSWORD },
  });
});

describe("ResetModeratorPassword", () => {
  it("asks for a password rather than for a letter to be sent", async () => {
    render(<ResetModeratorPassword userId={USER} email={EMAIL} />);

    await userEvent.click(screen.getByRole("button", { name: "Выдать новый пароль" }));

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith(`/admin/moderators/${USER}/password`, {}),
    );
  });

  it("shows the password, because this is the one moment it can be read", async () => {
    render(<ResetModeratorPassword userId={USER} email={EMAIL} />);

    await userEvent.click(screen.getByRole("button", { name: "Выдать новый пароль" }));

    expect(await screen.findByText(PASSWORD)).toBeInTheDocument();
  });

  it("names the account the password opens", async () => {
    render(<ResetModeratorPassword userId={USER} email={EMAIL} />);

    await userEvent.click(screen.getByRole("button", { name: "Выдать новый пароль" }));

    expect(await screen.findByRole("status")).toHaveTextContent(EMAIL);
  });

  it("nothing is on screen before the administrator presses anything", () => {
    render(<ResetModeratorPassword userId={USER} email={EMAIL} />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("reloads the row, which now says a password is waiting to be used", async () => {
    render(<ResetModeratorPassword userId={USER} email={EMAIL} />);

    await userEvent.click(screen.getByRole("button", { name: "Выдать новый пароль" }));

    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("cannot be pressed twice, because the second password would replace the first", async () => {
    apiPost.mockReturnValue(new Promise(() => {}));
    render(<ResetModeratorPassword userId={USER} email={EMAIL} />);

    await userEvent.click(screen.getByRole("button", { name: "Выдать новый пароль" }));

    expect(screen.getByRole("button", { name: "Выдаём…" })).toBeDisabled();
  });

  it("says why nothing was issued", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "not_found", message: "Это не модератор", fieldErrors: {} },
    });
    render(<ResetModeratorPassword userId={USER} email={EMAIL} />);

    await userEvent.click(screen.getByRole("button", { name: "Выдать новый пароль" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Это не модератор");
    expect(screen.queryByText(PASSWORD)).not.toBeInTheDocument();
  });
});
