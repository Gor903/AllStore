import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GoogleAccounts } from "@/components/auth/GoogleAccounts";
import { StepUp } from "@/components/auth/StepUp";

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push: vi.fn(), replace: vi.fn() }),
}));

function answer(status: number, body: unknown = {}): Response {
  return { ok: status < 400, status, json: async () => body } as Response;
}

beforeEach(() => {
  refresh.mockClear();
});

describe("attaching Google", () => {
  const none = { identities: [], configured: true, staff: false, email: "buyer@example.com" };

  it("says nothing at all when Google is not configured", () => {
    const { container } = render(<GoogleAccounts {...none} configured={false} />);

    // not an empty list: "you have none" and "we cannot ask" are different statements
    expect(container).toBeEmptyDOMElement();
  });

  it("asks for the password before offering the journey out", async () => {
    const user = userEvent.setup();
    render(<GoogleAccounts {...none} />);

    await user.click(screen.getByRole("button", { name: "Привязать Google" }));

    expect(screen.getByLabelText("Пароль")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Google/ })).toBeNull();
  });

  it("offers it once the password is proved", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => answer(204)),
    );
    const user = userEvent.setup();
    render(<GoogleAccounts {...none} />);

    await user.click(screen.getByRole("button", { name: "Привязать Google" }));
    await user.type(screen.getByLabelText("Пароль"), "a-password-1");
    await user.click(screen.getByRole("button", { name: "Подтвердить" }));

    const link = await screen.findByRole("link", { name: "Продолжить с Google" });
    expect(link.getAttribute("href")).toContain("/auth/google/link");
  });

  it("tells staff which account will be accepted", () => {
    render(<GoogleAccounts {...none} staff email="admin@example.com" />);

    expect(screen.getByText(/только аккаунт Google на адресе admin@example.com/)).toBeVisible();
  });

  it("shows what is attached, and offers to detach it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => answer(204)),
    );
    const user = userEvent.setup();
    render(
      <GoogleAccounts
        {...none}
        identities={[{ id: "one", provider: "google", email_at_link: "person@gmail.com" }]}
      />,
    );

    expect(screen.getByText("person@gmail.com")).toBeInTheDocument();
    // and no second one on offer: an account somebody has two of is one they have lost track of
    expect(screen.queryByRole("button", { name: "Привязать Google" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Отвязать" }));

    await waitFor(() => {
      expect(refresh).toHaveBeenCalled();
    });
  });

  it("says why the last way in cannot be detached", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        answer(409, {
          error: { code: "no_password_set", message: "Это единственный способ войти в аккаунт." },
        }),
      ),
    );
    const user = userEvent.setup();
    render(
      <GoogleAccounts
        {...none}
        identities={[{ id: "one", provider: "google", email_at_link: "person@gmail.com" }]}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Отвязать" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("единственный способ");
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("proving the password again", () => {
  it("sends it to the step-up route", async () => {
    const fetchMock = vi.fn<(url: string, init: RequestInit) => Promise<Response>>(async () =>
      answer(204),
    );
    vi.stubGlobal("fetch", fetchMock);
    const done = vi.fn();
    const user = userEvent.setup();
    render(<StepUp reason="Подтвердите пароль." onDone={done} />);

    await user.type(screen.getByLabelText("Пароль"), "a-password-1");
    await user.click(screen.getByRole("button", { name: "Подтвердить" }));

    await waitFor(() => {
      expect(done).toHaveBeenCalled();
    });
    expect(fetchMock.mock.calls.at(0)?.[0]).toContain("/auth/verify");
  });

  it("stays put and complains when the password is wrong", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        answer(401, { error: { code: "invalid_credentials", message: "Текущий пароль неверен" } }),
      ),
    );
    const done = vi.fn();
    const user = userEvent.setup();
    render(<StepUp reason="Подтвердите пароль." onDone={done} />);

    await user.type(screen.getByLabelText("Пароль"), "not-the-password");
    await user.click(screen.getByRole("button", { name: "Подтвердить" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("неверен");
    expect(done).not.toHaveBeenCalled();
  });
});
