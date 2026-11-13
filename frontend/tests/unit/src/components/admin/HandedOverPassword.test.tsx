import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HandedOverPassword } from "@/components/admin/HandedOverPassword";

/**
 * The generated password, shown the one time it can be read.
 *
 * It lives in that one answer and nowhere else: the row holds a hash, the journal records that
 * a password was handed over rather than which one, and no letter carries it (ADR 28). So the
 * screen has to say plainly that there is no second look — an administrator who closes the tab
 * expecting to find it later has lost it, and the way back is to issue another.
 *
 * The copy button is allowed to fail. A page served over plain http has no clipboard, and the
 * value is on screen and can be selected by hand — a thrown error there would look like the
 * appointment itself had broken.
 */

const EMAIL = "new-moderator@example.com";
const PASSWORD = "kf7p-2mxq-9vrt-ha3d";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HandedOverPassword", () => {
  it("shows the password, because this is the only place it can be read", () => {
    render(<HandedOverPassword email={EMAIL} password={PASSWORD} />);

    expect(screen.getByText(PASSWORD)).toBeInTheDocument();
  });

  it("names the account it opens, so two appointments cannot be confused", () => {
    render(<HandedOverPassword email={EMAIL} password={PASSWORD} />);

    expect(screen.getByText(EMAIL)).toBeInTheDocument();
  });

  it("says there is no letter and no second look", () => {
    render(<HandedOverPassword email={EMAIL} password={PASSWORD} />);

    expect(screen.getByRole("status")).toHaveTextContent(/в письме его нет/i);
    expect(screen.getByRole("status")).toHaveTextContent(/показан он один раз/i);
  });

  it("announces itself, because it appears after a form rather than with the page", () => {
    render(<HandedOverPassword email={EMAIL} password={PASSWORD} />);

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("copies the password and nothing around it", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    render(<HandedOverPassword email={EMAIL} password={PASSWORD} />);

    await userEvent.click(screen.getByRole("button", { name: "Скопировать" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(PASSWORD));
    expect(await screen.findByRole("button", { name: "Скопировано" })).toBeInTheDocument();
  });

  it("stays usable where there is no clipboard at all", async () => {
    vi.stubGlobal("navigator", {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error("not allowed")) },
    });
    render(<HandedOverPassword email={EMAIL} password={PASSWORD} />);

    await userEvent.click(screen.getByRole("button", { name: "Скопировать" }));

    // still offering to copy, and the value is still on screen to be selected by hand
    expect(screen.getByRole("button", { name: "Скопировать" })).toBeInTheDocument();
    expect(screen.getByText(PASSWORD)).toBeInTheDocument();
  });

  it("says what the password is good for and how long it lasts", () => {
    render(<HandedOverPassword email={EMAIL} password={PASSWORD} />);

    expect(screen.getByRole("status")).toHaveTextContent(/72 часа/);
  });
});
