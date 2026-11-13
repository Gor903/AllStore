import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RoleSelect } from "@/components/admin/RoleSelect";

/**
 * Changing somebody's role from the list of accounts.
 *
 * Appointing a moderator used to mean a direct write to the database. The refusals the backend
 * can answer with — the last administrator, an account that runs a shop — are shown next to the
 * row rather than swallowed: the administrator has to learn why.
 *
 * And on a refusal the select snaps back. A box left showing "moderator" for an account the
 * server refused to promote is a screen that disagrees with the database, and the next person
 * to read it has no way of telling which of the two is right.
 */

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

// the step-up prompt is its own screen with its own tests; here it is a pass-through
vi.mock("@/components/auth/useStepUp", () => ({
  useStepUp: () => ({
    attempt: (run: () => Promise<unknown>) => run(),
    prompt: null,
  }),
}));

const USER = "11111111-1111-1111-1111-111111111111";

beforeEach(() => {
  refresh.mockClear();
  apiPost.mockReset().mockResolvedValue({ ok: true, data: { id: USER, role: "moderator" } });
});

describe("RoleSelect", () => {
  it("offers every role the platform has", () => {
    render(<RoleSelect userId={USER} role="buyer" />);

    expect(screen.getByRole("combobox", { name: "Роль" })).toBeInTheDocument();
    for (const label of ["покупатель", "продавец", "модератор", "админ"]) {
      expect(screen.getByRole("option", { name: label })).toBeInTheDocument();
    }
  });

  it("shows the role the account has now", () => {
    render(<RoleSelect userId={USER} role="seller" />);

    expect(screen.getByRole("combobox", { name: "Роль" })).toHaveValue("seller");
  });

  it("asks the backend for the role that was picked", async () => {
    render(<RoleSelect userId={USER} role="buyer" />);

    await userEvent.selectOptions(screen.getByRole("combobox"), "moderator");

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith(`/admin/users/${USER}/role`, { role: "moderator" }),
    );
  });

  it("asks for nothing when the role picked is the one already there", async () => {
    render(<RoleSelect userId={USER} role="buyer" />);

    await userEvent.selectOptions(screen.getByRole("combobox"), "buyer");

    expect(apiPost).not.toHaveBeenCalled();
  });

  it("reloads the list, because the row it is in now says something else", async () => {
    render(<RoleSelect userId={USER} role="buyer" />);

    await userEvent.selectOptions(screen.getByRole("combobox"), "moderator");

    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("says why the backend refused", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: {
        code: "conflict",
        message: "Нельзя снять роль с последнего администратора",
        fieldErrors: {},
      },
    });
    render(<RoleSelect userId={USER} role="admin" />);

    await userEvent.selectOptions(screen.getByRole("combobox"), "buyer");

    expect(await screen.findByRole("alert")).toHaveTextContent("последнего администратора");
  });

  it("snaps the box back, so the screen cannot disagree with the database", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "conflict", message: "Нельзя", fieldErrors: {} },
    });
    render(<RoleSelect userId={USER} role="admin" />);

    await userEvent.selectOptions(screen.getByRole("combobox"), "buyer");

    await waitFor(() => expect(screen.getByRole("combobox")).toHaveValue("admin"));
    expect(refresh).not.toHaveBeenCalled();
  });

  it("cannot be changed again while a change is in flight", async () => {
    apiPost.mockReturnValue(new Promise(() => {}));
    render(<RoleSelect userId={USER} role="buyer" />);

    await userEvent.selectOptions(screen.getByRole("combobox"), "moderator");

    expect(screen.getByRole("combobox")).toBeDisabled();
  });

  it("names the box for a screen reader without putting a word on the screen", () => {
    /* The column already has a heading, so a visible label would repeat it on every row —
       but a select with no name at all is a select nobody can find by voice. */
    render(<RoleSelect userId={USER} role="buyer" />);

    expect(screen.getByText("Роль")).toHaveClass("sr-only");
  });
});
