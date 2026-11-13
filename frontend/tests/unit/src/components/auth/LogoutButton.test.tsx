import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LogoutButton } from "@/components/auth/LogoutButton";

/**
 * Signing out.
 *
 * Two things here are not decoration. The button goes dead while the request is in flight, or
 * an impatient second click sends a second logout for a session that is already gone. And the
 * router is refreshed as well as pushed: the cached server render of the page behind still has
 * the person's name on it, and a push alone would leave them looking at it.
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

beforeEach(() => {
  push.mockClear();
  refresh.mockClear();
  apiPost.mockReset().mockResolvedValue({ ok: true, data: undefined });
});

describe("LogoutButton", () => {
  it("ends the session on the server rather than only in the browser", async () => {
    render(<LogoutButton />);

    await userEvent.click(screen.getByRole("button", { name: "Выйти" }));

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith("/auth/logout", {}));
  });

  it("sends the person to the sign-in screen", async () => {
    render(<LogoutButton />);

    await userEvent.click(screen.getByRole("button", { name: "Выйти" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/login"));
  });

  it("drops the cached render, which still has their name on it", async () => {
    render(<LogoutButton />);

    await userEvent.click(screen.getByRole("button", { name: "Выйти" }));

    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("cannot be pressed twice while it is working", async () => {
    let finish: (value: unknown) => void = () => {};
    apiPost.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    render(<LogoutButton />);

    await userEvent.click(screen.getByRole("button", { name: "Выйти" }));

    const button = screen.getByRole("button", { name: "Выходим…" });
    expect(button).toBeDisabled();
    finish({ ok: true, data: undefined });
    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(1));
  });

  it("says what it is doing while it does it", async () => {
    apiPost.mockReturnValue(new Promise(() => {}));
    render(<LogoutButton />);

    await userEvent.click(screen.getByRole("button", { name: "Выйти" }));

    expect(screen.getByRole("button", { name: "Выходим…" })).toBeInTheDocument();
  });
});
