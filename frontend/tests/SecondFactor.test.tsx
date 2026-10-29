import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/auth/LoginForm";
import { SecondFactor } from "@/components/auth/SecondFactor";

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh, replace: vi.fn() }),
}));

function answer(status: number, body: unknown = {}): Response {
  return { ok: status < 400, status, json: async () => body } as Response;
}

beforeEach(() => {
  push.mockClear();
  refresh.mockClear();
});

describe("signing in with a second factor", () => {
  it("asks for a code instead of complaining when the password was right", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => answer(401, { error: { code: "totp_required", message: "Введите код" } })),
    );
    const user = userEvent.setup();
    render(<LoginForm next={null} />);

    await user.type(screen.getByLabelText("Email"), "admin@example.com");
    await user.type(screen.getByLabelText("Пароль"), "a-password-1");
    await user.click(screen.getByRole("button", { name: "Войти" }));

    // the refusal is not an error here — it is the second half of the form arriving
    expect(await screen.findByLabelText("Код")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(push).not.toHaveBeenCalled();
  });

  it("sends the code to the route that finishes the sign-in", async () => {
    const fetchMock = vi.fn<(url: string, init: RequestInit) => Promise<Response>>();
    fetchMock
      .mockResolvedValueOnce(answer(401, { error: { code: "totp_required", message: "x" } }))
      .mockResolvedValueOnce(answer(200, { role: "admin", must_change_password: false }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<LoginForm next={null} />);

    await user.type(screen.getByLabelText("Email"), "admin@example.com");
    await user.type(screen.getByLabelText("Пароль"), "a-password-1");
    await user.click(screen.getByRole("button", { name: "Войти" }));
    await user.type(await screen.findByLabelText("Код"), "123456");
    await user.click(screen.getByRole("button", { name: "Подтвердить" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalled();
    });
    const second = fetchMock.mock.calls.at(1);
    if (!second) {
      throw new Error("the code was never sent");
    }
    expect(second[0]).toContain("/auth/login/totp");
    expect(JSON.parse(String(second[1].body))).toEqual({ code: "123456" });
  });

  it("starts at the code when the server already paused the sign-in", () => {
    // the Google callback lands here, having nowhere to put a refusal a browser can read
    render(<LoginForm next={null} paused />);

    expect(screen.getByLabelText("Код")).toBeInTheDocument();
    expect(screen.queryByLabelText("Пароль")).toBeNull();
  });

  it("says a wrong code was wrong and stays on the code", async () => {
    const fetchMock = vi.fn<(url: string, init: RequestInit) => Promise<Response>>();
    fetchMock
      .mockResolvedValueOnce(answer(401, { error: { code: "totp_required", message: "x" } }))
      .mockResolvedValueOnce(
        answer(403, { error: { code: "totp_invalid_code", message: "Код не подходит" } }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<LoginForm next={null} />);

    await user.type(screen.getByLabelText("Email"), "admin@example.com");
    await user.type(screen.getByLabelText("Пароль"), "a-password-1");
    await user.click(screen.getByRole("button", { name: "Войти" }));
    await user.type(await screen.findByLabelText("Код"), "000000");
    await user.click(screen.getByRole("button", { name: "Подтвердить" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Код не подходит");
    expect(screen.getByLabelText("Код")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});

describe("the second-factor settings", () => {
  const off = { enabled: false, required: false, recovery_codes_left: 0 };

  it("tells staff that nothing else opens until it is set up", () => {
    render(<SecondFactor status={{ ...off, required: true }} />);

    expect(screen.getByText(/остальные разделы закрыты/)).toBeInTheDocument();
  });

  it("shows the key and the picture, because a camera is not always available", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        answer(200, { secret: "ABCDEFGH", uri: "otpauth://x", qr: "data:image/svg+xml;base64,x" }),
      ),
    );
    const user = userEvent.setup();
    render(<SecondFactor status={off} />);

    await user.click(screen.getByRole("button", { name: "Привязать приложение" }));

    expect(await screen.findByText("ABCDEFGH")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "QR-код для приложения" })).toBeInTheDocument();
  });

  it("shows the recovery codes once and says so", async () => {
    const fetchMock = vi.fn<(url: string, init: RequestInit) => Promise<Response>>();
    fetchMock
      .mockResolvedValueOnce(answer(200, { secret: "A", uri: "otpauth://x", qr: "data:,x" }))
      .mockResolvedValueOnce(answer(200, { recovery_codes: ["aaaaa-bbbbb", "ccccc-ddddd"] }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<SecondFactor status={off} />);

    await user.click(screen.getByRole("button", { name: "Привязать приложение" }));
    await user.type(await screen.findByLabelText("Код из приложения"), "123456");
    await user.click(screen.getByRole("button", { name: "Включить" }));

    expect(await screen.findByText("aaaaa-bbbbb")).toBeInTheDocument();
    expect(screen.getByText(/показать ещё раз мы не сможем/)).toBeInTheDocument();
  });

  it("asks for a code before turning it off", async () => {
    const user = userEvent.setup();
    render(<SecondFactor status={{ enabled: true, required: false, recovery_codes_left: 7 }} />);

    await user.click(screen.getByRole("button", { name: "Выключить" }));

    // an unattended screen reaches this button; it must not be enough to press it
    expect(screen.getByLabelText("Код из приложения")).toBeInTheDocument();
  });
});
