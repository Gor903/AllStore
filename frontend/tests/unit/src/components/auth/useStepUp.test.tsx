import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useStepUp } from "@/components/auth/useStepUp";
import type { ApiResult } from "@/lib/browser-api";

/**
 * Running an action the server may refuse until the password is given again.
 *
 * That refusal is a question, not a sentence to print, and the answer is a screen. So the
 * promise deliberately does not settle on it: it settles on what the action did *after* the
 * password was confirmed, and the call site keeps one path — ask, read the answer — instead of
 * growing a second one for the case where the answer arrives a minute later.
 *
 * Which makes the settling the thing to test. A promise that settled early would leave the call
 * site showing "verification required" as if it were a result; one that never settled would
 * leave a button disabled forever. Both are invisible in the component that uses it.
 *
 * The action is replayed rather than the form resubmitted, because the alternative is to confirm
 * the password and be handed back an empty form.
 */

vi.mock("@/components/auth/StepUp", () => ({
  StepUp: ({
    reason,
    onDone,
    onCancel,
  }: {
    reason: string;
    onDone: () => void;
    onCancel: () => void;
  }) => (
    <div role="dialog">
      <p>{reason}</p>
      <button type="button" onClick={onDone}>
        Подтвердить
      </button>
      <button type="button" onClick={onCancel}>
        Отмена
      </button>
    </div>
  ),
}));

const REFUSED: ApiResult<string> = {
  ok: false,
  error: {
    code: "verification_required",
    message: "Подтвердите пароль, чтобы продолжить",
    fieldErrors: {},
  },
};

const action = vi.fn();

/** A call site: one button, and whatever the promise finally settled with. */
function Harness() {
  const { attempt, prompt } = useStepUp();
  const [settled, setSettled] = useState<string | null>(null);

  async function run() {
    const result = await attempt(() => action() as Promise<ApiResult<string>>);
    setSettled(result.ok ? `ok:${result.data}` : `no:${result.error.code}`);
  }

  return (
    <div>
      <button type="button" onClick={() => void run()}>
        Сделать
      </button>
      {prompt}
      {settled === null ? null : <p data-testid="settled">{settled}</p>}
    </div>
  );
}

async function press(name: string): Promise<void> {
  await userEvent.click(screen.getByRole("button", { name }));
}

beforeEach(() => {
  action.mockReset();
});

describe("useStepUp", () => {
  it("passes a successful action straight through", async () => {
    action.mockResolvedValue({ ok: true, data: "готово" });
    render(<Harness />);

    await press("Сделать");

    expect(await screen.findByTestId("settled")).toHaveTextContent("ok:готово");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("passes any other refusal straight through, because it is an answer", async () => {
    action.mockResolvedValue({
      ok: false,
      error: { code: "conflict", message: "Нельзя", fieldErrors: {} },
    });
    render(<Harness />);

    await press("Сделать");

    expect(await screen.findByTestId("settled")).toHaveTextContent("no:conflict");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("asks for the password in the server's own words", async () => {
    action.mockResolvedValue(REFUSED);
    render(<Harness />);

    await press("Сделать");

    expect(await screen.findByRole("dialog")).toHaveTextContent(
      "Подтвердите пароль, чтобы продолжить",
    );
  });

  it("does not settle while the question is on screen", async () => {
    action.mockResolvedValue(REFUSED);
    render(<Harness />);

    await press("Сделать");

    await screen.findByRole("dialog");
    expect(screen.queryByTestId("settled")).not.toBeInTheDocument();
  });

  it("replays the action once the password is confirmed", async () => {
    action.mockResolvedValueOnce(REFUSED).mockResolvedValueOnce({ ok: true, data: "готово" });
    render(<Harness />);

    await press("Сделать");
    await press("Подтвердить");

    expect(await screen.findByTestId("settled")).toHaveTextContent("ok:готово");
    expect(action).toHaveBeenCalledTimes(2);
  });

  it("takes the question away once it is answered", async () => {
    action.mockResolvedValueOnce(REFUSED).mockResolvedValueOnce({ ok: true, data: "готово" });
    render(<Harness />);

    await press("Сделать");
    await press("Подтвердить");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("asks again when the confirmation itself went stale", async () => {
    /* Through `attempt` again rather than straight to the action: a password confirmed and
       then left sitting is the same situation as one never given. */
    action.mockResolvedValue(REFUSED);
    render(<Harness />);

    await press("Сделать");
    await press("Подтвердить");

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByTestId("settled")).not.toBeInTheDocument();
  });

  it("settles with the refusal that started it when the question is dismissed", async () => {
    /* So the call site has something to show. Settling with nothing would leave a button
       spinning over an action the server already refused. */
    action.mockResolvedValue(REFUSED);
    render(<Harness />);

    await press("Сделать");
    await press("Отмена");

    expect(await screen.findByTestId("settled")).toHaveTextContent("no:verification_required");
    expect(action).toHaveBeenCalledTimes(1);
  });

  it("takes the question away when it is dismissed too", async () => {
    action.mockResolvedValue(REFUSED);
    render(<Harness />);

    await press("Сделать");
    await press("Отмена");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows nothing at all until something is refused", () => {
    render(<Harness />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
